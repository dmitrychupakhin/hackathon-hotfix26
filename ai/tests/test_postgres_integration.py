"""Opt-in tests. Only point AI_TEST_DATABASE_URL at an isolated *_test database."""

import asyncio
import hashlib
import os
from pathlib import Path
from urllib.parse import urlsplit
from uuid import uuid4

import asyncpg
import pytest
from conftest import FakeModel, run_body, wait_run
from fastapi.testclient import TestClient

from app.domain import DomainError
from app.infrastructure.postgres import PostgresStore
from app.main import create_app


def dsn():
    value = os.environ.get("AI_TEST_DATABASE_URL")
    if not value:
        pytest.skip("Set AI_TEST_DATABASE_URL for isolated PostgreSQL integration")
    if not urlsplit(value).path.endswith("_test"):
        pytest.fail("Refusing non-test PostgreSQL database")
    return value


@pytest.mark.asyncio
async def test_postgres_repository_transaction_events_and_single_worker():
    run_id = "pg-run-" + str(uuid4())
    job_id = "pg-import-" + str(uuid4())
    duplicate_id = "duplicate-" + str(uuid4())
    store = PostgresStore(dsn())
    await store.open()
    try:
        second = PostgresStore(dsn())
        with pytest.raises(RuntimeError):
            await second.open()
        await store.create(
            "run",
            {"id": run_id, "status": "running", "request": {"questions": [{"id": "q"}]}},
            "pg-owner",
        )
        await store.patch_run(
            run_id, "pg-owner", {"status": "completed"}, "run.completed", {"status": "completed"}
        )
        events = await store.events(run_id, "pg-owner")
        assert events[-1]["type"] == "run.completed"
        with pytest.raises(DomainError):
            await store.events(run_id, "other")
        await store.create("file_import", {"id": job_id, "status": "running"}, "pg-owner")
        await store.patch_object(
            "file_import",
            job_id,
            "pg-owner",
            {"status": "failed"},
            "file_import.failed",
            {"status": "failed"},
        )
        assert (await store.events(job_id, "pg-owner", kind="file_import"))[-1][
            "type"
        ] == "file_import.failed"
        with pytest.raises(asyncpg.UniqueViolationError):
            await store.create_many(
                [("test", {"id": duplicate_id}), ("test", {"id": duplicate_id})], "pg-owner"
            )
        with pytest.raises(DomainError):
            await store.get("test", duplicate_id, "pg-owner")
    finally:
        await store.close()


@pytest.mark.asyncio
async def test_postgres_restart_recovery_preserves_accepted_answers():
    recovery_id = "recover-" + str(uuid4())
    store = PostgresStore(dsn())
    await store.open()
    try:
        await store.create(
            "run",
            {
                "id": recovery_id,
                "status": "running",
                "request": {"questions": [{"id": "q1"}, {"id": "q2"}]},
                "result": {
                    "answers": [{"id": "q1", "status": "ответ", "answer": "18000"}],
                    "raw_outputs": [],
                },
            },
            "pg-owner",
        )
        await store.recover_interrupted()
        result = await store.get("run", recovery_id, "pg-owner")
        assert result["status"] == "interrupted"
        assert result["result"]["answers"][0]["answer"] == "18000"
        assert result["result"]["answers"][1]["status"] == "не знаю"
    finally:
        await store.close()


@pytest.mark.parametrize("restricted_role", [False, True])
def test_postgres_api_file_import_and_harness(settings, headers, tmp_path, restricted_role):
    value = dsn()
    source_id = "file-" + str(uuid4())
    source = Path(settings.source_root)
    source.mkdir(exist_ok=True)
    raw = "Обеспечение заявки: 18000 рублей.".encode()
    (source / "notice.txt").write_bytes(raw)

    async def register():
        c = await asyncpg.connect(value)
        try:
            await c.execute(
                "INSERT INTO ai.files(owner,id,version,filename,relative_path,sha256,media_type) VALUES($1,$2,$3,$4,$5,$6,$7)",
                "user-1",
                source_id,
                "v1",
                "notice.txt",
                "notice.txt",
                hashlib.sha256(raw).hexdigest(),
                "text/plain",
            )
        finally:
            await c.close()

    asyncio.run(register())
    if restricted_role:
        role = "ai_app_test_" + uuid4().hex

        async def create_role():
            c = await asyncpg.connect(value)
            try:
                await c.execute(f"CREATE ROLE {role} LOGIN PASSWORD 'local_test_only'")
                await c.execute(f"GRANT USAGE ON SCHEMA ai TO {role}")
                await c.execute(f"GRANT SELECT ON ai.schema_version, ai.files TO {role}")
                await c.execute(f"GRANT UPDATE(updated_at) ON ai.files TO {role}")
                await c.execute(f"GRANT SELECT,INSERT,UPDATE ON ai.objects TO {role}")
                await c.execute(f"GRANT SELECT,INSERT ON ai.events TO {role}")
                await c.execute(f"GRANT USAGE,SELECT ON ALL SEQUENCES IN SCHEMA ai TO {role}")
            finally:
                await c.close()

        asyncio.run(create_role())
        parsed = urlsplit(value)
        value = f"postgresql://{role}:local_test_only@{parsed.hostname}:{parsed.port}{parsed.path}"
    settings = settings.model_copy(update={"database_url": value})
    # model_copy does not coerce SecretStr; explicit re-validation preserves config types.
    from pydantic import SecretStr

    settings.database_url = SecretStr(value)
    with TestClient(create_app(settings, FakeModel())) as client:
        assert (
            client.get("/api/v1/info", headers=headers).json()["storage"]["engine"] == "postgresql"
        )
        pid = client.post(
            "/api/v1/packages", headers=headers, json={"code": "P01", "name": "PG test"}
        ).json()["id"]
        job = client.post(
            f"/api/v1/packages/{pid}/documents/by-id",
            headers=headers,
            json={"file_ids": [source_id]},
        ).json()
        import time

        for _ in range(300):
            job = client.get(f"/api/v1/file-imports/{job['id']}", headers=headers).json()
            if job["status"] in {"completed", "failed"}:
                break
            time.sleep(0.01)
        assert job["status"] == "completed", job
        assert (
            client.get(f"/api/v1/file-imports/{job['id']}/events", headers=headers).json()[-1][
                "type"
            ]
            == "file_import.completed"
        )
        run_id = client.post("/api/v1/runs", headers=headers, json=run_body(pid)).json()["id"]
        run = wait_run(client, headers, run_id)
        assert run["status"] == "completed" and run["result"]["answers"][0]["status"] == "ответ"
        assert run["result"]["evidence_audit"]
        snapshot = client.get(f"/api/v1/runs/{run_id}/inputs", headers=headers).json()["snapshot"]
        assert snapshot["packages"][0]["documents"][0]["artifact_key"]
