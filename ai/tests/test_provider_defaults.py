import httpx
import pytest
from conftest import FakeModel, package, run_body, wait_run
from fastapi.testclient import TestClient

from app.domain import DomainError
from app.infrastructure.llm import ApiMira
from app.main import create_app
from app.provider_settings import MODEL_EXAMPLES
from app.services.evaluation import compare_evaluations


@pytest.mark.parametrize("route", ["run", "dataset", "chat"])
def test_omitted_provider_and_model_resolve_from_env_settings(settings, headers, route):
    model = FakeModel()
    with TestClient(create_app(settings, model)) as client:
        if route == "dataset":
            did = client.post(
                "/api/v1/datasets",
                headers=headers,
                json={
                    "name": "Defaults",
                    "packages": [
                        {
                            "code": "P01",
                            "name": "Test",
                            "documents": [
                                {"name": "notice.txt", "text": "Обеспечение заявки: 18000 рублей."}
                            ],
                        }
                    ],
                    "questions": [
                        {"id": "P01-01", "package": "P01", "question": "Какое обеспечение?"}
                    ],
                },
            ).json()["id"]
            path, body = f"/api/v1/datasets/{did}/runs", {}
        else:
            pid = package(client, headers)
            if route == "run":
                path, body = "/api/v1/runs", run_body(pid)
            else:
                sid = client.post(
                    "/api/v1/sessions", headers=headers, json={"package_id": pid}
                ).json()["id"]
                path, body = f"/api/v1/sessions/{sid}/messages", {"text": "Какое обеспечение?"}
        r = client.post(path, headers=headers, json=body)
        assert r.status_code == 202, r.text
        run = wait_run(client, headers, r.json()["id"])
        assert run["model"] == settings.model
        assert run["base_url"] == settings.base_url
        assert run["request"]["base_url"] == settings.base_url
        assert all(c["base_url"] == settings.base_url for c in model.calls)
        snapshot = client.get(f"/api/v1/runs/{run['id']}/inputs", headers=headers).json()[
            "snapshot"
        ]
        assert snapshot["base_url"] == settings.base_url
        schema = client.get("/openapi.json").json()
        for name in ["RunCreate", "ChatMessage", "DatasetRun"]:
            props = schema["components"]["schemas"][name]["properties"]
            assert props["model"]["default"] == settings.model
            assert props["base_url"]["default"] == settings.base_url
            assert props["model"]["examples"] == MODEL_EXAMPLES and len(MODEL_EXAMPLES) == 6


def test_explicit_provider_requires_admin_allowlist(settings, headers):
    settings = settings.model_copy(
        update={
            "allowed_base_urls": "https://proxy.example.test/v1",
            "allowed_models": "alternate-model",
        }
    )
    model = FakeModel()
    with TestClient(create_app(settings, model)) as client:
        pid = package(client, headers)
        r = client.post(
            "/api/v1/runs",
            headers=headers,
            json=run_body(pid, model="alternate-model", base_url="https://proxy.example.test/v1/"),
        )
        run = wait_run(client, headers, r.json()["id"])
        assert run["base_url"] == "https://proxy.example.test/v1"
        assert model.calls[0]["model"] == "alternate-model"
        assert model.calls[0]["base_url"] == run["base_url"]
        assert run["context_budget"]["source"] == "fallback"
        prior = len(model.calls)
        blocked = client.post(
            "/api/v1/runs",
            headers=headers,
            json=run_body(pid, base_url="https://untrusted.example.test/v1"),
        )
        assert (
            blocked.status_code == 422 and blocked.json()["error"]["code"] == "provider_not_allowed"
        )
        assert len(model.calls) == prior


@pytest.mark.parametrize(
    "url",
    [
        "https://user:secret@example.test/v1",
        "https://example.test/v1?key=secret",
        "https://example.test/v1#key",
        "http://example.test/v1",
        "file:///tmp",
        "http://localhost.evil.test/v1",
    ],
)
def test_unsafe_provider_url_rejected(client, headers, url):
    pid = package(client, headers)
    assert (
        client.post("/api/v1/runs", headers=headers, json=run_body(pid, base_url=url)).status_code
        == 422
    )


@pytest.mark.asyncio
async def test_provider_client_uses_only_approved_explicit_address(settings):
    settings = settings.model_copy(update={"allowed_base_urls": "https://proxy.example.test/v1"})
    requests = []

    def handler(request):
        requests.append(request)
        assert request.url.host == "proxy.example.test"
        assert request.headers["authorization"] == "Bearer test-key"
        assert b"base_url" not in request.content
        return httpx.Response(
            200,
            json={
                "choices": [
                    {"message": {"role": "assistant", "content": "{}"}, "finish_reason": "stop"}
                ]
            },
        )

    client = ApiMira(settings, httpx.MockTransport(handler))
    try:
        await client.complete(
            model="test-model",
            messages=[],
            max_tokens=1000,
            base_url="https://proxy.example.test/v1",
        )
        with pytest.raises(DomainError):
            await client.complete(
                model="test-model",
                messages=[],
                max_tokens=1000,
                base_url="https://untrusted.example.test/v1",
            )
        assert len(requests) == 1
    finally:
        await client.close()


def test_resolved_defaults_are_idempotent(client, headers, settings):
    pid = package(client, headers)
    headers = {**headers, "Idempotency-Key": "default-provider"}
    a = client.post("/api/v1/runs", headers=headers, json=run_body(pid)).json()["id"]
    wait_run(client, headers, a)
    b = client.post(
        "/api/v1/runs",
        headers=headers,
        json=run_body(pid, model=settings.model, base_url=settings.base_url),
    ).json()["id"]
    assert a == b


def test_before_after_requires_same_provider():
    with pytest.raises(DomainError) as error:
        compare_evaluations(
            {"model": "test", "base_url": "https://a.test/v1"},
            {"model": "test", "base_url": "https://b.test/v1"},
        )
    assert error.value.code == "different_providers"
