from __future__ import annotations

import asyncio
import fcntl
import json
from pathlib import Path

import aiosqlite

from app.domain import TERMINAL, Answer, AnswerStatus, DomainError, now


class Store:
    """Single-process SQLite repository; mutations and events commit together."""

    def __init__(self, path: Path):
        self.path = path
        self.lock = asyncio.Lock()
        self.db: aiosqlite.Connection | None = None
        self.process_lock = None

    async def open(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.process_lock = self.path.with_suffix(self.path.suffix + ".lock").open("a")
        try:
            fcntl.flock(self.process_lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            self.process_lock.close()
            self.process_lock = None
            raise RuntimeError(
                "This SQLite service requires exactly one worker process per database"
            ) from None
        self.db = await aiosqlite.connect(self.path)
        self.db.row_factory = aiosqlite.Row
        await self.db.executescript("""
            PRAGMA journal_mode=WAL;
            PRAGMA busy_timeout=5000;
            CREATE TABLE IF NOT EXISTS objects (
                kind TEXT NOT NULL, id TEXT NOT NULL, owner TEXT NOT NULL,
                data TEXT NOT NULL, PRIMARY KEY(kind,id)
            );
            CREATE INDEX IF NOT EXISTS objects_owner ON objects(owner,kind);
            CREATE TABLE IF NOT EXISTS events (
                seq INTEGER PRIMARY KEY AUTOINCREMENT, run_id TEXT NOT NULL,
                type TEXT NOT NULL, data TEXT NOT NULL, created_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS events_run ON events(run_id,seq);
            PRAGMA user_version=1;
        """)
        await self.db.commit()

    async def close(self):
        if self.db:
            await self.db.close()
        if self.process_lock:
            fcntl.flock(self.process_lock, fcntl.LOCK_UN)
            self.process_lock.close()
            self.process_lock = None

    async def ping(self):
        async with self.lock:
            cursor = await self.db.execute("SELECT 1")
            await cursor.fetchone()
            await cursor.close()

    async def _get(self, kind: str, object_id: str, owner: str):
        cursor = await self.db.execute(
            "SELECT data FROM objects WHERE kind=? AND id=? AND owner=?",
            (kind, object_id, owner),
        )
        row = await cursor.fetchone()
        await cursor.close()
        if not row:
            raise DomainError("not_found", "Resource not found", 404)
        return json.loads(row["data"])

    async def get(self, kind: str, object_id: str, owner: str):
        async with self.lock:
            return await self._get(kind, object_id, owner)

    async def list(self, kind: str, owner: str, limit: int = 100):
        async with self.lock:
            cursor = await self.db.execute(
                "SELECT data FROM objects WHERE kind=? AND owner=? ORDER BY rowid DESC LIMIT ?",
                (kind, owner, limit),
            )
            rows = await cursor.fetchall()
            await cursor.close()
        return [json.loads(row["data"]) for row in rows]

    async def create(self, kind: str, data: dict, owner: str):
        async with self.lock:
            await self.db.execute(
                "INSERT INTO objects(kind,id,owner,data) VALUES (?,?,?,?)",
                (kind, data["id"], owner, json.dumps(data, ensure_ascii=False)),
            )
            await self.db.commit()
        return data

    async def create_many(self, items: list[tuple[str, dict]], owner: str):
        async with self.lock:
            try:
                await self.db.executemany(
                    "INSERT INTO objects(kind,id,owner,data) VALUES (?,?,?,?)",
                    [
                        (kind, data["id"], owner, json.dumps(data, ensure_ascii=False))
                        for kind, data in items
                    ],
                )
                await self.db.commit()
            except Exception:
                await self.db.rollback()
                raise

    async def save(self, kind: str, data: dict, owner: str):
        async with self.lock:
            await self._get(kind, data["id"], owner)
            await self.db.execute(
                "UPDATE objects SET data=? WHERE kind=? AND id=? AND owner=?",
                (json.dumps(data, ensure_ascii=False), kind, data["id"], owner),
            )
            await self.db.commit()
        return data

    async def _event(self, run_id: str, event_type: str, data: dict):
        created = now()
        cursor = await self.db.execute(
            "INSERT INTO events(run_id,type,data,created_at) VALUES (?,?,?,?)",
            (run_id, event_type, json.dumps(data, ensure_ascii=False), created),
        )
        return {
            "seq": cursor.lastrowid,
            "run_id": run_id,
            "type": event_type,
            "data": data,
            "created_at": created,
        }

    async def append_event(self, run_id: str, event_type: str, data: dict):
        async with self.lock:
            event = await self._event(run_id, event_type, data)
            await self.db.commit()
            return event

    async def patch_run(
        self, run_id: str, owner: str, patch: dict, event_type=None, event_data=None
    ):
        async with self.lock:
            data = await self._get("run", run_id, owner)
            data.update(patch)
            data["updated_at"] = now()
            await self.db.execute(
                "UPDATE objects SET data=? WHERE kind='run' AND id=? AND owner=?",
                (json.dumps(data, ensure_ascii=False), run_id, owner),
            )
            if event_type:
                await self._event(run_id, event_type, event_data or {})
            await self.db.commit()
            return data

    async def events(self, run_id: str, owner: str, after: int = 0, limit: int = 100, kind="run"):
        async with self.lock:
            await self._get(kind, run_id, owner)
            cursor = await self.db.execute(
                "SELECT * FROM events WHERE run_id=? AND seq>? ORDER BY seq LIMIT ?",
                (run_id, after, limit),
            )
            rows = await cursor.fetchall()
            await cursor.close()
        return [
            {
                "seq": r["seq"],
                "run_id": r["run_id"],
                "type": r["type"],
                "data": json.loads(r["data"]),
                "created_at": r["created_at"],
            }
            for r in rows
        ]

    async def source_file(self, file_id, owner):
        return await self.get("source_file", file_id, owner)

    async def patch_object(self, kind, object_id, owner, patch, event_type, event_data):
        async with self.lock:
            try:
                data = await self._get(kind, object_id, owner)
                data.update(patch)
                data["updated_at"] = now()
                await self.db.execute(
                    "UPDATE objects SET data=? WHERE kind=? AND id=? AND owner=?",
                    (json.dumps(data, ensure_ascii=False), kind, object_id, owner),
                )
                await self._event(object_id, event_type, event_data)
                await self.db.commit()
                return data
            except BaseException:
                await self.db.rollback()
                raise

    async def publish_import(self, package, job, owner, sources):
        async with self.lock:
            try:
                for source in sources:
                    row = await self._get("source_file", source["id"], owner)
                    if any(
                        row[k] != source[k]
                        for k in ["version", "sha256", "relative_path", "filename", "media_type"]
                    ):
                        raise DomainError(
                            "source_changed", "Source version changed during import", 409
                        )
                await self._get("package", package["id"], owner)
                await self._get("file_import", job["id"], owner)
                for kind, data in [("package", package), ("file_import", job)]:
                    await self.db.execute(
                        "UPDATE objects SET data=? WHERE kind=? AND id=? AND owner=?",
                        (json.dumps(data, ensure_ascii=False), kind, data["id"], owner),
                    )
                await self._event(
                    job["id"],
                    "file_import.completed",
                    {"status": "completed", "processed": job["processed"], "total": job["total"]},
                )
                await self.db.commit()
            except BaseException:
                await self.db.rollback()
                raise

    async def recover_interrupted(self):
        async with self.lock:
            cursor = await self.db.execute("SELECT id,owner,data FROM objects WHERE kind='run'")
            rows = await cursor.fetchall()
            await cursor.close()
        for row in rows:
            run = json.loads(row["data"])
            if run["status"] not in TERMINAL:
                result = run.get("result") or {"answers": [], "raw_outputs": []}
                existing = {answer["id"]: answer for answer in result["answers"]}
                result["answers"] = [
                    existing.get(q["id"])
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
                            "message": "The process stopped; this run was not automatically retried.",
                        },
                    },
                    "run.interrupted",
                    {"reason": "process_restarted"},
                )
