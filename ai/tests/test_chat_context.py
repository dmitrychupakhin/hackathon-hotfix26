import json

from conftest import FakeModel, package, reply, wait_run
from fastapi.testclient import TestClient

from app.domain import Document, Package
from app.main import create_app
from app.services.chat_context import (
    advance_chat_state,
    build_chat_context,
    model_history,
    record_evidence_references,
)


def source_package():
    return Package(
        id="package-1",
        code="P01",
        name="Закупка",
        revision="revision-1",
        documents=[Document(id="doc-1", name="notice.txt", text="Источник", sha256="hash-1")],
    )


def test_long_dialogue_does_not_copy_assistant_answers_or_drop_sources():
    session = {
        "messages": [
            {"role": "user", "content": "Какое обеспечение исполнения контракта?"},
            {"role": "assistant", "content": "OLD_UNTRUSTED_ANSWER " * 50000},
            {"role": "user", "content": "А какой у него срок?"},
        ]
    }
    context = build_chat_context(session, source_package())
    serialized = json.dumps(model_history(context), ensure_ascii=False)
    assert "OLD_UNTRUSTED_ANSWER" not in serialized
    assert context["previous_user_question"] == "А какой у него срок?"
    assert context["topic_user_question"] == "Какое обеспечение исполнения контракта?"
    assert context["rules"]["ask_for_clarification_if_referent_is_ambiguous"]
    assert context["file_bindings"][0]["version"] == "hash-1"
    assert len(session["messages"][1]["content"]) > 100000


def test_refresh_bindings_preserves_old_run_context_and_rejects_stale_evidence():
    source = source_package()
    session = {"messages": [], "context_state": {}}
    advance_chat_state(session, source, "Какое обеспечение?")
    record_evidence_references(
        session,
        [
            {
                "answer": "UNTRUSTED_18000",
                "evidence": [
                    {
                        "id": "span-1",
                        "document_id": "doc-1",
                        "source_hash": "hash-1",
                        "start": 0,
                        "end": 8,
                        "text": "UNTRUSTED_QUOTE",
                    }
                ],
            }
        ],
        "old-run",
    )
    frozen = build_chat_context(session, source)
    assert frozen["evidence_references"][0]["span_id"] == "span-1"
    assert "UNTRUSTED" not in json.dumps(frozen)
    changed = source.model_copy(deep=True)
    changed.documents[0].sha256 = "hash-2"
    changed.revision = "revision-2"
    current = build_chat_context(session, changed)
    advance_chat_state(session, changed, "А какой у него срок?")
    assert frozen["file_bindings"][0]["version"] == "hash-1"
    assert current["file_bindings"][0]["version"] == "hash-2"
    assert current["evidence_references"] == []
    assert session["file_bindings"][0]["version"] == "hash-2"
    assert session["context_state"]["topic_user_question"] == "Какое обеспечение?"


def test_metadata_budget_never_silently_removes_file_bindings():
    source = source_package()
    source.documents *= 64
    session = {"messages": [{"role": "user", "content": "x" * 100000}]}
    context = build_chat_context(session, source, budget_tokens=100)
    assert context["dialogue_text_truncated"]
    assert len(context["previous_user_question"]) <= 100
    assert len(context["file_bindings"]) == 64
    assert context["metadata_exceeds_dialogue_budget"]


def test_session_snapshot_uses_compact_context_but_keeps_complete_messages(settings, headers):
    def behavior(kwargs, _):
        return reply(
            {
                "answers": [
                    {
                        "id": "q",
                        "status": "ответ",
                        "answer": "OLD_ANSWER_NOT_A_FACT",
                        "quote": "",
                        "file": "",
                    }
                ]
            }
        )

    with TestClient(create_app(settings, FakeModel(behavior))) as client:
        pid = package(client, headers)
        sid = client.post("/api/v1/sessions", headers=headers, json={"package_id": pid}).json()[
            "id"
        ]
        first = client.post(
            f"/api/v1/sessions/{sid}/messages",
            headers=headers,
            json={"mode": "plain", "text": "Какое обеспечение заявки?", "question_id": "q"},
        )
        assert first.status_code == 202, first.text
        wait_run(client, headers, first.json()["id"])
        second = client.post(
            f"/api/v1/sessions/{sid}/messages",
            headers=headers,
            json={"mode": "plain", "text": "А какой у него срок?", "question_id": "q"},
        )
        assert second.status_code == 202, second.text
        wait_run(client, headers, second.json()["id"])
        inputs = client.get(f"/api/v1/runs/{second.json()['id']}/inputs", headers=headers).json()[
            "snapshot"
        ]
        assert len(inputs["history"]) == 1
        assert inputs["history"][0]["kind"] == "chat_context"
        assert "OLD_ANSWER_NOT_A_FACT" not in json.dumps(inputs["history"])
        assert inputs["chat_context"]["previous_user_question"] == "Какое обеспечение заявки?"
        stored = client.get(f"/api/v1/sessions/{sid}", headers=headers).json()
        assert len(stored["messages"]) == 4
        assert stored["messages"][1]["content"] == "OLD_ANSWER_NOT_A_FACT"
        assert stored["context_state"]["last_user_question"] == "А какой у него срок?"
        assert len(stored["file_bindings"]) == 1


def test_ambiguous_followup_can_request_clarification_without_claiming_a_fact(settings):
    from app.domain import Candidate, Package
    from app.services.tools import ToolBox
    from app.services.validation import validate

    question = "Уточните, срок исполнения или срок подачи заявки?"
    answer, failures = validate(
        Candidate(id="q1", status="не знаю", clarification_question=question),
        ToolBox(Package(code="P01", name="Test")),
    )
    assert not failures and answer.clarification_question == question
    assert not answer.answer and not answer.evidence
    _, failures = validate(
        Candidate(id="q1", status="ответ", answer="18000", clarification_question=question),
        ToolBox(Package(code="P01", name="Test")),
    )
    assert any(c.code == "clarification_status" for c in failures)
