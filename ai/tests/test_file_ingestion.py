import asyncio
import hashlib
import io
import zipfile

import httpx
import pytest
from pydantic import SecretStr

from app.domain import DomainError
from app.infrastructure.files import ExtractionLimits, FileBackendConfig, FileIngestor
from app.infrastructure.files.extractors import extract


def config(**kwargs):
    return FileBackendConfig(
        base_url="https://backend.test", service_key=SecretStr("test-secret"), **kwargs
    )


def archive(files):
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as zipped:
        for name, body in files.items():
            zipped.writestr(name, body)
    return buffer.getvalue()


def parse(raw, name, **kwargs):
    return extract(raw, name, "application/octet-stream", "file-1", ExtractionLimits(**kwargs))


def test_plain_text_hash_and_encoding():
    raw = "Цена 18 000 рублей".encode("cp1251")
    result = parse(raw, "notice.txt")
    assert result.text == "Цена 18 000 рублей"
    assert result.original_sha256 == hashlib.sha256(raw).hexdigest()
    assert result.file_id == "file-1"
    assert result.warnings == ["encoding_assumed_cp1251"]
    assert not result.partial
    assert parse("Цена".encode("utf-16"), "notice.md").text == "Цена"


@pytest.mark.parametrize(
    "name,raw,expected",
    [
        ("data.csv", b"key,value\nprice,18000", "price,18000"),
        ("data.json", b'{"price":18000}', '"price":18000'),
        (
            "page.html",
            b"<h1>Price &amp; tax</h1><script>fake()</script><p>18000</p>",
            "Price & tax",
        ),
    ],
)
def test_text_formats(name, raw, expected):
    result = parse(raw, name)
    assert expected in result.text
    assert "fake()" not in result.text


@pytest.mark.parametrize(
    "name,raw,code",
    [
        ("secret.bin", b"hello", "unsupported_format"),
        ("image.txt", b"\x00\x01", "binary_input"),
        ("old.doc", b"legacy", "legacy_format_unavailable"),
        ("fake.pdf", b"not pdf", "unsupported_format"),
        ("../a.txt", b"hello", "invalid_filename"),
        ("image.png", b"fake", "ocr_unavailable"),
    ],
)
def test_controlled_unsupported(name, raw, code):
    with pytest.raises(DomainError) as error:
        parse(raw, name)
    assert error.value.code == code


def test_no_silent_truncation():
    with pytest.raises(DomainError, match="no truncated") as error:
        parse(b"abcdef", "a.txt", max_text_chars=5)
    assert error.value.code == "extracted_text_too_large"


def test_docx_text_tables_and_secondary_stories():
    raw = archive(
        {
            "word/document.xml": '<w:document xmlns:w="urn:w"><w:body><w:p><w:r><w:t>Notice</w:t></w:r></w:p><w:tbl><w:tr><w:tc><w:p><w:r><w:t>18000</w:t></w:r></w:p></w:tc></w:tr></w:tbl></w:body></w:document>',
            "word/header1.xml": '<w:hdr xmlns:w="urn:w"><w:p><w:r><w:t>Header</w:t></w:r></w:p></w:hdr>',
            "word/media/image1.png": b"image",
        }
    )
    result = parse(raw, "notice.docx")
    assert result.text == "Notice\n18000\nHeader"
    assert result.partial
    assert "embedded_images_charts_or_objects_not_extracted" in result.warnings


def test_archive_expansion_limit():
    raw = archive({"word/document.xml": " " * 5000})
    with pytest.raises(DomainError) as error:
        parse(raw, "notice.docx", max_archive_bytes=100)
    assert error.value.code == "unsafe_archive"


def test_xml_entities_are_blocked():
    from defusedxml.common import DefusedXmlException

    raw = archive(
        {
            "word/document.xml": '<!DOCTYPE doc [<!ENTITY x SYSTEM "file:///etc/passwd">]><doc>&x;</doc>'
        }
    )
    with pytest.raises(DefusedXmlException):
        parse(raw, "notice.docx")


