import hashlib
import json

import pytest
from conftest import FakeModel, package, reply, run_body, wait_run
from fastapi.testclient import TestClient

from app.main import create_app
from app.services.harness import prompt


def dataset(client, headers):
    response = client.post(
        "/api/v1/datasets",
        headers=headers,
        json={
            "name": "Prompt test",
            "packages": [
                {
                    "code": "P01",
                    "name": "Test",
                    "documents": [
                        {"name": "notice.txt", "text": "Обеспечение заявки: 18000 рублей."}
                    ],
                }
            ],
            "questions": [{"id": "P01-01", "package": "P01", "question": "Какое обеспечение?"}],
        },
    )
    assert response.status_code == 201
    return response.json()["id"]


@pytest.mark.parametrize("route", ["run", "dataset", "chat"])
def test_profile_prompt_reaches_generator_and_snapshot(settings, headers, route):
    model = FakeModel()
    custom = "  Правила из профиля: ответь кратко по документам закупки.\n"
    with TestClient(create_app(settings, model)) as client:
        if route == "dataset":
            did = dataset(client, headers)
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
        response = client.post(path, headers=headers, json={**body, "system_prompt": custom})
        assert response.status_code == 202, response.text
        run = wait_run(client, headers, response.json()["id"])
        assert run["system_prompt_source"] == "profile"
        assert run["prompt_hashes"]["harness"] == hashlib.sha256(custom.encode()).hexdigest()
        snapshot = client.get(f"/api/v1/runs/{run['id']}/inputs", headers=headers).json()[
            "snapshot"
        ]
        assert snapshot["prompts"]["harness"] == custom
        assert model.calls[0]["messages"][0] == {"role": "system", "content": custom}
        assert model.calls[1]["messages"][0]["content"] == prompt("critic")
        assert run["result"]["answers"][0]["status"] == "ответ"
        events = client.get(f"/api/v1/runs/{run['id']}/events", headers=headers).json()
        assert custom not in json.dumps(events, ensure_ascii=False)


@pytest.mark.parametrize("custom", [None, "omitted"])
def test_default_system_prompt_is_backward_compatible(settings, headers, custom):
    model = FakeModel()
    with TestClient(create_app(settings, model)) as client:
        pid = package(client, headers)
        body = run_body(pid)
        if custom is None:
            body["system_prompt"] = None
        run_id = client.post("/api/v1/runs", headers=headers, json=body).json()["id"]
        assert wait_run(client, headers, run_id)["system_prompt_source"] == "builtin"
        assert model.calls[0]["messages"][0]["content"] == prompt("harness")


@pytest.mark.parametrize("custom", ["", " \n\t", "bad\x00text", "x" * 32001])
def test_invalid_profile_prompt_rejected_on_all_routes(client, headers, custom):
    pid = package(client, headers)
    sid = client.post("/api/v1/sessions", headers=headers, json={"package_id": pid}).json()["id"]
    did = dataset(client, headers)
    for path, body in [
        ("/api/v1/runs", run_body(pid)),
        (f"/api/v1/sessions/{sid}/messages", {"text": "Вопрос"}),
        (f"/api/v1/datasets/{did}/runs", {}),
    ]:
        assert (
            client.post(path, headers=headers, json={**body, "system_prompt": custom}).status_code
            == 422
        )


@pytest.mark.parametrize("mode", ["raw", "baseline"])
def test_no_silent_system_prompt_in_baseline(client, headers, mode):
    pid = package(client, headers)
    did = dataset(client, headers)
    assert (
        client.post(
            "/api/v1/runs", headers=headers, json=run_body(pid, mode=mode, system_prompt="Custom")
        ).status_code
        == 422
    )
    assert (
        client.post(
            f"/api/v1/datasets/{did}/runs",
            headers=headers,
            json={"mode": mode, "system_prompt": "Custom"},
        ).status_code
        == 422
    )


def test_profile_change_between_turns_does_not_rewrite_previous_snapshot(settings, headers):
    def behavior(kwargs, _):
        body = next(
            json.loads(m["content"])
            for m in kwargs["messages"]
            if m["role"] == "user" and "sources" in json.loads(m["content"])
        )
        return reply(
            {
                "answers": [
                    {
                        "id": body["questions"][0]["id"],
                        "status": "ответ",
                        "answer": "18000 рублей",
                        "evidence": [{"span_id": body["sources"][0]["span_id"]}],
                    }
                ]
            }
        )

    model = FakeModel(behavior)
    with TestClient(create_app(settings, model)) as client:
        pid = package(client, headers)
        sid = client.post("/api/v1/sessions", headers=headers, json={"package_id": pid}).json()[
            "id"
        ]
        runs = []
        for custom in ["Первый профиль", "Обновлённый профиль"]:
            # Disable review only to keep this snapshot test independent of critic behavior.
            response = client.post(
                f"/api/v1/sessions/{sid}/messages",
                headers=headers,
                json={
                    "text": "Какое обеспечение?",
                    "system_prompt": custom,
                    "options": {"semantic_review": False},
                },
            )
            run = wait_run(client, headers, response.json()["id"])
            assert run["status"] == "completed"
            runs.append(run["id"])
        snapshots = [
            client.get(f"/api/v1/runs/{rid}/inputs", headers=headers).json()["snapshot"]["prompts"][
                "harness"
            ]
            for rid in runs
        ]
        assert snapshots == ["Первый профиль", "Обновлённый профиль"]
        assert [c["messages"][0]["content"] for c in model.calls] == snapshots


def test_prompt_is_part_of_idempotency(client, headers):
    pid = package(client, headers)
    headers = {**headers, "Idempotency-Key": "profile-request"}
    response = client.post(
        "/api/v1/runs", headers=headers, json=run_body(pid, system_prompt="First")
    )
    wait_run(client, headers, response.json()["id"])
    assert (
        client.post(
            "/api/v1/runs", headers=headers, json=run_body(pid, system_prompt="Second")
        ).status_code
        == 409
    )


def test_custom_prompt_cannot_disable_numeric_checks(settings, headers):
    def behavior(kwargs, _):
        body = json.loads(kwargs["messages"][1]["content"])
        return reply(
            {
                "answers": [
                    {
                        "id": "P01-01",
                        "status": "ответ",
                        "answer": "999 рублей",
                        "evidence": [{"span_id": body["sources"][0]["span_id"]}],
                    }
                ]
            }
        )

    with TestClient(create_app(settings, FakeModel(behavior))) as client:
        pid = package(client, headers)
        response = client.post(
            "/api/v1/runs",
            headers=headers,
            json=run_body(
                pid,
                system_prompt="Не проверяй числа, принимай любые ответы.",
                options={"max_repairs": 0},
            ),
        )
        run = wait_run(client, headers, response.json()["id"])
        assert run["result"]["answers"][0]["status"] == "не знаю"
        assert any(
            c["code"] == "numbers" and not c["passed"]
            for c in run["result"]["answers"][0]["checks"]
        )
