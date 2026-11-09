import asyncio
import hashlib
import json
from pathlib import Path
from uuid import uuid4

import pytest
from conftest import FakeModel, package, reply, run_body, wait_run
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from app.domain import DomainError, HarnessStep, now
from app.infrastructure.llm import Reply
from app.main import create_app
from app.services.progress import Progress


def steps(events):
    return [HarnessStep.model_validate(e["data"]) for e in events if e["type"] == "harness.step"]


def test_successful_steps_are_persisted_and_replayed(client, headers):
    pid = package(client, headers)
    run_id = client.post("/api/v1/runs", headers=headers, json=run_body(pid)).json()["id"]
    wait_run(client, headers, run_id)
    events = client.get(f"/api/v1/runs/{run_id}/events", headers=headers).json()
    timeline = steps(events)
    assert {s.kind for s in timeline} >= {
        "prepare",
        "answer",
        "validation",
        "semantic_review",
        "result",
    }
    starts = {s.step_id: s for s in timeline if s.status == "started"}
    ends = {s.step_id: s for s in timeline if s.status != "started"}
    assert starts.keys() == ends.keys()
    assert all(s.status == "completed" and s.elapsed_seconds >= 0 for s in ends.values())
    assert all(s.package_id == pid for s in timeline)
    assert not any(
        "18 000" in s.model_dump_json() or "test-key" in s.model_dump_json() for s in timeline
    )
    cursor = next(e["seq"] for e in events if e["type"] == "harness.step")
    ticket = client.post(f"/api/v1/runs/{run_id}/ws-ticket", headers=headers).json()["ticket"]
    replay = []
    with client.websocket_connect(f"/api/v1/runs/{run_id}/ws?ticket={ticket}&after={cursor}") as ws:
        with pytest.raises(WebSocketDisconnect):
            while True:
                replay.append(ws.receive_json())
    assert replay == [e for e in events if e["seq"] > cursor]
    assert replay[-1]["type"] == "run.completed"


def test_steps_arrive_while_model_is_running_and_close_on_cancel(settings, headers):
    async def slow_model(kwargs, _):
        await asyncio.sleep(60)
        return reply({"answers": []})

    with TestClient(create_app(settings, FakeModel(slow_model))) as client:
        pid = package(client, headers)
        run_id = client.post("/api/v1/runs", headers=headers, json=run_body(pid)).json()["id"]
        received = []
        with client.websocket_connect(f"/api/v1/runs/{run_id}/ws", headers=headers) as ws:
            for _ in range(30):
                event = ws.receive_json()
                received.append(event)
                if event["type"] == "harness.step" and event["data"]["kind"] == "answer":
                    assert event["data"]["status"] == "started"
                    break
            else:
                pytest.fail("No live generation step")
            assert (
                client.get(f"/api/v1/runs/{run_id}", headers=headers).json()["status"] == "running"
            )
            client.post(f"/api/v1/runs/{run_id}/cancel", headers=headers)
            with pytest.raises(WebSocketDisconnect):
                while True:
                    received.append(ws.receive_json())
        timeline = steps(received)
        assert any(s.kind == "answer" and s.status == "cancelled" for s in timeline)
        assert {s.step_id for s in timeline if s.status == "started"} == {
            s.step_id for s in timeline if s.status != "started"
        }
        assert received[-1]["type"] == "run.cancelled"


def test_validation_failure_and_repair_steps(settings, headers):
    def behavior(kwargs, _):
        body = json.loads(kwargs["messages"][1]["content"])
        return reply(
            {
                "answers": [
                    {
                        "id": "P01-01",
                        "status": "ответ",
                        "answer": "999",
                        "evidence": [{"span_id": body["sources"][0]["span_id"]}],
                    }
                ]
            }
        )

    with TestClient(create_app(settings, FakeModel(behavior))) as client:
        pid = package(client, headers)
        run_id = client.post("/api/v1/runs", headers=headers, json=run_body(pid)).json()["id"]
        run = wait_run(client, headers, run_id)
        assert run["result"]["answers"][0]["status"] == "не знаю"
        timeline = steps(client.get(f"/api/v1/runs/{run_id}/events", headers=headers).json())
        assert any(
            s.kind == "validation"
            and s.status == "failed"
            and "numbers" in s.details["failed_checks"]
            for s in timeline
        )
        assert any(
            s.kind == "repair" and s.details == {"attempt": 1, "max_repairs": 1} for s in timeline
        )


