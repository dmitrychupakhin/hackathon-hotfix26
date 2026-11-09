import asyncio
import csv
import io
import json
import zipfile

import pytest
from conftest import FakeModel, package, reply, run_body, wait_run
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from app.domain import DomainError
from app.main import create_app
from app.services.importing import import_archive


def test_swagger_health_and_auth(client, headers):
    assert client.get("/docs").status_code == 200
    schema = client.get("/openapi.json").json()
    assert "/api/v1/runs" in schema["paths"]
    assert any(
        p["name"] == "X-User-ID" for p in schema["paths"]["/api/v1/packages"]["get"]["parameters"]
    )
    assert client.get("/health/ready").status_code == 200
    assert client.get("/api/v1/packages").status_code == 401
    assert client.get("/api/v1/packages", headers=headers).status_code == 200


def test_owner_isolation(client, headers):
    pid = package(client, headers)
    other = {**headers, "X-User-ID": "other-user"}
    assert client.get(f"/api/v1/packages/{pid}", headers=other).status_code == 404
    assert client.get("/api/v1/packages", headers=other).json()["items"] == []
    assert client.post("/api/v1/runs", headers=other, json=run_body(pid)).status_code == 404


def test_upload_cp1251_and_reject_path_and_duplicates(client, headers):
    pid = client.post(
        "/api/v1/packages", headers=headers, json={"code": "P02", "name": "Test"}
    ).json()["id"]
    response = client.post(
        f"/api/v1/packages/{pid}/documents",
        headers=headers,
        files={"files": ("data.txt", "Обеспечение не требуется".encode("cp1251"), "text/plain")},
    )
    assert response.status_code == 201
    assert response.json()["documents"][0]["encoding"] == "cp1251"
    assert (
        client.post(
            f"/api/v1/packages/{pid}/documents/text",
            headers=headers,
            json={"name": "../.env", "text": "x"},
        ).status_code
        == 422
    )
    assert (
        client.post(
            f"/api/v1/packages/{pid}/documents/text",
            headers=headers,
            json={"name": "data.txt", "text": "x"},
        ).status_code
        == 409
    )


def test_idempotency_returns_same_run_and_rejects_new_body(client, headers):
    pid = package(client, headers)
    keyed = {**headers, "Idempotency-Key": "request-1"}
    a = client.post("/api/v1/runs", headers=keyed, json=run_body(pid))
    b = client.post("/api/v1/runs", headers=keyed, json=run_body(pid))
    assert a.status_code == b.status_code == 202
    assert a.json()["id"] == b.json()["id"]
    assert (
        client.post("/api/v1/runs", headers=keyed, json=run_body(pid, mode="raw")).status_code
        == 409
    )
    wait_run(client, headers, a.json()["id"])


def test_websocket_replay_and_ticket_scope(client, headers):
    pid = package(client, headers)
    run_id = client.post("/api/v1/runs", headers=headers, json=run_body(pid)).json()["id"]
    wait_run(client, headers, run_id)
    events = client.get(f"/api/v1/runs/{run_id}/events", headers=headers).json()
    ticket = client.post(f"/api/v1/runs/{run_id}/ws-ticket", headers=headers).json()["ticket"]
    seen = []
    with client.websocket_connect(
        f"/api/v1/runs/{run_id}/ws?ticket={ticket}&after={events[1]['seq']}"
    ) as ws:
        with pytest.raises(WebSocketDisconnect):
            while True:
                seen.append(ws.receive_json())
    assert [e["seq"] for e in seen] == [e["seq"] for e in events[2:]]
    assert seen[-1]["type"] == "run.completed"
    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect(f"/api/v1/runs/not-this-run/ws?ticket={ticket}"):
            pass
    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect(
            f"/api/v1/runs/{run_id}/ws?ticket={ticket}", headers={"origin": "https://evil.example"}
        ):
            pass


def test_csv_and_official_evaluation(client, headers):
    pid = package(client, headers, "Обеспечение заявки:\n18 000 рублей.")
    run_id = client.post("/api/v1/runs", headers=headers, json=run_body(pid)).json()["id"]
    run = wait_run(client, headers, run_id)
    assert run["result"]["answers"][0]["status"] == "ответ"
    response = client.get(f"/api/v1/runs/{run_id}/answers.csv", headers=headers)
    rows = list(csv.DictReader(io.StringIO(response.text), delimiter=";"))
    assert rows[0]["id"] == "P01-01" and "\n" not in rows[0]["quote"]
    reference = {
        "id": "P01-01",
        "package": "P01",
        "status": "ответ",
        "kind": "num",
        "expected": [18000],
        "type": "факт",
    }
    result = client.post(
        f"/api/v1/runs/{run_id}/evaluate", headers=headers, json={"reference_answers": [reference]}
    )
    assert result.status_code == 201, result.text
    assert result.json()["trust_index"] == 100
    assert (
        client.post(
            f"/api/v1/runs/{run_id}/evaluate",
            headers=headers,
            json={"reference_answers": [{**reference, "id": "P02-01"}]},
        ).status_code
        == 422
    )


