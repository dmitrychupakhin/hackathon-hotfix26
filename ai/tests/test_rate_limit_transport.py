import asyncio
import json

import httpx
import pytest

from app.domain import DomainError, Question, RunCreate
from app.infrastructure.llm import ApiMira
from app.services.harness import Harness


@pytest.mark.asyncio
async def test_only_429_retries_with_retry_after_and_records_http_attempts(settings, monkeypatch):
    delays, bodies = [], []

    async def sleep(seconds):
        delays.append(seconds)

    monkeypatch.setattr("app.infrastructure.llm.asyncio.sleep", sleep)

    def handler(request):
        bodies.append(json.loads(request.content))
        if len(bodies) < 3:
            return httpx.Response(
                429, headers={"Retry-After": "2"}, json={"error": {"code": "rate_limit_exceeded"}}
            )
        return httpx.Response(
            200,
            json={
                "choices": [{"message": {"content": "ok"}, "finish_reason": "stop"}],
                "model": "test-model",
                "usage": {"prompt_tokens": 1, "completion_tokens": 1},
            },
        )

    model = ApiMira(
        settings.model_copy(update={"enable_thinking": False}), httpx.MockTransport(handler)
    )
    try:
        result = await model.complete(
            model="test-model", messages=[{"role": "user", "content": "test"}], max_tokens=256
        )
        assert result.transport_attempts == 3
        assert delays == [2, 2]
        assert bodies[0] == bodies[1] == bodies[2]
        assert bodies[0]["enable_thinking"] is False
    finally:
        await model.close()


@pytest.mark.asyncio
async def test_429_attempts_share_harness_budget_and_do_not_loop(settings):
    requests = []

    def handler(request):
        requests.append(request)
        return httpx.Response(
            429, headers={"Retry-After": "0"}, json={"error": {"code": "rate_limited"}}
        )

    model = ApiMira(settings, httpx.MockTransport(handler))

    async def emit(*_):
        pass

    request = RunCreate(
        questions=[Question(id="q", package_id="p", text="test")], options={"max_calls": 2}
    )
    engine = Harness(model, settings, request, emit, asyncio.Event())
    try:
        with pytest.raises(DomainError) as first:
            await engine.invoke([{"role": "user", "content": "test"}])
        assert first.value.code == "rate_limited"
        assert engine.usage.transport_attempts == 2
        with pytest.raises(DomainError) as second:
            await engine.invoke([{"role": "user", "content": "test"}])
        assert second.value.code == "call_budget_exhausted"
        assert len(requests) == 2
    finally:
        await model.close()


@pytest.mark.asyncio
async def test_gateway_context_error_is_normalized_and_cancellation_keeps_attempts(settings):
    model = ApiMira(
        settings,
        httpx.MockTransport(
            lambda _: httpx.Response(
                502, json={"error": {"code": "maximum_context_length_exceeded"}}
            )
        ),
    )
    try:
        with pytest.raises(DomainError) as error:
            await model.complete(model="test-model", messages=[], max_tokens=256)
        assert error.value.code == "context_length_exceeded"
    finally:
        await model.close()
    count = 0

    async def cancelled(_):
        nonlocal count
        count += 1
        if count == 1:
            return httpx.Response(429, headers={"Retry-After": "0"})
        raise asyncio.CancelledError

    model = ApiMira(settings, httpx.MockTransport(cancelled))

    async def emit(*_):
        pass

    engine = Harness(
        model,
        settings,
        RunCreate(questions=[Question(id="q", package_id="p", text="test")]),
        emit,
        asyncio.Event(),
    )
    try:
        with pytest.raises(asyncio.CancelledError):
            await engine.invoke([{"role": "user", "content": "test"}])
        assert count == engine.usage.transport_attempts == 2
    finally:
        await model.close()
