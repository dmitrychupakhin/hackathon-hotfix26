import hashlib

import pytest
from conftest import FakeModel, reply, wait_run
from fastapi.testclient import TestClient

from app.domain import Answer, Document, Package
from app.main import create_app
from app.services.citation_anchors import attach_plain_anchor

QUOTE = "обеспечение составляет 18000 рублей"


def document(text=None, name="notice.txt"):
    text = text or f"🙂 Начало. {QUOTE}. Конец."
    return Document(
        id="doc-1",
        name=name,
        original_name=name,
        text=text,
        sha256=hashlib.sha256(text.encode()).hexdigest(),
        source_file_id="file-1",
        source_version="v1",
        original_sha256="a" * 64,
        locations=[{"page": 1, "start": 0, "end": len(text)}],
    )


def test_plain_unique_anchor_preserves_unsupported_answer_and_empty_checks():
    doc = document()
    answer = Answer(id="q-1", status="ответ", answer="999999 рублей", quote=QUOTE, file=doc.name)
    anchored = attach_plain_anchor(
        answer, [Package(id="p-1", code="P", name="Package", documents=[doc])], "p-1"
    )
    assert anchored.answer == answer.answer and anchored.status == answer.status
    assert anchored.checks == []
    span = anchored.evidence[0]
    assert span.anchor_method == "exact_text_match"
    assert span.source_file_id == "file-1" and span.source_version == "v1"
    assert doc.text[span.start : span.end] == QUOTE
    assert span.locations[0]["page"] == 1
    assert (
        span.start != len(doc.text[: span.start].encode("utf-16-le")) // 2
    )  # emoji uses 2 JS units


@pytest.mark.parametrize(
    "text,file,quote,package_id",
    [
        (f"{QUOTE}. Еще раз: {QUOTE}", "notice.txt", QUOTE, "p-1"),
        (QUOTE, "wrong.txt", QUOTE, "p-1"),
        (QUOTE, "notice.txt", QUOTE.upper(), "p-1"),
        (QUOTE, "notice.txt", QUOTE, "other-package"),
    ],
)
def test_unmatched_ambiguous_or_wrong_source_quote_has_no_anchor(text, file, quote, package_id):
    answer = Answer(id="q-1", status="ответ", answer="18000", quote=quote, file=file)
    package = Package(id="p-1", code="P", name="Package", documents=[document(text)])
    assert attach_plain_anchor(answer, [package], package_id).evidence == []


def test_plain_only_anchor_resolution_no_extra_calls(settings, headers):
    def behavior(kwargs, count):
        return reply(
            {
                "answers": [
                    {
                        "id": "q-1",
                        "status": "ответ",
                        "answer": "999999 рублей",
                        "quote": QUOTE,
                        "file": "notice.txt",
                    }
                ]
            }
        )

    model = FakeModel(behavior)
    with TestClient(create_app(settings, model)) as client:
        package = client.post(
            "/api/v1/packages", headers=headers, json={"code": "P", "name": "Package"}
        ).json()
        client.post(
            f"/api/v1/packages/{package['id']}/documents/text",
            headers=headers,
            json={"name": "notice.txt", "text": document().text},
        )
        for mode in ("plain", "baseline"):
            response = client.post(
                "/api/v1/runs",
                headers=headers,
                json={
                    "mode": mode,
                    "questions": [{"id": "q-1", "package_id": package["id"], "text": "Сколько?"}],
                },
            )
            run = wait_run(client, headers, response.json()["id"])
            answer = run["result"]["answers"][0]
            assert run["status"] == "completed" and run["metrics"]["model_calls"] == 1
            assert answer["checks"] == [] and answer["answer"] == "999999 рублей"
            assert bool(answer["evidence"]) == (mode == "plain")
    assert len(model.calls) == 2
