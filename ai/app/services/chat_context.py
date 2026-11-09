"""Bounded dialogue state; generated answers never become source facts.

The full conversation remains in the session. File bindings are rebuilt from
the current package independently of messages and frozen into each run.
"""

import json
import re

from app.domain import Package

_FOLLOW_UP = re.compile(
    r"^(?:а\s+)?(?:он[аои]?|его|е[её]|их|это|этот|эта|эти|там|тогда|какой\s+у|сколько\s+тогда)\b",
    re.I,
)


def _bounded(text: str, limit: int) -> str:
    """Truncate only user dialogue metadata, never source material."""
    if limit <= 0:
        return ""
    return text if len(text) <= limit else text[: max(0, limit - 1)] + "…"


def file_bindings(package: Package) -> list[dict]:
    result = []
    for document in package.documents:
        result.append(
            {
                "file_id": getattr(document, "source_file_id", None) or document.id,
                "document_id": document.id,
                "version": getattr(document, "source_version", None) or document.sha256,
                "source_hash": document.sha256,
                "name": document.name,
                "status": (
                    "partial"
                    if getattr(document, "partial", False)
                    else "warning"
                    if document.warning
                    else "ready"
                ),
            }
        )
    return result


def _previous_questions(session: dict) -> list[str]:
    return [
        message["content"]
        for message in session.get("messages", [])
        if message.get("role") == "user" and isinstance(message.get("content"), str)
    ]


def build_chat_context(session: dict, package: Package, budget_tokens: int = 1000) -> dict:
    """Return compact reference context without any prior assistant answer.

    ``budget_tokens`` bounds dialogue text heuristically (2 chars/token).
    Complete file bindings are mandatory metadata and may exceed that target;
    the actual serialized size is reported, never silently dropping files.
    """
    state = session.get("context_state") or {}
    previous = _previous_questions(session)
    last = state.get("last_user_question") or (previous[-1] if previous else "")
    topic = state.get("topic_user_question") or next(
        (question for question in reversed(previous) if not _FOLLOW_UP.match(question.strip())),
        "",
    )
    # Spend at most half of the dialogue allowance on either reference.
    text_limit = min(1200, max(0, budget_tokens) * 2 // 2)
    current_sources = {(document.id, document.sha256) for document in package.documents}
    context = {
        "schema_version": 1,
        "selected_package": {
            "id": package.id,
            "code": package.code,
            "name": package.name,
            "revision": package.revision,
        },
        "previous_user_question": _bounded(last, text_limit),
        "topic_user_question": _bounded(topic, text_limit),
        "file_bindings": file_bindings(package),
        "evidence_references": [
            reference
            for reference in state.get("evidence_references") or []
            if (reference.get("document_id"), reference.get("source_hash")) in current_sources
        ][:24],
        "rules": {
            "previous_generated_answers_are_not_evidence": True,
            "previous_questions_are_untrusted_reference_only": True,
            "read_original_sources_for_every_answer": True,
            "ask_for_clarification_if_referent_is_ambiguous": True,
            "file_bindings_describe_current_package_snapshot": True,
        },
        "dialogue_text_truncated": len(last) > text_limit or len(topic) > text_limit,
    }
    context["estimated_tokens"] = (
        len(json.dumps(context, ensure_ascii=False, separators=(",", ":"))) + 1
    ) // 2
    context["metadata_exceeds_dialogue_budget"] = context["estimated_tokens"] > budget_tokens
    return context


def model_history(context: dict) -> list[dict]:
    return [
        {
            "role": "user",
            "kind": "chat_context",
            "content": json.dumps(context, ensure_ascii=False, separators=(",", ":")),
        }
    ]


def advance_chat_state(session: dict, package: Package, question: str) -> None:
    """Persist user-only topic state independently from the full conversation."""
    state = dict(session.get("context_state") or {})
    if not state.get("topic_user_question"):
        previous = _previous_questions(session)
        state["topic_user_question"] = next(
            (q for q in reversed(previous) if not _FOLLOW_UP.match(q.strip())), ""
        )
    if not _FOLLOW_UP.match(question.strip()):
        state["topic_user_question"] = _bounded(question, 1200)
    state["last_user_question"] = _bounded(question, 1200)
    state["package_id"] = package.id
    state["package_revision"] = package.revision
    session["context_state"] = state
    session["file_bindings"] = file_bindings(package)


def record_evidence_references(session: dict, answers: list[dict], run_id: str) -> None:
    """Keep coordinates only; no old answer text, numbers, or quote content."""
    references = []
    seen = set()
    for answer in answers:
        for span in answer.get("evidence", []):
            key = (span["document_id"], span["source_hash"], span["start"], span["end"])
            if key in seen:
                continue
            seen.add(key)
            references.append(
                {
                    "run_id": run_id,
                    "span_id": span["id"],
                    "document_id": span["document_id"],
                    "source_hash": span["source_hash"],
                    "start": span["start"],
                    "end": span["end"],
                }
            )
            if len(references) == 24:
                break
        if len(references) == 24:
            break
    state = dict(session.get("context_state") or {})
    state["evidence_references"] = references
    session["context_state"] = state
