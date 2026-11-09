"""Configuration and provenance for backend document ingestion."""

import math
import re
from dataclasses import dataclass, field
from urllib.parse import urlsplit

from pydantic import BaseModel, Field, SecretStr

from app.domain import DomainError


class SourceLocation(BaseModel):
    start: int
    end: int
    page: int | None = None
    sheet: str | None = None
    slide: int | None = None


class ParsedFile(BaseModel):
    name: str
    text: str
    file_id: str | None = None
    media_type: str
    original_sha256: str
    extractor: str
    warnings: list[str] = Field(default_factory=list)
    partial: bool = False
    locations: list[SourceLocation] = Field(default_factory=list)


@dataclass(frozen=True)
class ExtractionLimits:
    max_bytes: int = 10 * 1024 * 1024
    max_text_chars: int = 2_000_000
    max_archive_bytes: int = 64 * 1024 * 1024
    max_archive_entries: int = 2000
    max_pages: int = 200
    timeout_seconds: float = 45
    memory_mb: int = 512
    ocr_enabled: bool = False
    ocr_language: str = "rus+eng"

    def __post_init__(self):
        for name in (
            "max_bytes",
            "max_text_chars",
            "max_archive_bytes",
            "max_archive_entries",
            "max_pages",
            "timeout_seconds",
            "memory_mb",
        ):
            if not math.isfinite(getattr(self, name)) or getattr(self, name) <= 0:
                raise ValueError(f"{name} must be positive")
        if not re.fullmatch(r"[a-zA-Z0-9_+.-]{1,64}", self.ocr_language):
            raise ValueError("Invalid OCR language")


@dataclass(frozen=True)
class FileBackendConfig:
    base_url: str
    service_key: SecretStr = field(repr=False)
    content_path: str = "/api/files/{file_id}/content"
    timeout_seconds: float = 20
    allow_http: bool = False

    def __post_init__(self):
        parsed = urlsplit(self.base_url)
        if (
            parsed.scheme not in ({"https", "http"} if self.allow_http else {"https"})
            or not parsed.hostname
            or parsed.username
            or parsed.password
            or parsed.query
            or parsed.fragment
            or parsed.path not in {"", "/"}
        ):
            raise ValueError("Backend URL must be an explicit HTTP(S) origin without credentials")
        if (
            not self.content_path.startswith("/")
            or self.content_path.startswith("//")
            or self.content_path.count("{file_id}") != 1
            or not re.fullmatch(r"/[a-zA-Z0-9_/{.}-]+", self.content_path)
            or ".." in self.content_path
            or "{" in self.content_path.replace("{file_id}", "")
            or "}" in self.content_path.replace("{file_id}", "")
        ):
            raise ValueError("Content path must contain exactly one {file_id} placeholder")
        secret = self.service_key.get_secret_value()
        if not secret or any(ord(c) < 32 or ord(c) > 126 for c in secret):
            raise ValueError("Backend service key must be nonempty printable ASCII")
        if not math.isfinite(self.timeout_seconds) or self.timeout_seconds <= 0:
            raise ValueError("Backend timeout must be positive")


def validate_file_id(file_id: str) -> str:
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,127}", file_id):
        raise DomainError("invalid_file_id", "File ID must be an opaque alphanumeric ID", 422)
    return file_id


def validate_name(name: str) -> str:
    if (
        not name
        or len(name) > 200
        or name in {".", ".."}
        or any(c in name for c in "/\\")
        or any(ord(c) < 32 for c in name)
    ):
        raise DomainError(
            "invalid_filename", "Expected a plain filename of up to 200 characters", 422
        )
    return name
