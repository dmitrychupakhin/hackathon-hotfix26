import asyncio
import hashlib
import time
from pathlib import Path

import pytest
from starlette.websockets import WebSocketDisconnect

from app.domain import now


def setup_source(
    client,
    headers,
    settings,
    file_id="doc-1",
    text="Обеспечение заявки: 18000 рублей.",
    version="v1",
):
    root = Path(settings.source_root)
    root.mkdir(exist_ok=True)
    path = root / "source.txt"
    path.write_text(text)
    record = {
        "id": file_id,
        "owner": "user-1",
        "version": version,
        "updated_at": now(),
        "filename": "notice.txt",
        "relative_path": "source.txt",
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "media_type": "text/plain",
    }
    client.portal.call(client.app.state.store.create, "source_file", record, "user-1")
    package_id = client.post(
        "/api/v1/packages", headers=headers, json={"code": "P01", "name": "Source test"}
    ).json()["id"]
    return package_id, record, path


def wait_import(client, headers, job_id):
    for _ in range(400):
        job = client.get(f"/api/v1/file-imports/{job_id}", headers=headers).json()
        if job["status"] in {"completed", "failed", "cancelled", "interrupted"}:
            return job
        time.sleep(0.01)
    pytest.fail("Import did not finish")


def submit(client, headers, pid, ids):
    r = client.post(
        f"/api/v1/packages/{pid}/documents/by-id", headers=headers, json={"file_ids": ids}
    )
    assert r.status_code == 202, r.text
    return r.json()["id"]


def test_file_id_cache_and_websocket_replay(client, headers, settings):
    pid, source, path = setup_source(client, headers, settings)
    first = submit(client, headers, pid, [source["id"]])
    job = wait_import(client, headers, first)
    assert job["status"] == "completed", job
    documents = client.get(f"/api/v1/packages/{pid}", headers=headers).json()["documents"]
    previous_revision = client.get(f"/api/v1/packages/{pid}", headers=headers).json()["revision"]
    assert len(documents) == 1 and documents[0]["source_version"] == "v1"
    folder = Path(settings.file_cache_root) / documents[0]["artifact_key"]
    assert (folder / "extracted.txt").read_text() == "Обеспечение заявки: 18000 рублей."
    second = submit(client, headers, pid, [source["id"]])
    assert wait_import(client, headers, second)["status"] == "completed"
    assert len(client.get(f"/api/v1/packages/{pid}", headers=headers).json()["documents"]) == 1
    assert (
        client.get(f"/api/v1/packages/{pid}", headers=headers).json()["revision"]
        == previous_revision
    )
    assert (
        client.get(f"/api/v1/packages/{pid}", headers=headers).json()["documents"][0]["id"]
        == documents[0]["id"]
    )
    events = client.get(f"/api/v1/file-imports/{second}/events", headers=headers).json()
    assert any(e["type"] == "file.cache_hit" for e in events)
    ticket = client.post(f"/api/v1/file-imports/{second}/ws-ticket", headers=headers).json()[
        "ticket"
    ]
    received = []
    with client.websocket_connect(f"/api/v1/file-imports/{second}/ws?ticket={ticket}") as ws:
        with pytest.raises(WebSocketDisconnect):
            while True:
                received.append(ws.receive_json())
    assert received == events
    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect(f"/api/v1/runs/{second}/ws?ticket={ticket}"):
            pass


def test_file_source_access_is_owner_scoped(client, headers, settings):
    pid, source, _ = setup_source(client, headers, settings)
    other = {**headers, "X-User-ID": "other"}
    assert (
        client.post(
            f"/api/v1/packages/{pid}/documents/by-id",
            headers=other,
            json={"file_ids": [source["id"]]},
        ).status_code
        == 404
    )
    assert (
        client.post(
            f"/api/v1/packages/{pid}/documents/by-id",
            headers=headers,
            json={"file_ids": ["missing"]},
        ).status_code
        == 404
    )
    assert (
        client.post(
            f"/api/v1/packages/{pid}/documents/by-id",
            headers=headers,
            json={"file_ids": ["../escape"]},
        ).status_code
        == 422
    )


def test_failed_import_does_not_publish_partial_package(client, headers, settings):
    pid, source, _ = setup_source(client, headers, settings)
    bad = {**source, "id": "doc-bad", "sha256": "f" * 64, "filename": "other.txt"}
    client.portal.call(client.app.state.store.create, "source_file", bad, "user-1")
    job = wait_import(client, headers, submit(client, headers, pid, [source["id"], bad["id"]]))
    assert job["status"] == "failed" and job["processed"] == 1
    assert client.get(f"/api/v1/packages/{pid}", headers=headers).json()["documents"] == []


def test_new_source_version_replaces_current_binding_but_preserves_old_snapshot(
    client, headers, settings
):
    pid, source, path = setup_source(client, headers, settings)
    assert (
        wait_import(client, headers, submit(client, headers, pid, [source["id"]]))["status"]
        == "completed"
    )
    previous = client.get(f"/api/v1/packages/{pid}", headers=headers).json()["documents"][0]
    path.write_text("Обеспечение заявки: 36000 рублей.")
    source.update(
        version="v2", sha256=hashlib.sha256(path.read_bytes()).hexdigest(), updated_at=now()
    )
    client.portal.call(client.app.state.store.save, "source_file", source, "user-1")
    assert (
        wait_import(client, headers, submit(client, headers, pid, [source["id"]]))["status"]
        == "completed"
    )
    current = client.get(f"/api/v1/packages/{pid}", headers=headers).json()["documents"][0]
    assert current["source_version"] == "v2" and current["id"] != previous["id"]
    assert (
        (Path(settings.file_cache_root) / previous["artifact_key"] / "extracted.txt")
        .read_text()
        .endswith("18000 рублей.")
    )


def test_duplicate_cancel_is_safe(client, headers, settings):
    pid, source, _ = setup_source(client, headers, settings)

    async def slow(*args):
        await asyncio.sleep(60)

    client.app.state.file_cache.prepare = slow
    job_id = submit(client, headers, pid, [source["id"]])
    client.post(f"/api/v1/file-imports/{job_id}/cancel", headers=headers)
    client.post(f"/api/v1/file-imports/{job_id}/cancel", headers=headers)
    job = wait_import(client, headers, job_id)
    assert job["status"] == "cancelled"
    assert client.get(f"/api/v1/packages/{pid}", headers=headers).json()["documents"] == []
    events = client.get(f"/api/v1/file-imports/{job_id}/events", headers=headers).json()
    assert sum(e["type"] == "file_import.cancelled" for e in events) == 1