def test_pptx_uses_presentation_order_and_offsets():
    raw = archive(
        {
            "ppt/presentation.xml": '<p:presentation xmlns:p="p" xmlns:r="r"><p:sldIdLst><p:sldId id="1" r:id="r2"/><p:sldId id="2" r:id="r1"/></p:sldIdLst></p:presentation>',
            "ppt/_rels/presentation.xml.rels": '<Relationships><Relationship Id="r1" Target="slides/slide1.xml"/><Relationship Id="r2" Target="slides/slide2.xml"/></Relationships>',
            "ppt/slides/slide1.xml": '<p:sld xmlns:p="p" xmlns:a="a"><a:p><a:r><a:t>Second</a:t></a:r></a:p></p:sld>',
            "ppt/slides/slide2.xml": '<p:sld xmlns:p="p" xmlns:a="a"><a:p><a:r><a:t>First</a:t></a:r></a:p></p:sld>',
        }
    )
    result = parse(raw, "slides.pptx")
    assert result.text == "First\nSecond"
    assert [(loc.slide, result.text[loc.start : loc.end]) for loc in result.locations] == [
        (1, "First"),
        (2, "Second"),
    ]


def test_xlsx_names_coordinates_and_formula_warning():
    raw = archive(
        {
            "xl/workbook.xml": '<workbook xmlns:r="r"><sheets><sheet name="Costs" r:id="r1"/></sheets></workbook>',
            "xl/_rels/workbook.xml.rels": '<Relationships><Relationship Id="r1" Target="/xl/worksheets/sheet1.xml"/></Relationships>',
            "xl/sharedStrings.xml": "<sst><si><t>Price</t></si></sst>",
            "xl/worksheets/sheet1.xml": '<worksheet><sheetData><row><c r="A1" t="s"><v>0</v></c><c r="C1"><f>1+1</f><v>2</v></c></row></sheetData></worksheet>',
        }
    )
    result = parse(raw, "costs.xlsx")
    assert result.text == "A1=Price\tC1=2"
    assert result.locations[0].sheet == "Costs"
    assert result.partial
    assert "spreadsheet_formula_uses_cached_value_without_recalculation" in result.warnings


def make_pdf(text=True):
    from pypdf import PdfWriter
    from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject

    writer = PdfWriter()
    page = writer.add_blank_page(width=100, height=100)
    if text:
        font = DictionaryObject(
            {
                NameObject("/Type"): NameObject("/Font"),
                NameObject("/Subtype"): NameObject("/Type1"),
                NameObject("/BaseFont"): NameObject("/Helvetica"),
            }
        )
        page[NameObject("/Resources")] = DictionaryObject(
            {NameObject("/Font"): DictionaryObject({NameObject("/F1"): writer._add_object(font)})}
        )
        content = DecodedStreamObject()
        content.set_data(b"BT /F1 12 Tf 10 50 Td (Price 18000) Tj ET")
        page[NameObject("/Contents")] = writer._add_object(content)
    output = io.BytesIO()
    writer.write(output)
    return output.getvalue()


def test_pdf_text_and_page_coordinates():
    result = parse(make_pdf(), "notice.pdf")
    assert "Price 18000" in result.text
    assert result.locations[0].page == 1
    assert result.text[result.locations[0].start : result.locations[0].end] == result.text


def test_pdf_scan_requires_ocr():
    with pytest.raises(DomainError) as error:
        parse(make_pdf(False), "scan.pdf")
    assert error.value.code == "ocr_required"


