"""Shared PostgreSQL repository. Schema creation belongs to backend/deployment."""

import asyncio
import json

import asyncpg

from app.domain import Answer, AnswerStatus, DomainError, now


class PostgresStore:
    def __init__(self, dsn):
        self.dsn = dsn
        self.pool = None
        self.guard = None
        self.lock = asyncio.Lock()

    async def open(self):
        async def init(connection):
            await connection.set_type_codec(
                "jsonb", schema="pg_catalog", encoder=json.dumps, decoder=json.loads
            )

        try:
            self.pool = await asyncpg.create_pool(
                self.dsn, min_size=1, max_size=6, init=init, command_timeout=30
            )
            self.guard = await self.pool.acquire()
            version = await self.guard.fetchval(
                "SELECT version FROM ai.schema_version WHERE singleton=true"
            )
            if version != 1:
                raise RuntimeError("unsupported schema")
            if not await self.guard.fetchval("SELECT pg_try_advisory_lock(6748121901::bigint)"):
                raise RuntimeError("AI worker already active")
        except Exception:
            await self.close()
            raise RuntimeError(
                "Cannot initialize AI PostgreSQL repository. Backend must create the shared database and apply ai/sql/001_ai_schema.sql; only one AI worker may use it."
            ) from None

    async def close(self):
        if self.pool:
            if self.guard:
                await self.guard.execute("SELECT pg_advisory_unlock(6748121901::bigint)")
                await self.pool.release(self.guard)
                self.guard = None
            await self.pool.close()
            self.pool = None

    async def ping(self):
        async with self.pool.acquire() as c:
            await c.fetchval("SELECT 1")

    async def _get(self, c, kind, object_id, owner, for_update=False):
        query = "SELECT data FROM ai.objects WHERE kind=$1 AND id=$2 AND owner=$3"
        if for_update:
            query += " FOR UPDATE"
        row = await c.fetchrow(query, kind, object_id, owner)
        if not row:
            raise DomainError("not_found", "Resource not found", 404)
        return dict(row["data"])

    async def get(self, kind, object_id, owner):
        async with self.pool.acquire() as c:
            return await self._get(c, kind, object_id, owner)

    async def list(self, kind, owner, limit=100):
        async with self.pool.acquire() as c:
            rows = await c.fetch(
                "SELECT data FROM ai.objects WHERE kind=$1 AND owner=$2 ORDER BY created_at DESC,id DESC LIMIT $3",
                kind,
                owner,
                limit,
            )
        return [dict(r["data"]) for r in rows]

    async def create(self, kind, data, owner):
        async with self.lock, self.pool.acquire() as c:
            await c.execute(
                "INSERT INTO ai.objects(kind,id,owner,data) VALUES($1,$2,$3,$4)",
                kind,
                data["id"],
                owner,
                data,
            )
        return data

    async def create_many(self, items, owner):
        async with self.lock, self.pool.acquire() as c, c.transaction():
            await c.executemany(
                "INSERT INTO ai.objects(kind,id,owner,data) VALUES($1,$2,$3,$4)",
                [(k, d["id"], owner, d) for k, d in items],
            )

    async def save(self, kind, data, owner):
        async with self.lock, self.pool.acquire() as c, c.transaction():
            await self._get(c, kind, data["id"], owner, True)
            await c.execute(
                "UPDATE ai.objects SET data=$1 WHERE kind=$2 AND id=$3 AND owner=$4",
                data,
                kind,
                data["id"],
                owner,
            )
        return data

    async def _event(self, c, run_id, event_type, data):
        row = await c.fetchrow(
            "INSERT INTO ai.events(run_id,type,data) VALUES($1,$2,$3) RETURNING seq,created_at",
            run_id,
            event_type,
            data,
        )
        return {
            "seq": row["seq"],
            "run_id": run_id,
            "type": event_type,
            "data": data,
            "created_at": row["created_at"].isoformat(),
        }

    async def append_event(self, run_id, event_type, data):
        async with self.lock, self.pool.acquire() as c, c.transaction():
            return await self._event(c, run_id, event_type, data)

    async def patch_run(self, run_id, owner, patch, event_type=None, event_data=None):
        async with self.lock, self.pool.acquire() as c, c.transaction():
            data = await self._get(c, "run", run_id, owner, True)
            data.update(patch)
            data["updated_at"] = now()
            await c.execute(
                "UPDATE ai.objects SET data=$1 WHERE kind='run' AND id=$2 AND owner=$3",
                data,
                run_id,
                owner,
            )
            if event_type:
                await self._event(c, run_id, event_type, event_data or {})
            return data

    async def patch_object(self, kind, object_id, owner, patch, event_type, event_data):
        async with self.lock, self.pool.acquire() as c, c.transaction():
            data = await self._get(c, kind, object_id, owner, True)
            data.update(patch)
            data["updated_at"] = now()
            await c.execute(
                "UPDATE ai.objects SET data=$1 WHERE kind=$2 AND id=$3 AND owner=$4",
                data,
                kind,
                object_id,
                owner,
            )
            await self._event(c, object_id, event_type, event_data)
            return data

    async def events(self, run_id, owner, after=0, limit=100, kind="run"):
        async with self.pool.acquire() as c:
            await self._get(c, kind, run_id, owner)
            rows = await c.fetch(
                "SELECT seq,run_id,type,data,created_at FROM ai.events WHERE run_id=$1 AND seq>$2 ORDER BY seq LIMIT $3",
                run_id,
                after,
                limit,
            )
        return [dict(r) | {"created_at": r["created_at"].isoformat()} for r in rows]

    async def source_file(self, file_id, owner):
        async with self.pool.acquire() as c:
            row = await c.fetchrow(
                "SELECT * FROM ai.files WHERE id=$1 AND owner=$2", file_id, owner
            )
        if not row:
            raise DomainError("not_found", "File not found or not accessible", 404)
        return dict(row)

    async def publish_import(self, package, job, owner, sources):
        async with self.lock, self.pool.acquire() as c, c.transaction():
            for source in sources:
                row = await c.fetchrow(
                    "SELECT * FROM ai.files WHERE id=$1 AND owner=$2 FOR SHARE", source["id"], owner
                )
                if not row or any(
                    row[k] != source[k]
                    for k in ["version", "sha256", "relative_path", "filename", "media_type"]
                ):
                    raise DomainError("source_changed", "Source version changed during import", 409)
            await self._get(c, "package", package["id"], owner, True)
            await self._get(c, "file_import", job["id"], owner, True)
            await c.execute(
                "UPDATE ai.objects SET data=$1 WHERE kind='package' AND id=$2 AND owner=$3",
                package,
                package["id"],
                owner,
            )
            await c.execute(
                "UPDATE ai.objects SET data=$1 WHERE kind='file_import' AND id=$2 AND owner=$3",
                job,
                job["id"],
                owner,
            )
            await self._event(
                c,
                job["id"],
                "file_import.completed",
                {"status": "completed", "processed": job["processed"], "total": job["total"]},
            )

    async def recover_interrupted(self):
        async with self.pool.acquire() as c:
            rows = await c.fetch(
                "SELECT id,owner,data FROM ai.objects WHERE kind='run' AND data->>'status' NOT IN ('completed','failed','cancelled','interrupted')"
            )
        for row in rows:
            run = dict(row["data"])
            result = run.get("result") or {"answers": [], "raw_outputs": []}
            accepted = {a["id"]: a for a in result["answers"]}
            result["answers"] = [
                accepted.get(q["id"])
                or Answer(
                    id=q["id"],
                    status=AnswerStatus.UNKNOWN,
                    origin="fallback",
                    reason="process_restarted",
                ).model_dump(mode="json")
                for q in run.get("request", {}).get("questions", [])
            ]
            await self.patch_run(
                row["id"],
                row["owner"],
                {
                    "status": "interrupted",
                    "result": result,
                    "error": {
                        "code": "process_restarted",
                        "message": "Process stopped; this run is not automatically retried.",
                    },
                },
                "run.interrupted",
                {"reason": "process_restarted"},
            )
