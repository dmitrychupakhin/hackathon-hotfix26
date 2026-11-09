> Legacy/optional adapter. Основная действующая интеграция по ID теперь использует общую PostgreSQL `ai.files` и read-only volume, см. [backend-integration.md](backend-integration.md). Описанный ниже HTTP GET-download клиент остаётся отдельным необязательным модулем и не является основным маршрутом.

# Backend file ingestion contract

## Availability and responsibility

Status: this is a tested standalone Python module and a proposed integration contract.
It is not wired into FastAPI routes, application settings, or document persistence yet.
Backend-by-ID integration was explicitly deferred by the user; current HTTP uploads remain TXT/MD.

The checked-in Django backend currently has user/photo endpoints and static media handling;
**it does not implement the document-by-ID content endpoint below**. The AI client is ready
for this contract, which must be implemented and authorized in Django before remote ingestion
works. Static `MEDIA_URL` is not an authenticated substitute. AI does not inspect Django's DB
or filesystem and does not accept URLs, local paths, presigned redirects, or arbitrary download
locations from the caller.

The Django service must verify the service key and that `X-User-ID` can access the requested
file. AI supplies the owner obtained from its authenticated request; the browser must not
receive the shared service secret. A globally valid service key alone does not establish
permission to read every file.

## Proposed HTTP interface (configurable)

```http
GET /api/files/{file_id}/content
X-AI-Service-Key: <configured shared backend secret>
X-User-ID: <authenticated owner ID>
Accept-Encoding: identity
```

- `file_id`: opaque ASCII letters/digits/underscore/hyphen, starts with a letter/digit,
  1–128 characters. Numeric IDs and UUIDs are accepted. Dots, slashes, percent escapes,
  query strings and URL-shaped IDs are rejected before network access.
- Successful response: HTTP 200 with the original binary bytes, `Content-Type` and
  `Content-Disposition: attachment; filename="notice.pdf"`. RFC 5987 `filename*` is supported
  by Python's standard email header parser. Filename must be a plain filename, max 200 chars.
- Optional `Content-Length` must be nonnegative and match the actual body.
- HTTP 404 means missing or inaccessible; 401/403 means access refused. Other HTTP statuses
  (including redirects) are rejected. Backend error bodies are never returned to callers.
- HTTP compression is disabled and rejected to avoid decompression amplification. Chunked
  responses are allowed and their actual received size is checked.

`FileBackendConfig` accepts `base_url` (origin only), `service_key: SecretStr`, configurable
`content_path` with exactly one `{file_id}`, and `timeout_seconds`. HTTPS is the default.
A trusted internal Docker endpoint such as `http://backend:8000` requires explicit
`allow_http=True`. The origin/template are administrator configuration, never request fields.
Use one dedicated `httpx.AsyncClient(trust_env=False)` without default cookies, unrelated auth,
or event hooks that log request headers, and one `FileIngestor` per AI process. Close the HTTP
client during shutdown. No secrets, backend bodies or parser exception contents are logged by
this module. Network egress policy remains the deployment's responsibility; administrator
configuration permits internal origins intentionally.

## Python integration

```python
from app.infrastructure.files import FileIngestor, FileBackendConfig, ExtractionLimits

loader = FileIngestor(
    client,
    FileBackendConfig(base_url=settings.backend_url,
                      service_key=settings.backend_key,
                      content_path=settings.backend_file_path,
                      allow_http=settings.backend_allow_http),
    ExtractionLimits(max_bytes=settings.max_upload_bytes,
                     ocr_enabled=settings.ocr_enabled),
)
parsed = await loader.fetch(file_id="123", owner_id=authenticated_owner)
# Multipart uploads can use the same bounded parser without a backend:
parsed = await loader.parse(raw_bytes, name="notice.pdf", media_type="application/pdf")
```

