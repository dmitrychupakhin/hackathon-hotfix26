import csv
import io
import json

import pytest
from conftest import FakeModel, package, reply, run_body, wait_run
from fastapi.testclient import TestClient

from app.infrastructure.llm import Reply
from app.main import create_app

PROFILE = "Ты помощник по закупкам. Используй документы и отвечай по-русски."


def wrong_answer(kwargs, _):
    if kwargs.get("tools"):
        body = json.loads(kwargs["messages"][-1]["content"])
        return reply(
            {
                "answers": [
                    {
                        "id": body["questions"][0]["id"],
                        "status": "ответ",
                        "answer": "999 рублей",
                        "evidence": [{"span_id": body["sources"][0]["span_id"]}],
                    }
                ]
            }
        )
    body = json.loads(kwargs["messages"][-1]["content"].split("\n\n", 1)[1])
    return reply(
        {
            "answers": [
                {
                    "id": q["id"],
                    "status": "ответ",
                    "answer": "999 рублей",
                    "quote": "Придуманная цитата",
                    "file": "missing.txt",
                }
                for q in body["questions"]
            ]
        }
    )


@pytest.mark.parametrize("endpoint", ["runs", "dataset", "chat"])
@pytest.mark.parametrize("mode", ["plain", "harness"])
def test_plain_and_harness_share_http_contract_but_not_fact_checks(
    settings, headers, endpoint, mode
):
    model = FakeModel(wrong_answer)
    with TestClient(create_app(settings, model)) as client:
        pid = package(client, headers)
        options = {
            "max_calls": 2,
            "max_repairs": 0,
            "max_rounds_per_package": 1,
            "semantic_review": False,
        }
        common = {"mode": mode, "system_prompt": PROFILE, "options": options}
        if endpoint == "runs":
            response = client.post("/api/v1/runs", headers=headers, json=run_body(pid, **common))
        elif endpoint == "dataset":
            dataset = client.post(
                "/api/v1/datasets",
                headers=headers,
                json={
                    "name": "Режимы",
                    "packages": [
                        {
                            "code": "P01",
                            "name": "Test",
                            "documents": [
                                {
                                    "name": "notice.txt",
                                    "text": "Обеспечение заявки составляет 18 000 рублей.",
                                }
                            ],
                        }
                    ],
                    "questions": [
                        {
                            "id": "P01-01",
                            "package": "P01",
                            "question": "Какой размер обеспечения заявки?",
                        }
                    ],
                },
            )
            assert dataset.status_code == 201, dataset.text
            response = client.post(
                f"/api/v1/datasets/{dataset.json()['id']}/runs", headers=headers, json=common
            )
        else:
            session = client.post("/api/v1/sessions", headers=headers, json={"package_id": pid})
            assert session.status_code == 201, session.text
            response = client.post(
                f"/api/v1/sessions/{session.json()['id']}/messages",
                headers=headers,
                json={
                    **common,
                    "text": "Какой размер обеспечения заявки?",
                    "question_id": "P01-01",
                },
            )
        assert response.status_code == 202, response.text
        run = wait_run(client, headers, response.json()["id"])
        assert run["status"] == "completed", run
        assert run["mode"] == mode
        assert run["system_prompt_source"] == "profile"
        assert len(model.calls) == 1
        assert model.calls[0]["messages"][0] == {"role": "system", "content": PROFILE}
        answer = run["result"]["answers"][0]
        if mode == "plain":
            assert len(model.calls[0]["messages"]) == 2
            assert model.calls[0]["messages"][1]["role"] == "user"
            assert model.calls[0].get("tools") is None
            assert answer["answer"] == "999 рублей"
            assert answer["quote"] == "Придуманная цитата"
            assert answer["checks"] == []
            assert answer["evidence"] == []
        else:
            assert model.calls[0]["tools"]
            assert answer["status"] == "не знаю"
            assert answer["answer"] == ""
        events = client.get(f"/api/v1/runs/{run['id']}/events", headers=headers).json()
        assert "answer.completed" in {event["type"] for event in events}
        if mode == "plain":
            assert not any(
                event["type"].startswith(("validation.", "review.", "repair.", "tool."))
                for event in events
            )
            steps = [event["data"] for event in events if event["type"] == "harness.step"]
            assert any(step["kind"] == "plain" and step["status"] == "completed" for step in steps)
        csv_response = client.get(f"/api/v1/runs/{run['id']}/answers.csv", headers=headers)
        assert csv_response.status_code == 200
        rows = list(csv.DictReader(io.StringIO(csv_response.text), delimiter=";"))
        assert rows[0]["answer"] == answer["answer"]


def test_plain_bad_format_is_preserved_without_a_repair_call(settings, headers):
    model = FakeModel(lambda _kwargs, _count: reply({"answer": "999"}))
    with TestClient(create_app(settings, model)) as client:
        pid = package(client, headers)
        response = client.post("/api/v1/runs", headers=headers, json=run_body(pid, mode="plain"))
        run = wait_run(client, headers, response.json()["id"])
        assert run["status"] == "failed"
        assert run["error"]["code"] == "plain_format_invalid"
        assert run["result"]["raw_outputs"][0]["message"]["content"]
        assert run["result"]["answers"][0]["status"] == "не знаю"
        assert len(model.calls) == 1


@pytest.mark.parametrize("mode", ["raw", "baseline"])
def test_legacy_modes_keep_no_system_message(settings, headers, mode):
    def behavior(kwargs, _):
        if mode == "raw":
            return Reply(
                {"role": "assistant", "content": "- P01-01: 999 рублей"}, "stop", "test-model", {}
            )
        return wrong_answer(kwargs, 1)

    model = FakeModel(behavior)
    with TestClient(create_app(settings, model)) as client:
        pid = package(client, headers)
        request = run_body(pid, mode=mode)
        response = client.post("/api/v1/runs", headers=headers, json=request)
        run = wait_run(client, headers, response.json()["id"])
        assert run["status"] == "completed", run
        assert run["system_prompt_source"] == "not_used"
        assert len(model.calls) == 1
        assert len(model.calls[0]["messages"]) == 1
        assert model.calls[0]["messages"][0]["role"] == "user"
        assert model.calls[0].get("tools") is None
        invalid = client.post(
            "/api/v1/runs", headers=headers, json={**request, "system_prompt": PROFILE}
        )
        assert invalid.status_code == 422


def test_chat_rejects_legacy_modes(client, headers):
    pid = package(client, headers)
    session = client.post("/api/v1/sessions", headers=headers, json={"package_id": pid}).json()
    for mode in ["raw", "baseline"]:
        assert (
            client.post(
                f"/api/v1/sessions/{session['id']}/messages",
                headers=headers,
                json={"mode": mode, "text": "Вопрос"},
            ).status_code
            == 422
        )
