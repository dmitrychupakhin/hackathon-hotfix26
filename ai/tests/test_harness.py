import asyncio
import json

import pytest
from conftest import FakeModel, package, reply, run_body, wait_run
from fastapi.testclient import TestClient

from app.infrastructure.llm import Reply
from app.main import create_app


def answer_payload(kwargs, quote=None, value="18000"):
    initial = json.loads(kwargs["messages"][1]["content"])
    evidence = {"span_id": initial["sources"][0]["span_id"]}
    if quote is not None:
        evidence["quote"] = quote
    return {
        "answers": [{"id": "P01-01", "status": "ответ", "answer": value, "evidence": [evidence]}]
    }


def test_quote_repair_and_audit(settings, headers):
    def behavior(kwargs, number):
        if kwargs["messages"][0]["content"].startswith("Review proposed"):
            return reply(
                {"reviews": [{"id": "P01-01", "verdict": "supported", "reason": "Подтверждено"}]}
            )
        return reply(answer_payload(kwargs, quote="Выдуманная цитата" if number == 1 else None))

    model = FakeModel(behavior)
    with TestClient(create_app(settings, model)) as client:
        pid = package(client, headers)
        run_id = client.post("/api/v1/runs", headers=headers, json=run_body(pid)).json()["id"]
        run = wait_run(client, headers, run_id)
        assert run["status"] == "completed"
        assert run["result"]["answers"][0]["status"] == "ответ"
        events = client.get(f"/api/v1/runs/{run_id}/events", headers=headers).json()
        assert any(
            e["type"] == "validation.failed" and e["data"]["checks"][0]["code"] == "quote"
            for e in events
        )
        assert any(e["type"] == "repair.started" for e in events)
        assert len(model.calls) == 3


def test_semantic_reviewer_triggers_repair(settings, headers):
    critic_calls = 0

    def behavior(kwargs, number):
        nonlocal critic_calls
        if kwargs["messages"][0]["content"].startswith("Review proposed"):
            critic_calls += 1
            return reply(
                {
                    "reviews": [
                        {
                            "id": "P01-01",
                            "verdict": "revise" if critic_calls == 1 else "supported",
                            "reason": "Проверь изменение значения",
                        }
                    ]
                }
            )
        return reply(answer_payload(kwargs))

    with TestClient(create_app(settings, FakeModel(behavior))) as client:
        pid = package(client, headers)
        run_id = client.post("/api/v1/runs", headers=headers, json=run_body(pid)).json()["id"]
        run = wait_run(client, headers, run_id)
        assert critic_calls == 2
        assert run["result"]["answers"][0]["status"] == "ответ"
        events = client.get(f"/api/v1/runs/{run_id}/events", headers=headers).json()
        assert any(
            e["type"] == "validation.failed" and e["data"]["checks"][0]["method"] == "llm"
            for e in events
        )


@pytest.mark.parametrize("max_calls,max_repairs,expected_calls", [(1, 1, 1), (5, 1, 2), (5, 0, 1)])
def test_bounded_failure_becomes_unknown(settings, headers, max_calls, max_repairs, expected_calls):
    model = FakeModel(
        lambda kwargs, _: reply(answer_payload(kwargs, quote="Несуществующий фрагмент"))
    )
    with TestClient(create_app(settings, model)) as client:
        pid = package(client, headers)
        run_id = client.post(
            "/api/v1/runs",
            headers=headers,
            json=run_body(pid, options={"max_calls": max_calls, "max_repairs": max_repairs}),
        ).json()["id"]
        run = wait_run(client, headers, run_id)
        answer = run["result"]["answers"][0]
        assert answer["status"] == "не знаю" and answer["origin"] == "fallback"
        assert answer["answer"] == answer["quote"] == answer["file"] == ""
        assert len(model.calls) == expected_calls


