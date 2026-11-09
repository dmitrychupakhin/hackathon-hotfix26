import hashlib

from app.config import Settings
from app.domain import Document, DomainError, Package, Span, TextDocument


def decode_text(raw: bytes) -> tuple[str, str]:
    if b"\x00" in raw:
        raise DomainError(
            "unsupported_encoding",
            "Binary or UTF-16 input is not supported; provide UTF-8 or CP1251 text",
            422,
        )
    for encoding in ("utf-8-sig", "cp1251"):
        try:
            return raw.decode(encoding), "utf-8" if encoding == "utf-8-sig" else encoding
        except UnicodeDecodeError:
            continue
    raise DomainError("unsupported_encoding", "Could not decode text without data loss", 422)


def document_from_text(item: TextDocument, settings: Settings, encoding="utf-8") -> Document:
    raw = item.text.encode("utf-8")
    if len(raw) > settings.max_upload_bytes:
        raise DomainError("file_too_large", "Document exceeds the configured size limit", 413)
    if "\x00" in item.text:
        raise DomainError("binary_input", "Text contains a NUL byte", 422)
    return Document(
        name=item.name,
        text=item.text,
        sha256=hashlib.sha256(raw).hexdigest(),
        encoding=encoding,
        warning="empty_document" if not item.text.strip() else None,
    )


def with_documents(package: Package, additions: list[Document], settings: Settings) -> Package:
    names = [d.name for d in package.documents + additions]
    if len(set(names)) != len(names):
        raise DomainError(
            "duplicate_filename", "Document names within a package must be unique", 409
        )
    if (
        len(names) > 64
        or sum(len(d.text.encode()) for d in package.documents + additions)
        > settings.max_package_bytes
    ):
        raise DomainError("package_too_large", "Package exceeds document count or size limit", 413)
    package = package.model_copy(deep=True)
    package.documents.extend(additions)
    manifest = "\n".join(
        f"{d.id}:{d.name}:{d.sha256}" for d in sorted(package.documents, key=lambda d: d.id)
    )
    package.revision = hashlib.sha256(manifest.encode()).hexdigest()
    return package


# Missing Word page layout does not imply missing text. Every other warning is
# conservatively treated as a possible content loss until explicitly classified.
INFORMATIONAL_TEXT_WARNINGS = frozenset({"docx_page_layout_unavailable"})


def document_text_complete(document: Document) -> bool:
    warnings = {item.strip() for item in (document.warning or "").split(";") if item.strip()}
    return (
        bool(document.text.strip())
        and not document.partial
        and warnings <= INFORMATIONAL_TEXT_WARNINGS
    )


def spans_for(
    package: Package, target_chars=None, *, target_tokens=2000, overlap_tokens=200
) -> dict[str, Span]:
    """Stable original-source spans. Explicit legacy target_chars remains accepted."""
    from app.services.chunking import split_text

    if target_chars is not None:
        target_tokens = max(16, target_chars // 2)
        overlap_tokens = min(overlap_tokens, max(0, target_tokens // 10))
    spans = {}
    for doc in package.documents:
        for chunk in split_text(
            doc.text, target_tokens=target_tokens, overlap_tokens=overlap_tokens
        ):
            key = hashlib.sha256(
                f"{doc.id}:{doc.sha256}:{chunk.start}:{chunk.end}".encode()
            ).hexdigest()[:24]
            spans[key] = Span(
                id=key,
                document_id=doc.id,
                file=doc.original_name or doc.name,
                source_hash=doc.sha256,
                source_file_id=doc.source_file_id,
                source_version=doc.source_version,
                original_sha256=doc.original_sha256,
                start=chunk.start,
                end=chunk.end,
                text=chunk.text,
                locations=[
                    location
                    for location in doc.locations
                    if isinstance(location.get("start"), int)
                    and isinstance(location.get("end"), int)
                    and location["start"] < chunk.end
                    and location["end"] > chunk.start
                ],
            )
    return spans
