from uuid import uuid4

import pytest
from conftest import FakeModel, reply, wait_run
from fastapi.testclient import TestClient
from test_file_preview import source

from app.main import create_app


@pytest.mark.parametrize("server_timeout,document_timeout", [(1200, 1200), (90, 90), (7200, 3600)])
def test_document_chat_uses_bounded_server_deadline(settings, headers, server_timeout, document_timeout):
    settings = settings.model_copy(update={"run_timeout": server_timeout})
    with TestClient(create_app(settings, FakeModel())) as client:
        record, _ = source(client, settings)
        response = client.post("/api/v1/chat-runs", headers=headers, json={
            "chat_id": str(uuid4()), "message_id": str(uuid4()),
            "model": "test-model", "file_ids": [record["id"]],
            "question": "Какой размер обеспечения?",
        })
        assert response.status_code == 202, response.text
        run = wait_run(client, headers, response.json()["id"])
        assert run["status"] == "completed", run.get("error")
        assert run["request"]["options"]["timeout_seconds"] == document_timeout
        limits = client.get("/api/v1/info", headers=headers).json()["limits"]
        assert limits["chat_document_timeout_seconds"] == document_timeout
        assert limits["chat_plain_timeout_seconds"] == min(server_timeout, 600)


def test_plain_chat_keeps_short_default_deadline(settings, headers):
    message_id = str(uuid4())
    model = FakeModel(lambda _kwargs, _count: reply({"answers": [{
        "id": message_id, "status": "ответ", "answer": "Здравствуйте.",
        "quote": "", "file": "",
    }]}))
    with TestClient(create_app(settings, model)) as client:
        response = client.post("/api/v1/chat-runs", headers=headers, json={
            "chat_id": str(uuid4()), "message_id": message_id,
            "model": "test-model", "question": "Привет",
        })
        assert response.status_code == 202, response.text
        run = wait_run(client, headers, response.json()["id"])
        assert run["status"] == "completed", run.get("error")
        assert run["request"]["options"]["timeout_seconds"] == 600
        assert len(model.calls) == 1
        description = client.get("/openapi.json").json()["paths"]["/api/v1/chat-runs"]["post"]["description"]
        assert "1200" in description and "3600" in description and "600" in description
