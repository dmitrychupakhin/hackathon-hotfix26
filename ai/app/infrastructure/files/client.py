"""Fetch only configured backend content URLs; never follow returned URLs."""

import asyncio
from email.message import Message

import httpx

from app.domain import DomainError
from app.infrastructure.files.models import (
    ExtractionLimits,
    FileBackendConfig,
    ParsedFile,
    validate_file_id,
    validate_name,
)
from app.infrastructure.files.worker import parse_isolated


class FileIngestor:
    def __init__(
        self,
        client: httpx.AsyncClient,
        config: FileBackendConfig | None = None,
        limits: ExtractionLimits | None = None,
    ):
        self.client = client
        self.config = config
        self.limits = limits or ExtractionLimits()
        # One loader/parser at a time per service instance, including cancellation cleanup.
        self._slots = asyncio.Semaphore(1)

    async def fetch(self, file_id: str, owner_id: str) -> ParsedFile:
        validate_file_id(file_id)
        if (
            not owner_id
            or len(owner_id) > 200
            or any(ord(c) < 33 or ord(c) > 126 for c in owner_id)
        ):
            raise DomainError("invalid_owner", "Owner ID must be printable ASCII", 422)
        if self.config is None:
            raise DomainError(
                "backend_files_not_configured", "Backend file API is not configured", 503
            )
        async with self._slots:
            raw, name, media_type = await self._download(file_id, owner_id)
            return await self._parse(raw, name, media_type, file_id)

    async def parse(
        self,
        raw: bytes,
        name: str,
        media_type: str = "application/octet-stream",
        file_id: str | None = None,
    ) -> ParsedFile:
        if file_id is not None:
            validate_file_id(file_id)
        async with self._slots:
            return await self._parse(raw, name, media_type, file_id)

    async def _parse(self, raw, name, media_type, file_id):
        validate_name(name)
        if len(raw) > self.limits.max_bytes:
            raise DomainError("file_too_large", "File exceeds the configured byte limit", 413)
        task = asyncio.create_task(
            asyncio.to_thread(
                parse_isolated,
                raw,
                name,
                media_type,
                file_id,
                self.limits,
            )
        )
        try:
            return await asyncio.shield(task)
        except asyncio.CancelledError:
            # Do not release the semaphore while a worker is still consuming resources.
            while not task.done():
                try:
                    await asyncio.shield(task)
                except asyncio.CancelledError:
                    continue
                except Exception:
                    break
            if not task.cancelled():
                task.exception()  # Retrieve any failure while preserving caller cancellation.
            raise

    async def _download(self, file_id, owner_id):
        config = self.config
        url = config.base_url.rstrip("/") + config.content_path.format(file_id=file_id)
        headers = {
            "X-AI-Service-Key": config.service_key.get_secret_value(),
            "X-User-ID": owner_id,
            "Accept-Encoding": "identity",
        }
        try:
            async with asyncio.timeout(config.timeout_seconds):
                async with self.client.stream(
                    "GET",
                    url,
                    headers=headers,
                    follow_redirects=False,
                    timeout=config.timeout_seconds,
                ) as response:
                    if response.status_code == 404:
                        raise DomainError(
                            "backend_file_not_found", "File not found or not accessible", 404
                        )
                    if response.status_code in {401, 403}:
                        raise DomainError(
                            "backend_file_forbidden", "Backend refused file access", 403
                        )
                    if response.status_code != 200:
                        raise DomainError(
                            "backend_file_error",
                            "Backend must return content directly with HTTP 200",
                            502,
                        )
                    if response.headers.get("content-encoding", "identity").lower() != "identity":
                        raise DomainError(
                            "backend_content_encoding",
                            "Compressed HTTP responses are not accepted",
                            502,
                        )
                    length = response.headers.get("content-length")
                    if length is not None:
                        try:
                            size = int(length)
                        except ValueError:
                            size = -1
                        if size < 0:
                            raise DomainError(
                                "backend_file_error", "Invalid backend content length", 502
                            )
                        if size > self.limits.max_bytes:
                            raise DomainError(
                                "file_too_large", "Backend file exceeds the byte limit", 413
                            )
                    disposition = Message()
                    disposition["Content-Disposition"] = response.headers.get(
                        "content-disposition", ""
                    )
                    name = disposition.get_filename()
                    if not name:
                        raise DomainError(
                            "backend_filename_missing",
                            "Backend must return a filename in Content-Disposition",
                            502,
                        )
                    validate_name(name)
                    raw = bytearray()
                    async for chunk in response.aiter_bytes(chunk_size=64 * 1024):
                        if len(raw) + len(chunk) > self.limits.max_bytes:
                            raise DomainError(
                                "file_too_large", "Backend file exceeds the byte limit", 413
                            )
                        raw.extend(chunk)
                    if length is not None and len(raw) != int(length):
                        raise DomainError(
                            "backend_file_error",
                            "Backend body length does not match Content-Length",
                            502,
                        )
                    media_type = (
                        response.headers.get("content-type", "application/octet-stream")
                        .split(";", 1)[0]
                        .strip()
                        .lower()
                    )
                    return bytes(raw), name, media_type
        except (httpx.TimeoutException, TimeoutError):
            raise DomainError(
                "backend_file_timeout", "Backend file download timed out", 504
            ) from None
        except httpx.HTTPError:
            raise DomainError(
                "backend_file_unavailable", "Backend file download failed", 502
            ) from None
