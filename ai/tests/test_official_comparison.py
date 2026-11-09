import hashlib
import io
import json
import zipfile
from pathlib import Path
from uuid import uuid4

import pytest
from conftest import FakeModel, reply, wait_run
from fastapi.testclient import TestClient

from app.domain import DomainError, now
from app.main import create_app
from app.services.comparison_inputs import parse_inputs
from app.services.evaluation import compare_evaluations, evaluate_run
from app.services.importing import import_archive

CSV = "id;package;question\nP01-01;P01;Какое обеспечение?\nP02-01;P02;Какое обеспечение?\n"
GOLD = [
    dict(
        id=f"P0{i}-01",
        package=f"P0{i}",
        status="ответ",
        kind="num",
        expected=[value],
        type="факт",
        quote="untouched gold quote",
    )
    for i, value in [(1, 18000), (2, 27000)]
]


def test_different_actual_provider_model_versions_have_no_paired_delta():
    before = {'model': 'alias', 'run_metrics': {'returned_models': ['version-a']}}
    after = {'model': 'alias', 'run_metrics': {'returned_models': ['version-b']}}
    with pytest.raises(DomainError) as exc:
        compare_evaluations(before, after)
    assert exc.value.code == 'different_returned_models'


def upload_source(client, settings, name, raw):
    file_id = str(uuid4())
    path = Path(settings.source_root) / file_id
    path.parent.mkdir(exist_ok=True)
    path.write_bytes(raw)
    record = dict(
        id=file_id,
        owner="user-1",
        version="v1",
        updated_at=now(),
        filename=name,
        relative_path=file_id,
        sha256=hashlib.sha256(raw).hexdigest(),
        media_type="application/octet-stream",
    )
    client.portal.call(client.app.state.store.create, "source_file", record, "user-1")
    return file_id


def test_csv_and_gold_are_preserved_without_model_rewriting():
    questions, references = parse_inputs("\ufeff" + CSV, json.dumps(GOLD))
    assert [q.id for q in questions] == ["P01-01", "P02-01"]
    assert [q.package_id for q in questions] == ["P01", "P02"]
    assert references == GOLD
    bad = [dict(GOLD[0]), dict(GOLD[1], id="P01-01")]
    with pytest.raises(DomainError):
        parse_inputs(CSV, json.dumps(bad))


def test_technical_failure_has_no_score_and_unsupported_zip_is_not_silently_partial(settings):
    with pytest.raises(DomainError) as exc:
        evaluate_run({"status": "failed"}, [])
    assert exc.value.status == 409
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w") as z:
        z.writestr("questions.csv", CSV)
        z.writestr("packages/P01/notice.txt", "Обеспечение 18000 рублей.")
        z.writestr("packages/P01/amendment.pdf", b"%PDF-later amendment")
    with pytest.raises(DomainError) as exc:
        import_archive(out.getvalue(), settings)
    assert exc.value.code == "unsupported_archive_document"


def test_zip_mapping_is_idempotent_and_never_calls_model(client, headers, settings):
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w") as z:
        z.writestr("packages/P01/notice.txt", "Обеспечение 18000 рублей.")
        z.writestr("packages/P02/notice.txt", "Обеспечение 27000 рублей.")
        z.writestr("answers_public.json", "THIS MUST NEVER REACH THE MODEL")
        z.writestr("check.py", "THIS MUST NOT EXECUTE")
    q = upload_source(client, settings, "questions.csv", CSV.encode())
    g = upload_source(client, settings, "answers_public.json", json.dumps(GOLD).encode())
    doc = upload_source(client, settings, "documents.zip", out.getvalue())
    body = dict(questions_file_id=q, answers_file_id=g, model="test-model", document_file_ids=[doc])
    h = {**headers, "Idempotency-Key": "same-preparation"}
    first = client.post("/api/v1/comparison-inputs/parse", json=body, headers=h)
    assert first.status_code == 200, first.text
    second = client.post("/api/v1/comparison-inputs/parse", json=body, headers=h)
    assert first.json() == second.json()
    assert first.json()["reference_answers"] == GOLD
    assert set(first.json()["package_ids"]) == {"P01", "P02"}
    assert len(client.app.state.runner.model.calls) == 0
    for package_id in first.json()["package_ids"].values():
        package = client.portal.call(client.app.state.store.get, "package", package_id, "user-1")
        assert len(package["documents"]) == 1
        assert "MUST NEVER" not in package["documents"][0]["text"]
    bad = client.post(
        "/api/v1/comparison-inputs/parse", json={**body, "document_file_ids": []}, headers=h
    )
    assert bad.status_code == 409
    blocked = client.post(
        "/api/v1/comparison-inputs/parse", json={**body, "document_file_ids": [g]}, headers=headers
    )
    assert blocked.status_code == 422