`ParsedFile`: `name`, `text`, optional `file_id`, `media_type` (backend/upload declaration),
`original_sha256` (original bytes, distinct from the hash of extracted text), `extractor`,
`warnings`, `partial`, and `locations`. Each location has Python string character offsets
`start`/`end` into final `text`, plus optional 1-based `page`, 1-based `slide`, or `sheet` name.
Extraction is selected by filename extension with PDF/ZIP signature checks, never by trusting
MIME alone. MIME is retained as provenance; it is not a proof of format.

Store all provenance along with the text and propagate `partial` to answer checks. Missing
content must not support a confident "absent from documents" answer. DOCX has no reliable
page coordinates without a layout engine. Spreadsheet output includes cell coordinates;
numeric/date values remain raw XML values without Excel display formatting or recalculation.
Partial or OCR-derived text must be distinguished from exact original textual source bytes.

## Supported extraction and limits

- TXT/MD/CSV/JSON: UTF-8 with BOM, UTF-16 with BOM, CP1251 fallback (explicit warning).
  JSON syntax is validated. CSV quoting/content is preserved as source text.
- HTML: visible text approximation excluding script/style/template/noscript; partial warning
  because CSS, layout and image content are not rendered.
- PDF: pypdf text layer, page locations; encrypted PDFs rejected. A PDF with no extractable
  text fails with `ocr_required` unless OCR is enabled. Pages without text are flagged;
  graphics on text-bearing pages are not silently represented as recognized text.
- DOCX: paragraphs/tables, headers/footers, notes/comments; embedded graphics/objects flagged.
  No legacy binary DOC conversion. No execution of Office content or external relationships.
- PPTX: text in actual presentation slide order and slide locations; graphics and speaker
  notes that are not extracted are flagged.
- XLSX: worksheet order/names, string/numeric cell values and addresses; formulas use cached
  values with a partial warning; formulas are not recalculated. Graphics/objects flagged.
- PNG/JPEG/TIFF/BMP/WebP: local Tesseract OCR only when explicitly enabled and installed.
  Scanned PDF pages additionally require `pdftoppm`. OCR language defaults to `rus+eng`;
  both language datasets must be installed. OCR is marked partial and requires verification.
  Empty OCR output is an explicit error, never a successful empty document.
- DOC/XLS/PPT/ODT/ODS/ODP/RTF return `legacy_format_unavailable`; other binaries return
  `unsupported_format`. No claim of universal file support is made.

Python dependencies: `pypdf>=5,<7`, `defusedxml>=0.7,<1`; httpx/pydantic already exist.
Optional Debian packages for OCR: `tesseract-ocr`, `tesseract-ocr-rus`, `tesseract-ocr-eng`,
`poppler-utils`. No paid/cloud API is used for extraction.

Default limits: 10 MiB source bytes, 2M extracted characters, 64 MiB expanded Office ZIP,
2,000 ZIP members, 200 PDF pages/slides/sheets, 45 seconds extraction wall time and CPU budget,
512 MiB address space per parser process. Reaching a limit rejects the file rather than
returning truncated text. The network has an independent 20-second total deadline.

Parsing runs outside the event loop in a disposable POSIX spawn process with `RLIMIT_AS`,
`RLIMIT_CPU`, `RLIMIT_FSIZE`; deadlines kill its entire process group including OCR children.
A single semaphore bounds the whole download/parse pipeline per loader instance. Cancellation
waits for the bounded worker cleanup before releasing the slot. This is resource isolation,
not a complete OS security sandbox. Production containers should also restrict egress, mounts,
and privileges. Do not create a new ingestor per request, which would defeat concurrency bounds.

## Offline checks

`ai/.venv/bin/pytest -q tests/test_file_ingestion.py` covers MockTransport download/auth,
redirect rejection, invalid IDs/configuration, size/time limits, original hash, XML protection,
archive expansion limits, DOCX/PPTX/XLSX/PDF extraction, locations and controlled missing OCR.
Fixtures are generated in memory; no real backend or paid model requests are made.