def archive_bytes(files):
    data = io.BytesIO()
    with zipfile.ZipFile(data, "w") as archive:
        for name, content in files.items():
            archive.writestr(name, content)
    return data.getvalue()


def test_zip_import_never_loads_gold_or_checker(settings, client, headers):
    raw = archive_bytes(
        {
            "school/packages/P01/notice.txt": "Обеспечение: 18000 рублей",
            "school/questions.csv": "id;package;question\nP01-01;P01;Какое обеспечение?\n",
            "school/answers_public.json": '{"SECRET_REFERENCE": 123}',
            "school/check.py": "raise RuntimeError('MUST NEVER EXECUTE')",
        }
    )
    dataset = import_archive(raw, settings)
    assert "SECRET_REFERENCE" not in dataset.model_dump_json()
    response = client.post(
        "/api/v1/datasets/import",
        headers=headers,
        files={"file": ("data.zip", raw, "application/zip")},
    )
    assert response.status_code == 201, response.text
    assert len(response.json()["questions"]) == 1
    with pytest.raises(DomainError):
        import_archive(archive_bytes({"../outside.txt": "bad"}), settings)


def test_snapshot_stable_and_session_serialized(settings, headers):
    async def behavior(kwargs, _):
        await asyncio.sleep(60)
        return reply({"answers": []})

    with TestClient(create_app(settings, FakeModel(behavior))) as client:
        pid = package(client, headers)
        session = client.post("/api/v1/sessions", headers=headers, json={"package_id": pid}).json()
        keyed = {**headers, "Idempotency-Key": "chat/retry-1"}
        response = client.post(
            f"/api/v1/sessions/{session['id']}/messages",
            headers=keyed,
            json={"text": "Какое обеспечение?"},
        )
        assert response.status_code == 202, response.text
        run_id = response.json()["id"]
        same = client.post(
            f"/api/v1/sessions/{session['id']}/messages",
            headers=keyed,
            json={"text": "Какое обеспечение?"},
        )
        assert same.json()["id"] == run_id
        assert (
            client.post(
                f"/api/v1/sessions/{session['id']}/messages",
                headers=headers,
                json={"text": "Ещё вопрос"},
            ).status_code
            == 409
        )
        client.post(
            f"/api/v1/packages/{pid}/documents/text",
            headers=headers,
            json={"name": "amendment.txt", "text": "Новые данные"},
        )
        snapshot = client.get(f"/api/v1/runs/{run_id}/inputs", headers=headers).json()
        assert len(snapshot["snapshot"]["packages"][0]["documents"]) == 1
        assert len(client.get(f"/api/v1/packages/{pid}", headers=headers).json()["documents"]) == 2
        client.post(f"/api/v1/runs/{run_id}/cancel", headers=headers)
        assert wait_run(client, headers, run_id)["status"] == "cancelled"


def test_before_after_comparison_same_input(settings, headers):
    def behavior(kwargs, _):
        if kwargs["messages"][0]["role"] == "user":
            return reply(
                {
                    "answers": [
                        {
                            "id": "P01-01",
                            "status": "ответ",
                            "answer": "99999",
                            "quote": "Обеспечение заявки составляет 18 000 рублей.",
                            "file": "notice.txt",
                        }
                    ]
                }
            )
        if kwargs["messages"][0]["content"].startswith("Review proposed"):
            return reply(
                {"reviews": [{"id": "P01-01", "verdict": "supported", "reason": "Подтверждено"}]}
            )
        body = json.loads(kwargs["messages"][1]["content"])
        return reply(
            {
                "answers": [
                    {
                        "id": "P01-01",
                        "status": "ответ",
                        "answer": "18000",
                        "evidence": [{"span_id": body["sources"][0]["span_id"]}],
                    }
                ]
            }
        )

    with TestClient(create_app(settings, FakeModel(behavior))) as client:
        pid = package(client, headers)
        ids = []
        reference = {
            "id": "P01-01",
            "package": "P01",
            "status": "ответ",
            "kind": "num",
            "expected": [18000],
            "type": "факт",
        }
        for mode in ["baseline", "harness"]:
            run_id = client.post(
                "/api/v1/runs", headers=headers, json=run_body(pid, mode=mode)
            ).json()["id"]
            assert wait_run(client, headers, run_id)["status"] == "completed"
            evaluation = client.post(
                f"/api/v1/runs/{run_id}/evaluate",
                headers=headers,
                json={"reference_answers": [reference]},
            )
            assert evaluation.status_code == 201
            ids.append(evaluation.json()["id"])
        response = client.post(
            "/api/v1/comparisons",
            headers=headers,
            json={"before_evaluation_id": ids[0], "after_evaluation_id": ids[1]},
        )
        assert response.status_code == 200, response.text
        assert response.json()["delta"]["correct"] == 1
        assert response.json()["delta"]["errors"] == -1
        assert response.json()["changed_questions"][0]["id"] == "P01-01"
