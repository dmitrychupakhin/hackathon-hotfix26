import json
import time

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.infrastructure.llm import Reply
from app.main import create_app


class FakeModel:
    def __init__(self, behavior=None):
        self.calls = []
        self.behavior = behavior

    async def complete(self, **kwargs):
        self.calls.append(kwargs)
        if self.behavior:
            value = self.behavior(kwargs, len(self.calls))
            if hasattr(value, "__await__"):
                value = await value
            return value
        messages = kwargs["messages"]
        if messages[0]["content"].startswith("Partition the raw text"):
            return reply({"parts": [messages[-1]["content"]]}, kwargs['model'])
        body = json.loads(messages[-1]["content"])
        if messages[0]["content"].startswith("Review proposed"):
            result = {
                "reviews": [
                    {
                        "id": answer["id"],
                        "verdict": "supported",
                        "reason": "Подтверждено источником",
                    }
                    for answer in body["proposed"]
                ]
            }
        elif kwargs.get("tools"):
            body = next(
                json.loads(m["content"])
                for m in messages
                if m["role"] == "user" and "sources" in json.loads(m["content"])
            )
            result = {
                "answers": [
                    {
                        "id": q["id"],
                        "status": "ответ",
                        "answer": "18000 руб.",
                        "evidence": [{"span_id": body["sources"][0]["span_id"]}],
                    }
                    for q in body["questions"]
                ]
            }
        else:
            raise AssertionError("Provide explicit fake behavior for baseline tests")
        return reply(result, kwargs["model"])


def reply(value, model="test-model", finish="stop"):
    return Reply(
        {"role": "assistant", "content": json.dumps(value, ensure_ascii=False)},
        finish,
        model,
        {"prompt_tokens": 100, "completion_tokens": 20, "total_tokens": 120},
    )


@pytest.fixture
def settings(tmp_path):
    return Settings(
        _env_file=None,
        api_key="test-key",
        model="test-model",
        service_key="s" * 32,
        environment="test",
        database_path=str(tmp_path / "ai.sqlite3"),
        source_root=str(tmp_path / "incoming"),
        file_cache_root=str(tmp_path / "files"),
        max_output_tokens=2000,
    )


@pytest.fixture
def headers():
    return {"X-AI-Service-Key": "s" * 32, "X-User-ID": "user-1"}


@pytest.fixture
def client(settings):
    with TestClient(create_app(settings, FakeModel())) as instance:
        yield instance


def package(client, headers, text="Обеспечение заявки составляет 18 000 рублей."):
    response = client.post(
        "/api/v1/packages", headers=headers, json={"code": "P01", "name": "Test"}
    )
    assert response.status_code == 201, response.text
    package_id = response.json()["id"]
    response = client.post(
        f"/api/v1/packages/{package_id}/documents/text",
        headers=headers,
        json={"name": "notice.txt", "text": text},
    )
    assert response.status_code == 201, response.text
    return package_id


def run_body(package_id, **kwargs):
    return {
        "questions": [
            {"id": "P01-01", "package_id": package_id, "text": "Какой размер обеспечения заявки?"}
        ],
        **kwargs,
    }


def wait_run(client, headers, run_id):
    for _ in range(200):
        response = client.get(f"/api/v1/runs/{run_id}", headers=headers)
        assert response.status_code == 200
        run = response.json()
        if run["status"] in {"completed", "failed", "cancelled", "interrupted"}:
            return run
        time.sleep(0.01)
    pytest.fail("Run did not terminate")
