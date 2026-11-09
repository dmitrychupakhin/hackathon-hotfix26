"""Shared-volume file metadata and local extraction artifacts."""

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.infrastructure.files.models import ParsedFile


class SourceFile(BaseModel):
    """An immutable backend-owned source revision, resolved only after owner checks."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str = Field(min_length=1, max_length=128, pattern=r"^[A-Za-z0-9][A-Za-z0-9_-]*$")
    owner: str = Field(min_length=1, max_length=200)
    version: str = Field(min_length=1, max_length=128)
    updated_at: datetime
    filename: str = Field(min_length=1, max_length=200)
    relative_path: str = Field(min_length=1, max_length=2000)
    sha256: str = Field(pattern=r"^[a-fA-F0-9]{64}$")
    media_type: str = Field(default="application/octet-stream", max_length=200)

    @field_validator("id", "owner", "version", "media_type")
    @classmethod
    def printable(cls, value: str) -> str:
        if not value.strip() or any(ord(char) < 32 or ord(char) == 127 for char in value):
            raise ValueError("Expected nonempty metadata without control characters")
        return value

    @field_validator("updated_at")
    @classmethod
    def aware_utc(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("updated_at must contain a timezone")
        return value.astimezone(timezone.utc)

    @field_validator("filename")
    @classmethod
    def plain_filename(cls, value: str) -> str:
        if (
            value in {".", ".."}
            or any(c in value for c in "/\\")
            or any(ord(c) < 32 or ord(c) == 127 for c in value)
        ):
            raise ValueError("Expected a plain filename")
        return value

    @field_validator("relative_path")
    @classmethod
    def relative_local_path(cls, value: str) -> str:
        if (
            "\\" in value
            or PurePosixPath(value).is_absolute()
            or any(part in {"", ".", ".."} for part in value.split("/"))
            or any(ord(c) < 32 or ord(c) == 127 for c in value)
        ):
            raise ValueError("Expected a normalized relative POSIX path")
        return value

    @field_validator("sha256")
    @classmethod
    def lowercase_hash(cls, value: str) -> str:
        return value.lower()


@dataclass(frozen=True)
class CachedArtifact:
    parsed: ParsedFile
    cache_hit: bool
    artifact_key: str
    text_path: Path