def test_real_tool_call_read_then_submit(settings, headers):
    def behavior(kwargs, number):
        if number == 1:
            initial = json.loads(kwargs["messages"][1]["content"])
            assert "sources" not in initial
            return Reply(
                {
                    "role": "assistant",
                    "content": None,
                    "tool_calls": [
                        {
                            "id": "read-1",
                            "type": "function",
                            "function": {
                                "name": "read_document",
                                "arguments": json.dumps(
                                    {"document_id": initial["documents"][0]["id"]}
                                ),
                            },
                        }
                    ],
                },
                "tool_calls",
                "test-model",
                {"prompt_tokens": 100, "completion_tokens": 10},
            )
        if number == 2:
            tool = json.loads(kwargs["messages"][-1]["content"])
            data = {
                "answers": [
                    {
                        "id": "P01-01",
                        "status": "ответ",
                        "answer": "18000",
                        "evidence": [{"span_id": tool["blocks"][0]["span_id"]}],
                    }
                ]
            }
            return Reply(
                {
                    "role": "assistant",
                    "content": None,
                    "tool_calls": [
                        {
                            "id": "submit-1",
                            "type": "function",
                            "function": {"name": "submit_answers", "arguments": json.dumps(data)},
                        }
                    ],
                },
                "tool_calls",
                "test-model",
                {"prompt_tokens": 100, "completion_tokens": 20},
            )
        return reply(
            {"reviews": [{"id": "P01-01", "verdict": "supported", "reason": "Источник проверен"}]}
        )

    with TestClient(create_app(settings, FakeModel(behavior))) as client:
        pid = package(client, headers)
        run_id = client.post(
            "/api/v1/runs", headers=headers, json=run_body(pid, options={"context": "retrieval"})
        ).json()["id"]
        run = wait_run(client, headers, run_id)
        assert run["status"] == "completed"
        assert run["result"]["answers"][0]["answer"] == "18000"
        assert run["metrics"]["model_calls"] == 3


def test_baseline_is_one_user_message_and_has_no_critic(settings, headers):
    def behavior(kwargs, _):
        assert len(kwargs["messages"]) == 1 and kwargs["messages"][0]["role"] == "user"
        assert not kwargs.get("tools")
        return reply(
            {
                "answers": [
                    {
                        "id": "P01-01",
                        "status": "ответ",
                        "answer": "18000",
                        "quote": "Обеспечение заявки составляет 18 000 рублей.",
                        "file": "notice.txt",
                    }
                ]
            }
        )

    model = FakeModel(behavior)
    with TestClient(create_app(settings, model)) as client:
        pid = package(client, headers)
        run_id = client.post(
            "/api/v1/runs", headers=headers, json=run_body(pid, mode="baseline")
        ).json()["id"]
        assert wait_run(client, headers, run_id)["status"] == "completed"
        assert len(model.calls) == 1


def test_raw_does_not_invent_status_or_citations(settings, headers):
    def behavior(kwargs, _):
        assert set(json.loads(kwargs["messages"][0]["content"])) == {"documents", "questions"}
        return Reply(
            {"role": "assistant", "content": "- **P01-01:** 18000 рублей"},
            model="test-model",
            usage={"prompt_tokens": 100, "completion_tokens": 20},
        )

    with TestClient(create_app(settings, FakeModel(behavior))) as client:
        pid = package(client, headers)
        run_id = client.post(
            "/api/v1/runs", headers=headers, json=run_body(pid, mode="raw")
        ).json()["id"]
        answer = wait_run(client, headers, run_id)["result"]["answers"][0]
        assert answer["status"] is None
        assert answer["quote"] == answer["file"] == ""
        assert answer["answer"] == "18000 рублей"


def test_truncated_model_output_is_recorded_not_accepted(settings, headers):
    model = FakeModel(lambda kwargs, _: reply({"answers": []}, finish="length"))
    with TestClient(create_app(settings, model)) as client:
        pid = package(client, headers)
        run_id = client.post(
            "/api/v1/runs", headers=headers, json=run_body(pid, mode="baseline")
        ).json()["id"]
        run = wait_run(client, headers, run_id)
        assert run["status"] == "failed" and run["error"]["code"] == "output_truncated"
        assert run["result"]["raw_outputs"]
        assert run["metrics"]["known_total_tokens"] == 120


def test_cancel_does_not_continue_provider_calls(settings, headers):
    async def behavior(kwargs, _):
        await asyncio.sleep(60)
        return reply({"answers": []})

    model = FakeModel(behavior)
    with TestClient(create_app(settings, model)) as client:
        pid = package(client, headers)
        run_id = client.post("/api/v1/runs", headers=headers, json=run_body(pid)).json()["id"]
        client.post(f"/api/v1/runs/{run_id}/cancel", headers=headers)
        run = wait_run(client, headers, run_id)
        assert run["status"] == "cancelled"
        assert len(model.calls) <= 1