def test_all_modes_isolate_procurements_and_profile_only_appends(settings, headers):
    generations = []

    def behavior(kwargs, _):
        messages = kwargs["messages"]
        assert "untouched gold quote" not in json.dumps(messages)
        direct = messages[0]["role"] == "user"
        body = (
            json.loads(messages[0]["content"].split("\n\n", 1)[1])
            if direct
            else json.loads(messages[-1]["content"])
        )
        if not direct and messages[0]["content"].startswith("Review proposed"):
            return reply(
                {
                    "reviews": [
                        dict(id=a["id"], verdict="supported", reason="test")
                        for a in body["proposed"]
                    ]
                }
            )
        assert len(body["questions"]) == 1
        q = body["questions"][0]
        amount = "18000" if q["id"] == "P01-01" else "27000"
        assert (
            ("27000" not in json.dumps(body))
            if amount == "18000"
            else ("18000" not in json.dumps(body))
        )
        generations.append((direct, q["id"]))
        row = dict(id=q["id"], status="ответ", answer=amount + " рублей")
        row.update(
            quote=f"Обеспечение {amount} рублей.", file="notice.txt"
        ) if direct else row.update(evidence=[{"span_id": body["sources"][0]["span_id"]}])
        return reply({"answers": [row]})

    with TestClient(create_app(settings, FakeModel(behavior))) as client:
        ds = client.post(
            "/api/v1/datasets",
            headers=headers,
            json={
                "name": "two procurements",
                "packages": [
                    dict(
                        code=f"P0{i}",
                        name=f"P0{i}",
                        documents=[dict(name="notice.txt", text=f"Обеспечение {amount} рублей.")],
                    )
                    for i, amount in [(1, 18000), (2, 27000)]
                ],
                "questions": [
                    dict(id=r["id"], package=r["package"], question="Какое обеспечение?")
                    for r in GOLD
                ],
            },
        ).json()
        for mode in ["baseline", "harness"]:
            body = dict(mode=mode)
            if mode == "harness":
                body["additional_instructions"] = "Отвечай кратко."
            response = client.post(f"/api/v1/datasets/{ds['id']}/runs", json=body, headers=headers)
            run = wait_run(client, headers, response.json()["id"])
            assert run["status"] == "completed", run
            assert run["request"]["options"]["question_grouping"] == "per_package"
            if mode == "harness":
                inputs = client.get(f"/api/v1/runs/{run['id']}/inputs", headers=headers).json()
                assert inputs["snapshot"]["prompts"]["harness"].startswith("You answer questions")
                assert inputs["snapshot"]["prompts"]["harness"].endswith("Отвечай кратко.")
            evaluation = client.post(
                f"/api/v1/runs/{run['id']}/evaluate",
                json={"reference_answers": GOLD},
                headers=headers,
            ).json()
            assert evaluation["correct"] == 2
            assert evaluation["rows"][0]["question"] == "Какое обеспечение?"
            assert evaluation["rows"][0]["answer"]["id"] == "P01-01"
        assert [q for direct, q in generations if direct] == [
            q for direct, q in generations if not direct
        ]
