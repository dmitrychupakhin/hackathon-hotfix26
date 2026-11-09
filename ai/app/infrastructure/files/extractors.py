"""Bounded text extraction. No office macros, external links, or shell execution."""

import hashlib
import io
import json
import re
import shutil
import subprocess
import tempfile
import zipfile
from html.parser import HTMLParser
from pathlib import Path

from defusedxml import ElementTree

from app.domain import DomainError
from app.infrastructure.files.models import (
    ExtractionLimits,
    ParsedFile,
    SourceLocation,
    validate_name,
)

TEXT_EXTENSIONS = {".txt", ".md", ".csv", ".json", ".html", ".htm"}
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp", ".webp"}


class TextHTML(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.hidden = 0
        self.parts = []

    def handle_starttag(self, tag, attrs):
        if tag in {"script", "style", "noscript", "template"}:
            self.hidden += 1
        elif not self.hidden and tag in {"p", "div", "br", "li", "tr", "h1", "h2", "h3"}:
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag in {"script", "style", "noscript", "template"}:
            self.hidden = max(0, self.hidden - 1)

    def handle_data(self, data):
        if not self.hidden:
            self.parts.append(data)


def decode(raw):
    encodings = ["utf-8-sig", "cp1251"]
    if raw.startswith((b"\xff\xfe", b"\xfe\xff")):
        encodings = ["utf-16"]
    for encoding in encodings:
        try:
            text = raw.decode(encoding)
        except UnicodeDecodeError:
            continue
        if any(ord(c) < 32 and c not in "\n\r\t\f" for c in text):
            raise DomainError("binary_input", "Input contains binary control characters", 422)
        return text, encoding
    raise DomainError("unsupported_encoding", "Cannot decode text without data loss", 422)


class Builder:
    def __init__(self, limits):
        self.limits = limits
        self.parts = []
        self.locations = []
        self.length = 0
        self.warnings = []
        self.partial = False

    def add(self, text, **location):
        if self.length + len(text) + bool(self.parts) > self.limits.max_text_chars:
            raise DomainError(
                "extracted_text_too_large",
                "Extracted text exceeds limit; no truncated text is accepted",
                413,
            )
        if self.parts:
            self.parts.append("\n")
            self.length += 1
        start = self.length
        self.parts.append(text)
        self.length += len(text)
        if location:
            self.locations.append(SourceLocation(start=start, end=self.length, **location))

    def warn(self, warning):
        if warning not in self.warnings:
            self.warnings.append(warning)
        self.partial = True


def xml(archive, name):
    return ElementTree.fromstring(archive.read(name))


def local(tag):
    return tag.rsplit("}", 1)[-1]


def paragraphs(root):
    result = []
    for node in root.iter():
        if local(node.tag) == "p":
            result.append(
                "".join(
                    child.text or ""
                    if local(child.tag) == "t"
                    else "\t"
                    if local(child.tag) == "tab"
                    else "\n"
                    for child in node.iter()
                    if local(child.tag) in {"t", "tab", "br"}
                )
            )
    return "\n".join(result)


def office(raw, extension, out):
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        entries = archive.infolist()
        names = archive.namelist()
        if (
            len(entries) > out.limits.max_archive_entries
            or sum(e.file_size for e in entries) > out.limits.max_archive_bytes
            or len(names) != len(set(names))
            or any(e.flag_bits & 1 for e in entries)
        ):
            raise DomainError(
                "unsafe_archive",
                "Archive is encrypted, duplicated, or exceeds expansion limits",
                422,
            )
        if any("vbaProject" in name for name in names):
            raise DomainError(
                "unsupported_format", "Macro-enabled Office documents are not supported", 422
            )
        if any("/media/" in name or "/embeddings/" in name or "/charts/" in name for name in names):
            out.warn("embedded_images_charts_or_objects_not_extracted")
        if extension == ".docx":
            root = xml(archive, "word/document.xml")
            out.add(paragraphs(root))
            # Explicitly acknowledge all secondary stories; no invented page coordinates.
            for name in sorted(names):
                if re.fullmatch(
                    r"word/(?:header\d+|footer\d+|footnotes|endnotes|comments)\.xml", name
                ):
                    out.add(paragraphs(xml(archive, name)))
            if any(
                local(node.tag) in {"altChunk", "drawing", "object", "pict"} for node in root.iter()
            ):
                out.warn("docx_nonparagraph_content_not_extracted")
            out.warnings.append("docx_page_layout_unavailable")
        elif extension == ".pptx":
            # Presentation relationship order, not slide filename order.
            rels = {
                node.attrib["Id"]: node.attrib.get("Target", "")
                for node in xml(archive, "ppt/_rels/presentation.xml.rels")
            }
            slides = [
                n for n in xml(archive, "ppt/presentation.xml").iter() if local(n.tag) == "sldId"
            ]
            if len(slides) > out.limits.max_pages:
                raise DomainError("too_many_pages", "Presentation exceeds slide limit", 413)
            for number, slide in enumerate(slides, 1):
                rel_id = next(v for k, v in slide.attrib.items() if local(k) == "id" and "}" in k)
                target = rels[rel_id]
                if not re.fullmatch(r"slides/slide\d+\.xml", target):
                    raise DomainError("invalid_document", "Unsupported slide relationship", 422)
                out.add(paragraphs(xml(archive, "ppt/" + target)), slide=number)
            if any(
                name.startswith("ppt/notesSlides/notesSlide") and name.endswith(".xml")
                for name in names
            ):
                out.warn("presentation_speaker_notes_not_extracted")
        else:
            shared = []
            if "xl/sharedStrings.xml" in names:
                shared = [
                    "".join(n.text or "" for n in item.iter() if local(n.tag) == "t")
                    for item in xml(archive, "xl/sharedStrings.xml")
                ]
            rels = {
                node.attrib["Id"]: node.attrib.get("Target", "")
                for node in xml(archive, "xl/_rels/workbook.xml.rels")
            }
            sheets = [
                node
                for node in xml(archive, "xl/workbook.xml").iter()
                if local(node.tag) == "sheet"
            ]
            if len(sheets) > out.limits.max_pages:
                raise DomainError("too_many_pages", "Workbook exceeds sheet limit", 413)
            for sheet in sheets:
                rid = next(v for k, v in sheet.attrib.items() if local(k) == "id")
                target = rels[rid].removeprefix("/xl/")
                if not re.fullmatch(r"worksheets/sheet\d+\.xml", target):
                    raise DomainError("invalid_document", "Unsupported worksheet relationship", 422)
                root = xml(archive, "xl/" + target)
                rows = []
                for row in root.iter():
                    if local(row.tag) != "row":
                        continue
                    cells = []
                    for cell in row:
                        if local(cell.tag) != "c":
                            continue
                        value = next((n.text or "" for n in cell if local(n.tag) == "v"), "")
                        kind = cell.attrib.get("t")
                        if kind == "s":
                            index = int(value)
                            if not 0 <= index < len(shared):
                                raise DomainError(
                                    "invalid_document", "Invalid shared-string reference", 422
                                )
                            value = shared[index]
                        elif kind == "inlineStr":
                            value = "".join(
                                n.text or "" for n in cell.iter() if local(n.tag) == "t"
                            )
                        if any(local(n.tag) == "f" for n in cell):
                            out.warn("spreadsheet_formula_uses_cached_value_without_recalculation")
                            if not value:
                                value = "[formula: cached value unavailable]"
                        cells.append(f"{cell.attrib.get('r', '?')}={value}")
                    rows.append("\t".join(cells))
                out.add("\n".join(rows), sheet=sheet.attrib["name"])
            out.warn("spreadsheet_values_are_raw_without_display_number_formats")


def command(args, timeout):
    try:
        result = subprocess.run(args, capture_output=True, timeout=timeout, check=False)
    except (subprocess.TimeoutExpired, OSError):
        raise DomainError("ocr_failed", "OCR tool failed or timed out", 422) from None
    if result.returncode:
        raise DomainError(
            "ocr_failed", "OCR failed; verify installed language data and input format", 422
        )
    return result.stdout


def ocr(path, out):
    if not out.limits.ocr_enabled or not shutil.which("tesseract"):
        raise DomainError(
            "ocr_unavailable",
            "OCR requires explicit enablement and installed Tesseract with language data",
            422,
        )
    result = command(
        [
            "tesseract",
            str(path),
            "stdout",
            "-l",
            out.limits.ocr_language,
        ],
        out.limits.timeout_seconds,
    )
    text = result.decode("utf-8")
    if not text.strip():
        raise DomainError("ocr_empty_text", "OCR produced no readable text", 422)
    out.warn("ocr_text_requires_verification")
    return text


def pdf(raw, out):
    try:
        from pypdf import PdfReader
    except ImportError:
        raise DomainError("extractor_unavailable", "PDF extraction requires pypdf", 503) from None
    reader = PdfReader(io.BytesIO(raw), strict=True)
    if reader.is_encrypted:
        raise DomainError("encrypted_file", "Encrypted PDFs are not accepted", 422)
    if len(reader.pages) > out.limits.max_pages:
        raise DomainError("too_many_pages", "PDF exceeds page limit", 413)
    with tempfile.TemporaryDirectory(prefix="ai-pdf-") as tmp:
        for number, page in enumerate(reader.pages, 1):
            text = page.extract_text() or ""
            if not text.strip():
                if not out.limits.ocr_enabled:
                    out.warn(f"page_{number}_has_no_text_layer_ocr_required")
                else:
                    if not shutil.which("pdftoppm"):
                        raise DomainError(
                            "ocr_unavailable", "Scanned PDF OCR requires pdftoppm", 422
                        )
                    source = Path(tmp) / "source.pdf"
                    source.write_bytes(raw)
                    prefix = Path(tmp) / "page"
                    command(
                        [
                            "pdftoppm",
                            "-f",
                            str(number),
                            "-l",
                            str(number),
                            "-singlefile",
                            "-scale-to",
                            "2400",
                            "-png",
                            str(source),
                            str(prefix),
                        ],
                        out.limits.timeout_seconds,
                    )
                    text = ocr(prefix.with_suffix(".png"), out)
            elif page.get("/Resources") and "/XObject" in page["/Resources"]:
                out.warn(f"page_{number}_embedded_graphics_not_ocr_processed")
            out.add(text, page=number)
    if not any(part.strip() for part in out.parts):
        raise DomainError(
            "ocr_required", "PDF has no extractable text; enable OCR and install its tools", 422
        )


def extract(raw: bytes, name: str, media_type: str, file_id: str | None, limits: ExtractionLimits):
    validate_name(name)
    if len(raw) > limits.max_bytes:
        raise DomainError("file_too_large", "File exceeds configured byte limit", 413)
    extension = Path(name).suffix.lower()
    out = Builder(limits)
    extractor = extension.lstrip(".")
    if extension in TEXT_EXTENSIONS:
        text, encoding = decode(raw)
        extractor = f"text:{encoding}"
        if encoding == "cp1251":
            out.warnings.append("encoding_assumed_cp1251")
        if extension == ".json":
            json.loads(text)
        if extension in {".html", ".htm"}:
            parser = TextHTML()
            parser.feed(text)
            text = "".join(parser.parts)
            extractor = "html:visible_text"
            out.warn("html_scripts_styles_images_and_layout_not_extracted")
        out.add(text)
    elif extension == ".pdf" and raw.startswith(b"%PDF-"):
        pdf(raw, out)
        extractor = (
            "pypdf+ocr"
            if any(w == "ocr_text_requires_verification" for w in out.warnings)
            else "pypdf"
        )
    elif extension in {".docx", ".pptx", ".xlsx"} and raw.startswith(b"PK"):
        office(raw, extension, out)
        extractor = f"ooxml:{extension[1:]}"
    elif extension in IMAGE_EXTENSIONS:
        # Tesseract validates image bytes; no file paths or command flags come from the filename.
        with tempfile.TemporaryDirectory(prefix="ai-ocr-") as tmp:
            path = Path(tmp) / ("image" + extension)
            path.write_bytes(raw)
            text = ocr(path, out)
            if extension in {".tif", ".tiff"}:
                out.warn("tiff_frame_coordinates_unavailable")
                out.add(text)
            else:
                out.add(text, page=1)
        extractor = "tesseract"
    elif extension in {".doc", ".xls", ".ppt", ".odt", ".ods", ".odp", ".rtf"}:
        raise DomainError(
            "legacy_format_unavailable",
            "Convert this document to PDF or OOXML before ingestion",
            422,
        )
    else:
        raise DomainError(
            "unsupported_format", "Unsupported format or file signature mismatch", 422
        )
    text = "".join(out.parts)
    if not text.strip():
        out.warn("empty_document")
    return ParsedFile(
        name=name,
        text=text,
        file_id=file_id,
        media_type=media_type,
        original_sha256=hashlib.sha256(raw).hexdigest(),
        extractor=extractor,
        warnings=out.warnings,
        partial=out.partial,
        locations=out.locations,
    )
