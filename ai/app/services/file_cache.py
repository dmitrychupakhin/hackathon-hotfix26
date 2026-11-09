"""Immutable, owner-scoped TXT artifacts beside local original copies.

The backend source volume is read-only. Metadata comes from the authenticated
shared database, never from a model/tool argument. POSIX no-follow opens reject
symlink escapes even if a source path changes during traversal.
"""

import asyncio
import errno
import fcntl
import hashlib
import json
import os
import re
import shutil
import stat
import tempfile
from dataclasses import asdict
from datetime import datetime, timezone
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from uuid import uuid4

from pydantic import ValidationError

from app.domain import DomainError
from app.infrastructure.files import FileIngestor, ParsedFile
from app.infrastructure.files.cache_models import CachedArtifact, SourceFile

CACHE_FORMAT_VERSION = 1


def _digest(value: str | bytes) -> str:
    return hashlib.sha256(value.encode() if isinstance(value, str) else value).hexdigest()


def _json(value: object) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True).encode("utf-8")


class FileCache:
    def __init__(
        self,
        source_root: Path,
        cache_root: Path,
        ingestor: FileIngestor,
        max_bytes: int = 10 * 1024 * 1024,
    ):
        self.source_root = Path(source_root).resolve(strict=True)
        if not self.source_root.is_dir():
            raise ValueError("source_root must be a directory")
        self.cache_root = Path(cache_root)
        self.cache_root.mkdir(parents=True, exist_ok=True, mode=0o700)
        if self.cache_root.is_symlink():
            raise ValueError("cache_root must not be a symlink")
        self.cache_root = self.cache_root.resolve(strict=True)
        if max_bytes <= 0:
            raise ValueError("max_bytes must be positive")
        self.max_bytes = min(max_bytes, ingestor.limits.max_bytes)
        self.ingestor = ingestor
        self.parser_fingerprint = self._fingerprint()

    def _fingerprint(self) -> str:
        dependencies = {}
        for name in ("pypdf", "defusedxml"):
            try:
                dependencies[name] = version(name)
            except PackageNotFoundError:
                dependencies[name] = "missing"
        parser_dir = Path(__file__).resolve().parents[1] / "infrastructure" / "files"
        code = {p.name: _digest(p.read_bytes()) for p in sorted(parser_dir.glob("*.py"))}
        return _digest(
            _json(
                {
                    "format": CACHE_FORMAT_VERSION,
                    "limits": asdict(self.ingestor.limits),
                    "dependencies": dependencies,
                    "code": code,
                }
            )
        )

    def _artifact_parts(self, source: SourceFile) -> list[str]:
        # IDs and revision strings are database values, not filesystem components.
        # The digest also prevents collisions across equal revision labels/content.
        revision = _digest(
            _json(
                {
                    "version": source.version,
                    "sha256": source.sha256,
                    "filename": source.filename,
                    "media_type": source.media_type,
                }
            )
        )
        return [_digest(source.owner), _digest(source.id), revision, self.parser_fingerprint]

    def _safe_cache_parent(self, parts: list[str]) -> Path:
        current = self.cache_root
        for part in parts:
            current = current / part
            try:
                current.mkdir(mode=0o700)
            except FileExistsError:
                pass
            if current.is_symlink() or not current.is_dir():
                raise DomainError("unsafe_cache_path", "Cache directory is not safe", 503)
        return current

    def _read_source(self, source: SourceFile) -> bytes:
        directory_fd = os.open(self.source_root, os.O_RDONLY | os.O_DIRECTORY)
        file_fd = None
        try:
            parts = source.relative_path.split("/")
            for part in parts[:-1]:
                child_fd = os.open(
                    part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=directory_fd
                )
                os.close(directory_fd)
                directory_fd = child_fd
            file_fd = os.open(
                parts[-1], os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory_fd
            )
            before = os.fstat(file_fd)
            if not stat.S_ISREG(before.st_mode):
                raise DomainError("invalid_source_file", "Source must be a regular file", 422)
            if before.st_size > self.max_bytes:
                raise DomainError("file_too_large", "Source exceeds the configured byte limit", 413)
            chunks = []
            size = 0
            while chunk := os.read(file_fd, min(65536, self.max_bytes + 1 - size)):
                size += len(chunk)
                if size > self.max_bytes:
                    raise DomainError("file_too_large", "Source exceeds the byte limit", 413)
                chunks.append(chunk)
            after = os.fstat(file_fd)
            if (before.st_size, before.st_mtime_ns, before.st_ctime_ns) != (
                after.st_size,
                after.st_mtime_ns,
                after.st_ctime_ns,
            ):
                raise DomainError("source_changed", "Source changed while being read", 409)
            raw = b"".join(chunks)
            if _digest(raw) != source.sha256:
                raise DomainError("source_changed", "Source SHA-256 does not match metadata", 409)
            return raw
        except FileNotFoundError:
            raise DomainError("source_file_not_found", "Source file was not found", 404) from None
        except OSError as exc:
            if exc.errno in {errno.ELOOP, errno.ENOTDIR}:
                raise DomainError(
                    "unsafe_source_path", "Source symlinks are not allowed", 422
                ) from None
            raise DomainError(
                "source_file_unavailable", "Source file cannot be read", 503
            ) from None
        finally:
            if file_fd is not None:
                os.close(file_fd)
            os.close(directory_fd)

    def _read_cached(self, artifact: Path, source: SourceFile) -> ParsedFile | None:
        if not artifact.exists() and not artifact.is_symlink():
            return None
        try:
            if artifact.is_symlink() or not artifact.is_dir():
                raise ValueError("Unsafe artifact")
            contents = {}
            for name in ("metadata.json", "extracted.txt"):
                path = artifact / name
                fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
                with os.fdopen(fd, "rb") as stream:
                    if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode):
                        raise ValueError("Nonregular cache file")
                    limit = (
                        4 * self.ingestor.limits.max_text_chars + 4
                        if name == "extracted.txt"
                        else 16 * 1024 * 1024
                    )
                    contents[name] = stream.read(limit + 1)
                    if len(contents[name]) > limit:
                        raise ValueError("Oversized artifact")
            metadata = json.loads(contents["metadata.json"])
            if (
                metadata["format"] != CACHE_FORMAT_VERSION
                or metadata["parser_fingerprint"] != self.parser_fingerprint
                or metadata["source"]["owner"] != source.owner
                or metadata["source"]["id"] != source.id
                or metadata["source"]["version"] != source.version
                or metadata["source"]["sha256"] != source.sha256
                or metadata["source"]["filename"] != source.filename
                or metadata["source"]["media_type"] != source.media_type
                or metadata["text_sha256"] != _digest(contents["extracted.txt"])
            ):
                raise ValueError("Artifact provenance mismatch")
            parsed = ParsedFile.model_validate(
                {**metadata["parsed"], "text": contents["extracted.txt"].decode("utf-8")}
            )
            if parsed.original_sha256 != source.sha256 or parsed.file_id != source.id:
                raise ValueError("Parser provenance mismatch")
            return parsed
        except FileNotFoundError:
            # Interrupted/incomplete publication is rebuilt under the same lock.
            return None
        except (OSError, ValueError, KeyError, TypeError):
            # Never silently trust broken provenance or delete an unexpected artifact.
            raise DomainError("file_cache_corrupt", "Cached extraction is corrupt", 503) from None

    async def prepare(self, source: SourceFile, owner_id: str) -> CachedArtifact:
        if source.owner != owner_id:
            raise DomainError("source_file_not_found", "Source file was not found", 404)
        raw = await asyncio.to_thread(self._read_source, source)
        return await self._prepare_raw(source, raw)

    async def prepare_bytes(
        self,
        raw: bytes,
        name: str,
        owner_id: str,
        media_type: str = "application/octet-stream",
        file_id: str | None = None,
    ) -> CachedArtifact:
        if len(raw) > self.max_bytes:
            raise DomainError("file_too_large", "Upload exceeds the byte limit", 413)
        sha = _digest(raw)
        try:
            source = SourceFile(
                id=file_id or str(uuid4()),
                owner=owner_id,
                version=sha,
                updated_at=datetime.now(timezone.utc),
                filename=name,
                relative_path="uploads/content",
                sha256=sha,
                media_type=media_type,
            )
        except ValidationError as exc:
            filename_invalid = any(error["loc"] == ("filename",) for error in exc.errors())
            raise DomainError(
                "invalid_filename" if filename_invalid else "invalid_source_metadata",
                "Expected a plain filename of up to 200 characters"
                if filename_invalid
                else "Upload metadata is invalid",
                422,
            ) from None
        return await self._prepare_raw(source, raw)

    async def _prepare_raw(self, source: SourceFile, raw: bytes) -> CachedArtifact:
        parts = self._artifact_parts(source)
        parent = self._safe_cache_parent(parts[:-1])
        artifact = parent / parts[-1]
        artifact_key = "/".join(parts)
        try:
            lock_fd = os.open(
                parent / (parts[-1] + ".lock"), os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600
            )
            if not stat.S_ISREG(os.fstat(lock_fd).st_mode):
                os.close(lock_fd)
                raise DomainError("unsafe_cache_path", "Cache lock is not a regular file", 503)
        except OSError:
            raise DomainError(
                "unsafe_cache_path", "Cache lock cannot be opened safely", 503
            ) from None
        try:
            while True:
                try:
                    fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    break
                except BlockingIOError:
                    await asyncio.sleep(0.025)
            cached = await asyncio.to_thread(self._read_cached, artifact, source)
            if cached is not None:
                return CachedArtifact(cached, True, artifact_key, artifact / "extracted.txt")
            parsed = await self.ingestor.parse(
                raw, source.filename, source.media_type, file_id=source.id
            )
            if parsed.original_sha256 != source.sha256 or parsed.file_id != source.id:
                raise DomainError(
                    "parser_provenance_error", "Parser returned invalid provenance", 503
                )
            if artifact.exists():
                if artifact.is_symlink() or not artifact.is_dir():
                    raise DomainError("unsafe_cache_path", "Cache artifact is not safe", 503)
                # Keep incomplete entries for inspection; never overwrite them in place.
                artifact.rename(parent / (".incomplete-" + str(uuid4())))
            temporary = Path(tempfile.mkdtemp(prefix=".extract-", dir=parent))
            try:
                suffix = Path(source.filename).suffix.lower()
                if not re.fullmatch(r"\.[a-z0-9]{1,12}", suffix):
                    suffix = ".bin"
                original_name = "original" + suffix
                (temporary / original_name).write_bytes(raw)
                text = parsed.text.encode("utf-8")
                (temporary / "extracted.txt").write_bytes(text)
                metadata = {
                    "format": CACHE_FORMAT_VERSION,
                    "generated_at": datetime.now(timezone.utc).isoformat(),
                    "source": source.model_dump(mode="json"),
                    "parser_fingerprint": self.parser_fingerprint,
                    "original_name": original_name,
                    "text_sha256": _digest(text),
                    "parsed": parsed.model_dump(exclude={"text"}),
                }
                (temporary / "metadata.json").write_bytes(_json(metadata))
                # All readers observe either no artifact or a complete immutable directory.
                temporary.rename(artifact)
            finally:
                if temporary.exists():
                    shutil.rmtree(temporary)
            return CachedArtifact(parsed, False, artifact_key, artifact / "extracted.txt")
        finally:
            fcntl.flock(lock_fd, fcntl.LOCK_UN)
            os.close(lock_fd)
