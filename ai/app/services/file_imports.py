"""Bounded file-ID imports from the shared catalog; originals and TXT stay on disk."""

import asyncio
import hashlib

from pydantic import ValidationError

from app.domain import Document, DomainError, Package, now, uid
from app.infrastructure.files.cache_models import SourceFile
from app.services.documents import with_documents


def artifact_document(artifact, source=None, document_id=None):
    parsed = artifact.parsed
    return Document(
        id=document_id or uid(),
        name=parsed.name,
        original_name=source.filename if source else parsed.name,
        text=parsed.text,
        sha256=hashlib.sha256(parsed.text.encode()).hexdigest(),
        encoding=parsed.extractor.split(":", 1)[1]
        if parsed.extractor.startswith("text:")
        else "utf-8",
        warning=";".join(parsed.warnings) or None,
        partial=parsed.partial,
        source_file_id=source.id if source else None,
        source_version=source.version if source else parsed.original_sha256,
        source_updated_at=source.updated_at.isoformat() if source else None,
        original_sha256=parsed.original_sha256,
        media_type=parsed.media_type,
        extractor=parsed.extractor,
        artifact_key=artifact.artifact_key,
        locations=[p.model_dump(exclude_none=True) for p in parsed.locations],
    )


class FileImports:
    def __init__(self, store, cache, settings, mutation_lock):
        self.store, self.cache, self.settings, self.mutation_lock = (
            store,
            cache,
            settings,
            mutation_lock,
        )
        self.tasks = {}
        self.cancelling = set()
        self.finalizing = set()
        self.started = set()
        self.closing = False
        self.submission_lock = asyncio.Lock()
        self.slots = asyncio.Semaphore(settings.concurrent_runs)

    async def submit(self, package_id, file_ids, owner):
        await self.store.get("package", package_id, owner)
        async with self.submission_lock:
            if self.closing:
                raise DomainError("shutting_down", "Service is stopping", 503)
            if len(self.tasks) >= self.settings.pending_runs:
                raise DomainError("queue_full", "Import queue is full", 429)
            # Validate access before allocating a job. No source paths come from HTTP.
            for file_id in file_ids:
                await self.store.source_file(file_id, owner)
            job = {
                "id": uid(),
                "package_id": package_id,
                "file_ids": file_ids,
                "status": "queued",
                "processed": 0,
                "total": len(file_ids),
                "documents": [],
                "created_at": now(),
                "updated_at": now(),
                "error": None,
            }
            await self.store.create("file_import", job, owner)
            await self.store.append_event(job["id"], "file_import.queued", {"total": len(file_ids)})
            task = asyncio.create_task(self._run(job, owner))
            self.tasks[job["id"]] = task
            task.add_done_callback(lambda _: self.tasks.pop(job["id"], None))
            return job

    async def _save(self, job, owner, event, data):
        job["updated_at"] = now()
        await self.store.patch_object("file_import", job["id"], owner, job, event, data)

    async def _run(self, job, owner):
        self.started.add(job["id"])
        status = "completed"
        error = None
        additions = []
        sources = []
        published = False
        try:
            async with asyncio.timeout(self.settings.file_import_timeout), self.slots:
                if self.closing or job["id"] in self.cancelling:
                    raise asyncio.CancelledError
                job["status"] = "running"
                await self._save(job, owner, "file_import.started", {"total": job["total"]})
                for file_id in job["file_ids"]:
                    source = SourceFile.model_validate(await self.store.source_file(file_id, owner))
                    sources.append(source)
                    await self.store.append_event(
                        job["id"],
                        "file.started",
                        {"file_id": file_id, "name": source.filename, "version": source.version},
                    )
                    artifact = await self.cache.prepare(source, owner)
                    document = artifact_document(artifact, source)
                    additions.append(document)
                    await self.store.append_event(
                        job["id"],
                        "file.cache_hit" if artifact.cache_hit else "file.text_extracted",
                        {
                            "file_id": file_id,
                            "version": source.version,
                            "partial": document.partial,
                            "characters": len(document.text),
                        },
                    )
                    job["processed"] += 1
                    job["documents"].append(
                        {
                            "id": document.id,
                            "source_file_id": file_id,
                            "version": source.version,
                            "name": document.name,
                            "partial": document.partial,
                            "artifact_key": document.artifact_key,
                        }
                    )
                    await self._save(
                        job,
                        owner,
                        "file.ready",
                        {"file_id": file_id, "processed": job["processed"], "total": job["total"]},
                    )
                for source in sources:
                    current = SourceFile.model_validate(
                        await self.store.source_file(source.id, owner)
                    )
                    if any(
                        getattr(current, k) != getattr(source, k)
                        for k in ["version", "sha256", "relative_path", "filename", "media_type"]
                    ):
                        raise DomainError(
                            "source_changed",
                            "Source metadata changed during import; retry with the new version",
                            409,
                        )
                self.finalizing.add(job["id"])
                publication = asyncio.create_task(self._publish(job, owner, additions, sources))
                while not publication.done():
                    try:
                        await asyncio.shield(publication)
                    except asyncio.CancelledError:
                        continue
                publication.result()
                published = True
        except asyncio.CancelledError:
            status = "interrupted" if self.closing else "cancelled"
            error = {"code": status, "message": "Import stopped; no partial package publication."}
        except TimeoutError:
            status = "failed"
            error = {"code": "file_import_timeout", "message": "File import deadline exceeded"}
        except DomainError as exc:
            status = "failed"
            error = {"code": exc.code, "message": exc.message}
        except ValidationError:
            status = "failed"
            error = {
                "code": "invalid_source_metadata",
                "message": "Backend file catalog metadata is invalid",
            }
        except Exception:
            status = "failed"
            error = {"code": "file_import_failed", "message": "Unexpected file import error"}
        finally:
            self.finalizing.add(job["id"])
            job.update(status=status, error=error, finished_at=now())

            async def final_save():
                if not published:
                    await self._save(
                        job,
                        owner,
                        f"file_import.{status}",
                        {
                            "status": status,
                            "processed": job["processed"],
                            "total": job["total"],
                            "error": error,
                        },
                    )

            final = asyncio.create_task(final_save())
            while not final.done():
                try:
                    await asyncio.shield(final)
                except asyncio.CancelledError:
                    continue
            try:
                final.result()
            finally:
                self.finalizing.discard(job["id"])
                self.cancelling.discard(job["id"])
                self.started.discard(job["id"])

    async def _publish(self, job, owner, additions, sources):
        async with self.mutation_lock:
            package = Package.model_validate(
                await self.store.get("package", job["package_id"], owner)
            )
            replacements = {d.source_file_id: d for d in additions}
            documents = []
            imported = []
            for old in package.documents:
                new = replacements.pop(old.source_file_id, None) if old.source_file_id else None
                if new is not None:
                    if all(
                        getattr(old, key) == getattr(new, key)
                        for key in ["source_version", "original_sha256", "sha256", "artifact_key"]
                    ):
                        new = old
                    documents.append(new)
                    imported.append(new)
                else:
                    documents.append(old)
            documents.extend(replacements.values())
            imported.extend(replacements.values())
            package = with_documents(
                package.model_copy(update={"documents": []}), documents, self.settings
            )
            job["documents"] = [
                {
                    "id": d.id,
                    "source_file_id": d.source_file_id,
                    "version": d.source_version,
                    "name": d.name,
                    "partial": d.partial,
                    "artifact_key": d.artifact_key,
                }
                for d in imported
            ]
            job.update(status="completed", finished_at=now(), updated_at=now(), error=None)
            await self.store.publish_import(
                package.model_dump(), job, owner, [s.model_dump(mode="json") for s in sources]
            )

    async def cancel(self, job_id, owner):
        job = await self.store.get("file_import", job_id, owner)
        if (
            job["status"] in {"completed", "failed", "cancelled", "interrupted"}
            or job_id in self.cancelling
            or job_id in self.finalizing
        ):
            return job
        self.cancelling.add(job_id)
        task = self.tasks.get(job_id)
        # Marking before any await prevents duplicate cancellation of finalization.
        if task and job_id in self.started:
            task.cancel()
        return job

    async def recover(self):
        # Single worker lock is already held by PostgresStore.
        if hasattr(self.store, "pool"):
            async with self.store.pool.acquire() as c:
                rows = await c.fetch(
                    "SELECT owner,data FROM ai.objects WHERE kind='file_import' AND data->>'status' IN ('queued','running')"
                )
            items = [(r["owner"], dict(r["data"])) for r in rows]
        else:
            async with self.store.lock:
                cursor = await self.store.db.execute(
                    "SELECT owner,data FROM objects WHERE kind='file_import'"
                )
                rows = await cursor.fetchall()
                await cursor.close()
            import json

            items = [(r["owner"], json.loads(r["data"])) for r in rows]
        for owner, job in items:
            if job["status"] in {"queued", "running"}:
                job.update(
                    status="interrupted",
                    finished_at=now(),
                    error={
                        "code": "process_restarted",
                        "message": "Import was interrupted; retry explicitly",
                    },
                )
                await self._save(job, owner, "file_import.interrupted", {"status": "interrupted"})

    async def close(self):
        self.closing = True
        for job_id, task in list(self.tasks.items()):
            self.cancelling.add(job_id)
            if job_id in self.started and job_id not in self.finalizing and not task.cancelling():
                task.cancel()
        await asyncio.gather(*list(self.tasks.values()), return_exceptions=True)
