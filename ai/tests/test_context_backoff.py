import asyncio
import json

import httpx
import pytest
from conftest import FakeModel, package, reply, run_body, wait_run
from fastapi.testclient import TestClient

from app.domain import DomainError, Package, Question, RunCreate, TextDocument
from app.infrastructure.llm import ApiMira
from app.main import create_app
from app.services.documents import document_from_text, with_documents
from app.services.harness import Harness
from app.services.model_limits import context_budget


@pytest.mark.asyncio
async def test_provider_context_metadata_is_validated(settings):
    def handler(request):
        assert request.url.path.endswith("/models")
        assert request.headers["authorization"] == "Bearer test-key"
        return httpx.Response(
            200,
            json={
                "data": [
                    {"id": "test-model", "context_window": 266000, "context_length": 270000},
                    {"id": "test-model", "context_window": "invalid"},
                    {"id": "unknown", "context_window": 999999},
                ]
            },
        )

    model = ApiMira(settings, httpx.MockTransport(handler))
    try:
        # The model picker can select any operator-enabled provider model, not
        # only the default configured model. Invalid metadata is still ignored.
        assert await model.context_windows() == {"test-model": 266000, "unknown": 999999}
    finally:
        await model.close()


@pytest.mark.asyncio
async def test_metadata_failure_uses_conservative_fallback(settings):
    model = ApiMira(
        settings, httpx.MockTransport(lambda _: httpx.Response(503, text="private provider body"))
    )
    try:
        windows = await model.context_windows()
        assert windows == {}
        assert context_budget(settings, "test-model", windows)["context_window_tokens"] == 160000
    finally:
        await model.close()
    assert (
        context_budget(settings, "test-model", {"test-model": 8192})["context_window_tokens"]
        == 8192
    )
    assert (
        context_budget(settings, "test-model", {"test-model": 1000000})["context_window_tokens"]
        == 266000
    )


def test_run_freezes_model_context_budget(settings, headers):
    with TestClient(create_app(settings, FakeModel())) as client:
        client.app.state.runner.context_windows["test-model"] = 266000
        pid = package(client, headers)
        run_id = client.post("/api/v1/runs", headers=headers, json=run_body(pid)).json()["id"]
        run = wait_run(client, headers, run_id)
        assert run["context_budget"]["context_window_tokens"] == 266000
        assert run["context_budget"]["source"] == "provider"
        client.app.state.runner.context_windows["test-model"] = 8192
        snapshot = client.get(f"/api/v1/runs/{run_id}/inputs", headers=headers).json()["snapshot"]
        assert snapshot["context_budget"]["context_window_tokens"] == 266000
        info = client.get("/api/v1/info", headers=headers).json()
        assert info["limits"]["context_window_tokens"] == 8192
        assert run["metrics"]["context_window_tokens_final"] == 266000


def big_package(settings):
    return with_documents(
        Package(code="P01", name="Context test"),
        [
            document_from_text(
                TextDocument(
                    name="notice.txt",
                    text="Общие условия исполнения. " * 2500 + "\nОбеспечение: 18000 рублей.",
                ),
                settings,
            )
        ],
        settings,
    )