async def test_backend_download_auth_provenance_and_isolated_parser():
    def handler(request):
        assert str(request.url) == "https://backend.test/api/files/file-1/content"
        assert request.headers["X-AI-Service-Key"] == "test-secret"
        assert request.headers["X-User-ID"] == "user-1"
        assert request.headers["Accept-Encoding"] == "identity"
        return httpx.Response(
            200,
            content=b"Price 18000",
            headers={
                "Content-Type": "text/plain; charset=utf-8",
                "Content-Disposition": "attachment; filename=notice.txt",
            },
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        result = await FileIngestor(client, config()).fetch("file-1", "user-1")
    assert result.text == "Price 18000"
    assert result.file_id == "file-1"
    assert result.media_type == "text/plain"
    assert "test-secret" not in repr(config())


@pytest.mark.parametrize(
    "file_id", ["../secret", "https://evil.test", "a/b", "a%2fb", ".", "a?x", "x\r\ny"]
)
async def test_unsafe_ids_never_make_network_request(file_id):
    def handler(request):
        pytest.fail("Must not access network")

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(DomainError) as error:
            await FileIngestor(client, config()).fetch(file_id, "user-1")
    assert error.value.code == "invalid_file_id"


@pytest.mark.parametrize(
    "status,extra,code",
    [
        (302, {"Location": "https://evil.test"}, "backend_file_error"),
        (401, {}, "backend_file_forbidden"),
        (404, {}, "backend_file_not_found"),
        (200, {"Content-Length": "9999"}, "file_too_large"),
        (200, {"Content-Encoding": "br"}, "backend_content_encoding"),
    ],
)
async def test_backend_failures_do_not_leak_content(status, extra, code):
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(
            status,
            content=b"secret backend body",
            headers={"Content-Disposition": "attachment; filename=a.txt", **extra},
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(DomainError) as error:
            await FileIngestor(client, config(), ExtractionLimits(max_bytes=100)).fetch(
                "id", "owner"
            )
    assert len(calls) == 1
    assert error.value.code == code
    assert "secret" not in str(error.value)


class Chunks(httpx.AsyncByteStream):
    async def __aiter__(self):
        yield b"a" * 50
        yield b"b" * 51


async def test_chunked_response_limit_without_content_length():
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(
            lambda request: httpx.Response(
                200, stream=Chunks(), headers={"Content-Disposition": "attachment; filename=a.txt"}
            )
        )
    ) as client:
        with pytest.raises(DomainError) as error:
            await FileIngestor(client, config(), ExtractionLimits(max_bytes=100)).fetch(
                "id", "owner"
            )
    assert error.value.code == "file_too_large"


async def test_total_download_deadline():
    async def handler(request):
        await asyncio.sleep(0.1)
        return httpx.Response(200, content=b"a")

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(DomainError) as error:
            await FileIngestor(client, config(timeout_seconds=0.01)).fetch("id", "owner")
    assert error.value.code == "backend_file_timeout"


async def test_isolated_parser_maps_malformed_xml_and_enforces_walltime():
    raw = archive({"word/document.xml": "<invalid>"})
    async with httpx.AsyncClient() as client:
        with pytest.raises(DomainError) as error:
            await FileIngestor(client).parse(raw, "broken.docx")
        assert error.value.code == "invalid_document"
        with pytest.raises(DomainError) as error:
            await FileIngestor(client, limits=ExtractionLimits(timeout_seconds=0.001)).parse(
                b"text", "a.txt"
            )
        assert error.value.code == "extraction_timeout"


@pytest.mark.parametrize(
    "url",
    ["http://backend.test", "https://x.test/path", "https://a:b@x.test", "https://x.test?url=evil"],
)
def test_unsafe_backend_configuration(url):
    with pytest.raises(ValueError):
        FileBackendConfig(url, SecretStr("key"))


def test_internal_http_requires_explicit_configuration():
    assert FileBackendConfig("http://backend:8000", SecretStr("key"), allow_http=True)
    with pytest.raises(ValueError):
        config(content_path="//evil.test/{file_id}")


def test_ocr_empty_output_is_not_success(monkeypatch):
    import app.infrastructure.files.extractors as extractors

    monkeypatch.setattr(extractors.shutil, "which", lambda _: "/usr/bin/tesseract")
    monkeypatch.setattr(extractors, "command", lambda *_: b"  \n")
    with pytest.raises(DomainError) as error:
        parse(b"image", "a.png", ocr_enabled=True)
    assert error.value.code == "ocr_empty_text"


def test_ocr_provenance_and_tiff_coordinates(monkeypatch):
    import app.infrastructure.files.extractors as extractors

    monkeypatch.setattr(extractors.shutil, "which", lambda _: "/usr/bin/tesseract")
    monkeypatch.setattr(extractors, "command", lambda *_: b"Recognized text")
    result = parse(b"image", "a.tiff", ocr_enabled=True)
    assert result.text == "Recognized text"
    assert result.partial
    assert result.extractor == "tesseract"
    assert not result.locations
    assert "tiff_frame_coordinates_unavailable" in result.warnings


async def test_cancelled_parser_holds_slot_until_worker_exits(monkeypatch):
    import threading

    import app.infrastructure.files.client as ingestion

    entered = threading.Event()
    release = threading.Event()

    def worker(*args):
        entered.set()
        release.wait(timeout=2)
        return parse(b"text", "a.txt")

    monkeypatch.setattr(ingestion, "parse_isolated", worker)
    async with httpx.AsyncClient() as client:
        loader = FileIngestor(client)
        task = asyncio.create_task(loader.parse(b"text", "a.txt"))
        while not entered.is_set():
            await asyncio.sleep(0.001)
        task.cancel()
        await asyncio.sleep(0)
        task.cancel()  # Repeated cancellation must not release the concurrency slot.
        await asyncio.sleep(0)
        assert loader._slots.locked()
        release.set()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert not loader._slots.locked()