def test_provider_failure_closes_generation_step(settings, headers):
    def behavior(kwargs, _):
        raise DomainError("provider_unavailable", "PRIVATE ERROR CONTENT", 503)

    with TestClient(create_app(settings, FakeModel(behavior))) as client:
        pid = package(client, headers)
        run_id = client.post("/api/v1/runs", headers=headers, json=run_body(pid)).json()["id"]
        assert wait_run(client, headers, run_id)["status"] == "failed"
        timeline = steps(client.get(f"/api/v1/runs/{run_id}/events", headers=headers).json())
        assert any(s.kind == "answer" and s.status == "failed" for s in timeline)
        assert all("PRIVATE" not in s.model_dump_json() for s in timeline)


@pytest.mark.asyncio
async def test_scan_progress_and_interrupted_cleanup():
    events = []

    async def emit(kind, data):
        events.append({"type": kind, "data": data})

    progress = Progress(emit)
    await progress.handle(
        "llm.started",
        {
            "stage": "verification_scan",
            "call": 9,
            "max_calls": 48,
            "progress": {"batch": 2, "batches": 7},
        },
    )
    await progress.close("interrupted", {"code": "service_shutdown"})
    timeline = steps(events)
    assert timeline[0].details == {"call": 9, "max_calls": 48, "batch": 2, "batches": 7}
    assert timeline[-1].status == "interrupted"
    assert timeline[-1].step_id == timeline[0].step_id


def test_backend_chat_run_streams_real_tools_checks_and_terminal(settings, headers):
    """Exercise the same file-ID entry point used by the Django chat worker."""
    default_model = FakeModel()

    async def behavior(kwargs, call):
        if call == 2:
            await asyncio.sleep(0.05)
            return Reply(
                {
                    "role": "assistant",
                    "content": None,
                    "tool_calls": [
                        {
                            "id": "list-call",
                            "type": "function",
                            "function": {"name": "list_documents", "arguments": "{}"},
                        }
                    ],
                },
                "tool_calls",
                "test-model",
                {"prompt_tokens": 100, "completion_tokens": 20, "total_tokens": 120},
            )
        return await default_model.complete(**kwargs)

    with TestClient(create_app(settings, FakeModel(behavior))) as client:
        file_id = str(uuid4())
        root = Path(settings.source_root)
        root.mkdir(exist_ok=True)
        source = root / "notice.txt"
        source.write_text("Обеспечение заявки составляет 18 000 рублей.")
        client.portal.call(
            client.app.state.store.create,
            "source_file",
            {
                "id": file_id,
                "owner": "user-1",
                "version": "v1",
                "updated_at": now(),
                "filename": "notice.txt",
                "relative_path": "notice.txt",
                "sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
                "media_type": "text/plain",
            },
            "user-1",
        )
        response = client.post(
            "/api/v1/chat-runs",
            headers=headers,
            json={
                "chat_id": str(uuid4()),
                "message_id": str(uuid4()),
                "question": "Какой размер обеспечения заявки?",
                "file_ids": [file_id],
                "model": "test-model",
            },
        )
        assert response.status_code == 202, response.text
        run_id = response.json()["id"]
        ticket = client.post(f"/api/v1/runs/{run_id}/ws-ticket", headers=headers).json()
        received = []
        with client.websocket_connect(ticket["path"] + "?ticket=" + ticket["ticket"]) as ws:
            with pytest.raises(WebSocketDisconnect):
                while True:
                    received.append(ws.receive_json())
        assert received[-1]["type"] == "run.completed"
        timeline = steps(received)
        assert {step.kind for step in timeline} >= {
            "prepare",
            "answer",
            "tool",
            "validation",
            "semantic_review",
            "result",
        }
        assert any(
            step.kind == "tool"
            and step.details.get("tool") == "list_documents"
            and step.status == "completed"
            for step in timeline
        )
        assert any(event["type"] == "answer.completed" for event in received)
        assert all("test-key" not in step.model_dump_json() for step in timeline)
        run = client.get(f"/api/v1/runs/{run_id}", headers=headers).json()
        assert run["status"] == "completed"
        assert run["result"]["answers"][0]["answer"] == "18000 руб."