def successful_reply(kwargs):
    body = json.loads(kwargs["messages"][-1]["content"])
    system = kwargs["messages"][0]["content"]
    if system.startswith("Scan ORIGINAL"):
        return reply(
            {
                "selections": [
                    {
                        "id": q["id"],
                        "span_ids": [s["span_id"] for s in body["sources"] if "18000" in s["text"]],
                    }
                    for q in body["questions"]
                ]
            }
        )
    if system.startswith("Review proposed"):
        return reply(
            {
                "reviews": [
                    {"id": a["id"], "verdict": "supported", "reason": "Подтверждено"}
                    for a in body["proposed"]
                ]
            }
        )
    body = json.loads(kwargs["messages"][1]["content"])
    span = next(s for s in body["sources"] if "18000" in s["text"])
    return reply(
        {
            "answers": [
                {
                    "id": q["id"],
                    "status": "ответ",
                    "answer": "18000 рублей",
                    "evidence": [
                        {"span_id": span["span_id"], "quote": "Обеспечение: 18000 рублей."}
                    ],
                }
                for q in body["questions"]
            ]
        }
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("failure_stage", ["initial_and_scan", "critic"])
async def test_context_error_replans_smaller_batches_and_recovers(settings, failure_stage):
    source = big_package(settings)
    events = []
    failures = 0

    async def emit(kind, data):
        events.append({"type": kind, "data": data})

    def behavior(kwargs, number):
        nonlocal failures
        fail = (
            number <= 2
            if failure_stage == "initial_and_scan"
            else kwargs["messages"][0]["content"].startswith("Review proposed") and failures == 0
        )
        if fail:
            failures += 1
            raise DomainError("context_length_exceeded", "Provider rejected size", 502)
        return successful_reply(kwargs)

    request = RunCreate(
        questions=[Question(id="q1", package_id=source.id, text="Какое обеспечение?")]
    )
    engine = Harness(FakeModel(behavior), settings, request, emit, asyncio.Event())
    result = await engine.execute([source])
    assert result[0].status == "ответ"
    reductions = [e["data"] for e in events if e["type"] == "context.reduced"]
    assert len(reductions) == failures
    for reduction in reductions:
        assert (
            reduction["context_window_tokens"] <= reduction["previous_context_window_tokens"] // 2
        )
        assert reduction["context_window_tokens"] <= reduction["failed_input_estimate"] // 2
    assert any(e["type"] == "context.batch_scanned" for e in events)
    assert source.documents[0].text.endswith("Обеспечение: 18000 рублей.")
    assert engine.usage.calls <= request.options.max_calls


@pytest.mark.asyncio
async def test_context_retry_limit_stops_instead_of_looping(settings):
    settings = settings.model_copy(update={"max_context_reductions": 1})
    source = big_package(settings)

    async def emit(*args):
        pass

    def behavior(kwargs, number):
        raise DomainError("context_length_exceeded", "Too large", 502)

    request = RunCreate(
        questions=[Question(id="q1", package_id=source.id, text="Какое обеспечение?")]
    )
    engine = Harness(FakeModel(behavior), settings, request, emit, asyncio.Event())
    result = await engine.execute([source])
    assert engine.usage.calls == 2
    assert engine.context_reductions == 1
    assert result[0].status == "не знаю" and result[0].reason == "context_retry_exhausted"


@pytest.mark.asyncio
async def test_other_provider_errors_do_not_shrink_or_retry(settings):
    source = big_package(settings)

    async def emit(*args):
        pass

    def behavior(kwargs, number):
        raise DomainError("rate_limited", "Too many requests", 429)

    engine = Harness(
        FakeModel(behavior),
        settings,
        RunCreate(questions=[Question(id="q1", package_id=source.id, text="Вопрос")]),
        emit,
        asyncio.Event(),
    )
    with pytest.raises(DomainError, match="Too many requests"):
        await engine.execute([source])
    assert engine.context_reductions == 0 and engine.usage.calls == 1


@pytest.mark.asyncio
async def test_small_window_cannot_reduce_forever(settings):
    async def emit(*args):
        pass

    engine = Harness(
        FakeModel(),
        settings,
        RunCreate(questions=[Question(id="q1", package_id="p", text="Вопрос")]),
        emit,
        asyncio.Event(),
    )
    with pytest.raises(DomainError) as exc:
        await engine.reduce_context(7000)
    assert exc.value.code == "context_retry_exhausted"
    assert engine.context_reductions == 0


@pytest.mark.asyncio
async def test_context_replan_preserves_previously_accepted_answers(settings):
    source = big_package(settings)
    events = []
    generated_groups = []
    critic_failed = False

    async def emit(kind, data):
        events.append({"type": kind, "data": data})

    def behavior(kwargs, _):
        nonlocal critic_failed
        if kwargs["messages"][0]["content"].startswith("Review proposed") and not critic_failed:
            critic_failed = True
            raise DomainError("context_length_exceeded", "Too large", 502)
        result = successful_reply(kwargs)
        if kwargs.get("tools"):
            payload = json.loads(result.message["content"])
            generated_groups.append([a["id"] for a in payload["answers"]])
            for answer in payload["answers"]:
                if answer["id"] == "q1":
                    answer.update(status="не знаю", answer="", evidence=[])
            return reply(payload)
        return result

    request = RunCreate(
        questions=[Question(id=qid, package_id=source.id, text="Вопрос") for qid in ["q1", "q2"]]
    )
    engine = Harness(FakeModel(behavior), settings, request, emit, asyncio.Event())
    result = await engine.execute([source])
    assert [a.status for a in result] == ["не знаю", "ответ"]
    assert generated_groups[0] == ["q1", "q2"]
    assert all(group == ["q2"] for group in generated_groups[1:])
    assert (
        sum(e["type"] == "answer.completed" and e["data"]["answer"]["id"] == "q1" for e in events)
        == 1
    )
    assert engine.answer_rounds[source.id] <= request.options.max_rounds_per_package


@pytest.mark.asyncio
async def test_reduction_events_have_public_steps():
    from app.services.progress import Progress

    events = []

    async def emit(kind, data):
        events.append({"type": kind, "data": data})

    progress = Progress(emit)
    await progress.handle(
        "context.reduced",
        {
            "previous_context_window_tokens": 266000,
            "context_window_tokens": 120000,
            "attempt": 1,
            "max_attempts": 5,
        },
    )
    await progress.handle(
        "context.reduction_exhausted",
        {"attempt": 5, "max_attempts": 5, "reason": "context_retry_exhausted"},
    )
    assert [e["data"]["status"] for e in events] == ["started", "completed", "started", "failed"]
    assert all(
        e["type"] == "harness.step" and e["data"]["kind"] == "context_reduction" for e in events
    )
