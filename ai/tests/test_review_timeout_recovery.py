import json
from uuid import uuid4

import pytest
from conftest import FakeModel, reply, wait_run
from fastapi.testclient import TestClient
from test_file_preview import source
from test_scan_recovery import setup_engine

from app.domain import DomainError
from app.main import create_app


@pytest.mark.asyncio
async def test_transient_verification_failure_retries_same_batch_only(settings):
    bodies = []
    failed = False

    def behavior(kwargs, _):
        nonlocal failed
        body = json.loads(kwargs["messages"][-1]["content"])
        bodies.append(body)
        if len(bodies) == 3 and not failed:
            failed = True
            raise DomainError("upstream_timeout", "Provider timed out", 502)
        return reply({"selections": [{"id": q["id"], "span_ids": []} for q in body["questions"]]})

    engine, _, questions, tools, events = setup_engine(settings, behavior, large=True)
    await engine._scan(tools, questions, proposed=[])
    assert failed and bodies[2] == bodies[3]
    assert len(bodies) == engine.scan_coverage["verification_scan"]["batches_total"] + 1
    assert engine.scan_coverage["verification_scan"]["complete"]
    retries = [data for kind, data in events if kind == "review.retry"]
    assert len(retries) == 1 and retries[0]["error_code"] == "upstream_timeout"


@pytest.mark.asyncio
async def test_chat_keeps_code_checked_answer_after_two_reviewer_timeouts(settings):
    calls = {"answer": 0, "critic": 0}

    def behavior(kwargs, _):
        body = json.loads(kwargs["messages"][-1]["content"])
        if kwargs["messages"][0]["content"].startswith("Review proposed"):
            calls["critic"] += 1
            raise DomainError("upstream_timeout", "Provider timed out", 502)
        calls["answer"] += 1
        return reply(
            {
                "answers": [
                    {
                        "id": q["id"],
                        "status": "ответ",
                        "answer": "18000 рублей",
                        "evidence": [{"span_id": body["sources"][0]["span_id"]}],
                    }
                    for q in body["questions"]
                ]
            }
        )

    engine, package, _, _, events = setup_engine(settings, behavior)
    engine.chat_return_code_checked = True
    answers = await engine.execute([package])
    assert calls == {"answer": 1, "critic": 2}
    assert all(a.status == "ответ" and a.answer == "18000 рублей" and a.evidence for a in answers)
    assert all(a.reason == "independent_review_incomplete" for a in answers)
    assert all(all(c.passed for c in a.checks if c.method == "code") for a in answers)
    assert all(
        any(c.code == "review_unavailable" and not c.passed for c in a.checks) for a in answers
    )
    assert not any(kind == "repair.started" for kind, _ in events)


@pytest.mark.asyncio
async def test_chat_never_returns_answer_that_failed_code_checks(settings):
    def behavior(kwargs, _):
        assert not kwargs["messages"][0]["content"].startswith("Review proposed")
        body = json.loads(next(m["content"] for m in kwargs["messages"] if m["role"] == "user"))
        return reply(
            {
                "answers": [
                    {
                        "id": q["id"],
                        "status": "ответ",
                        "answer": "99999 рублей",
                        "evidence": [{"span_id": body["sources"][0]["span_id"]}],
                    }
                    for q in body["questions"]
                ]
            }
        )

    engine, package, _, _, _ = setup_engine(settings, behavior)
    engine.chat_return_code_checked = True
    answers = await engine.execute([package])
    assert all(a.status == "не знаю" and not a.answer for a in answers)


def test_chat_route_preserves_answer_and_file_anchor_on_review_timeout(settings, headers):
    calls = []

    def behavior(kwargs, _):
        system = kwargs["messages"][0]["content"]
        if system.startswith("Partition the raw text"):
            return reply({"parts": [kwargs["messages"][-1]["content"]]})
        body = json.loads(kwargs["messages"][-1]["content"])
        if system.startswith("Review proposed"):
            calls.append("critic")
            raise DomainError("upstream_timeout", "Provider timed out", 502)
        return reply(
            {
                "answers": [
                    {
                        "id": q["id"],
                        "status": "ответ",
                        "answer": "18000 рублей",
                        "evidence": [{"span_id": body["sources"][0]["span_id"]}],
                    }
                    for q in body["questions"]
                ]
            }
        )

    with TestClient(create_app(settings, FakeModel(behavior))) as client:
        record, _ = source(client, settings)
        response = client.post(
            "/api/v1/chat-runs",
            headers=headers,
            json={
                "chat_id": str(uuid4()),
                "message_id": str(uuid4()),
                "model": "test-model",
                "file_ids": [record["id"]],
                "question": "Какой размер обеспечения?",
            },
        )
        assert response.status_code == 202
        run = wait_run(client, headers, response.json()["id"])
        answer = run["result"]["answers"][0]
        assert calls == ["critic", "critic"]
        assert run["status"] == "completed" and answer["status"] == "ответ"
        assert answer["answer"] == "18000 рублей"
        assert answer["evidence"][0]["source_file_id"] == record["id"]
        assert answer["reason"] == "independent_review_incomplete"
        assert any(not c["passed"] for c in answer["checks"] if c["method"] == "llm")
