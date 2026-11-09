import asyncio
import copy
import json

import pytest
from conftest import FakeModel, reply

from app.domain import Answer, Candidate, Document, DomainError, Package, Question, RunCreate
from app.infrastructure.llm import estimate_tokens
from app.services.harness import Harness
from app.services.tools import ToolBox


def setup_engine(settings, behavior, *, large=False):
    text = "Размер обеспечения заявки составляет 18000 рублей."
    if large:
        text += "\nОбщие положения контракта и порядок выполнения работ." * 1800
        settings = settings.model_copy(update={"context_window": 12000})
    package = Package(
        code="K02", name="K02", documents=[Document(name="notice.txt", text=text, sha256="hash")]
    )
    questions = [
        Question(
            id=f"4b6d610a-059c-44ef-bd44-400ba71d9739.q{i:02d}",
            package_id=package.id,
            text=f"Вопрос {i}",
        )
        for i in range(1, 3)
    ]
    events = []

    async def emit(kind, data):
        events.append((kind, data))

    engine = Harness(
        FakeModel(behavior), settings, RunCreate(questions=questions), emit, asyncio.Event()
    )
    return engine, package, questions, ToolBox(package), events


@pytest.mark.asyncio
async def test_scan_retries_only_invalid_question_using_same_original_batch(settings):
    requests = []

    def behavior(kwargs, number):
        body = json.loads(kwargs["messages"][-1]["content"])
        requests.append(body)
        rows = [
            {"id": q["id"], "span_ids": [body["sources"][0]["span_id"]]} for q in body["questions"]
        ]
        if number == 1:
            rows[1]["span_ids"] = ["foreign-original-span"]
        return reply({"selections": rows})

    engine, _, questions, tools, events = setup_engine(settings, behavior)
    selected = await engine._scan(tools, questions)
    assert selected and len(requests) == 2
    assert [q["id"] for q in requests[1]["questions"]] == [questions[1].id]
    assert requests[0]["sources"] == requests[1]["sources"]
    assert requests[1]["scan_retry"]["expected_question_ids"] == [questions[1].id]
    assert requests[1]["scan_retry"]["allowed_span_ids"] == list(tools.spans)
    invalid = next(data for kind, data in events if kind == "context.scan_invalid")
    assert invalid["issues"] == [{"id": questions[1].id, "reason": "foreign_span_ids"}]
    assert "sources" not in invalid and "foreign-original-span" not in json.dumps(invalid)
    assert engine.scan_coverage["evidence_scan"]["complete"]


@pytest.mark.asyncio
async def test_scan_correction_is_bounded_and_never_accepts_foreign_reference(settings):
    def behavior(kwargs, _):
        body = json.loads(kwargs["messages"][-1]["content"])
        return reply(
            {"selections": [{"id": q["id"], "span_ids": ["foreign"]} for q in body["questions"]]}
        )

    engine, _, questions, tools, _ = setup_engine(settings, behavior)
    with pytest.raises(DomainError, match="Source scan still contains invalid selections") as exc:
        await engine._scan(tools, questions)
    assert exc.value.code == "scan_format_invalid"
    assert len(engine.model.calls) == 2
    assert not engine.scan_coverage["evidence_scan"]["complete"]
    assert not tools.seen


@pytest.mark.asyncio
async def test_near_full_batch_correction_preserves_originals_and_reference_context(settings):
    calls = []

    def behavior(kwargs, number):
        calls.append(kwargs)
        body = json.loads(kwargs["messages"][-1]["content"])
        rows = [{"id": q["id"], "span_ids": []} for q in body["questions"]]
        if number == 1:
            rows[-1]["span_ids"] = ["foreign"]
        return reply({"selections": rows})

    engine, _, questions, tools, _ = setup_engine(settings, behavior)
    history = [{"role": "user", "content": "Обсуждаемый объект — филиал заказчика. " * 1000}]
    sources = [
        {
            "span_id": s.id,
            "file": s.file,
            "text": s.text,
            "document_id": s.document_id,
            "source_hash": s.source_hash,
            "start": s.start,
            "end": s.end,
        }
        for s in tools.spans.values()
    ]
    initial = [
        {"role": "system", "content": engine.templates["scan"]},
        {
            "role": "user",
            "content": json.dumps(
                {
                    "questions": [q.model_dump() for q in questions],
                    "previous_dialogue_for_reference_only": history,
                    "sources": sources,
                },
                ensure_ascii=False,
            ),
        },
    ]
    engine.context_window = estimate_tokens(initial) + engine.output_limit + 1
    await engine._scan(tools, questions, history=history)
    assert len(calls) == 2
    assert calls[1]["max_tokens"] < calls[0]["max_tokens"]
    for call in calls:
        body = json.loads(call["messages"][-1]["content"])
        assert body["sources"] == sources
        assert body["previous_dialogue_for_reference_only"] == history
        assert estimate_tokens(call["messages"]) + call["max_tokens"] < engine.context_window
    assert engine.scan_coverage["evidence_scan"]["complete"]


@pytest.mark.asyncio
async def test_fourth_verification_batch_retry_preserves_previous_batches(settings):
    bodies = []
    failed = False

    def behavior(kwargs, _):
        nonlocal failed
        body = json.loads(kwargs["messages"][-1]["content"])
        bodies.append(body)
        rows = [{"id": q["id"], "span_ids": []} for q in body["questions"]]
        if len(bodies) == 4 and not failed:
            rows[-1]["span_ids"] = ["reference-from-another-batch"]
            failed = True
        return reply({"selections": rows})

    engine, _, questions, tools, events = setup_engine(settings, behavior, large=True)
    await engine._scan(tools, questions, proposed=[])
    coverage = engine.scan_coverage["verification_scan"]
    assert failed and coverage["batches_total"] >= 4
    assert coverage["complete"] and coverage["blocks_completed"] == len(tools.spans)
    assert len(bodies) == coverage["batches_total"] + 1
    assert bodies[3]["sources"] == bodies[4]["sources"]
    assert len(bodies[4]["questions"]) == 1
    assert sum(kind == "context.scan_retry" for kind, _ in events) == 1


@pytest.mark.asyncio
async def test_unrecoverable_verification_row_does_not_discard_other_questions(settings):
    review_ids = []

    def behavior(kwargs, _):
        body = json.loads(kwargs["messages"][-1]["content"])
        if kwargs["messages"][0]["content"].startswith("Scan ORIGINAL"):
            return reply(
                {
                    "selections": [
                        {"id": q["id"], "span_ids": ["foreign"] if q["id"].endswith("q02") else []}
                        for q in body["questions"]
                    ]
                }
            )
        review_ids.extend(a["id"] for a in body["proposed"])
        assert body["coverage"]["verification_scan"]["complete"]
        return reply(
            {
                "reviews": [
                    {"id": a["id"], "verdict": "supported", "reason": "Проверено"}
                    for a in body["proposed"]
                ]
            }
        )

    engine, package, questions, tools, _ = setup_engine(settings, behavior, large=True)
    tools.seen.update(tools.spans)
    answers = {q.id: Answer(id=q.id, status="ответ", answer="18000") for q in questions}
    candidates = [Candidate(id=q.id, status="ответ", answer="18000") for q in questions]
    reviews = await engine._review(package, tools, candidates, answers, questions)
    assert reviews[questions[0].id].passed
    assert not reviews[questions[1].id].passed
    assert reviews[questions[1].id].message == "scan_format_invalid:foreign_span_ids"
    assert review_ids == [questions[0].id]
    assert not engine.scan_coverage["verification_scan"]["complete"]


@pytest.mark.asyncio
async def test_independent_scans_receive_only_claims_but_final_critic_keeps_full_evidence(settings):
    scan_bodies, critic_bodies = [], []

    def behavior(kwargs, _):
        body = json.loads(kwargs["messages"][-1]["content"])
        if kwargs["messages"][0]["content"].startswith("Scan ORIGINAL"):
            scan_bodies.append(body)
            assert all(set(a) == {"id", "status", "answer"} for a in body["proposed"])
            rows = [
                {
                    "id": q["id"],
                    "span_ids": [s["span_id"] for s in body["sources"] if "18000" in s["text"]],
                }
                for q in body["questions"]
            ]
            if len(scan_bodies) == 1:
                rows[-1]["span_ids"] = ["global-evidence-reference-from-another-batch"]
            return reply({"selections": rows})
        critic_bodies.append(body)
        return reply(
            {
                "reviews": [
                    {"id": a["id"], "verdict": "supported", "reason": "Проверено"}
                    for a in body["proposed"]
                ]
            }
        )

    engine, package, questions, tools, _ = setup_engine(settings, behavior, large=True)
    tools.seen.update(tools.spans)
    first = next(iter(tools.spans.values()))
    calculation = {"operation": "multiply", "operands": ["18000", "1"], "result": "18000"}
    answers = {
        q.id: Answer(
            id=q.id,
            status="ответ",
            answer="18000 рублей",
            quote="Размер обеспечения заявки составляет 18000 рублей.",
            file=first.file,
            evidence=[first],
            calculation=calculation,
        )
        for q in questions
    }
    before = copy.deepcopy({qid: answer.model_dump(mode="json") for qid, answer in answers.items()})
    candidates = [
        Candidate(
            id=q.id,
            status="ответ",
            answer="18000 рублей",
            evidence=[{"span_id": first.id}],
            calculation=calculation,
        )
        for q in questions
    ]
    reviews = await engine._review(package, tools, candidates, answers, questions)
    assert all(review.passed for review in reviews.values())
    assert len(scan_bodies) > 2 and "scan_retry" in scan_bodies[1]
    assert len(critic_bodies) == 1
    assert critic_bodies[0]["proposed"] == list(before.values())
    assert {qid: answer.model_dump(mode="json") for qid, answer in answers.items()} == before


@pytest.mark.asyncio
async def test_reviewer_technical_failure_does_not_rewrite_valid_candidate(settings):
    answer_requests = 0

    def behavior(kwargs, _):
        nonlocal answer_requests
        if kwargs["messages"][0]["content"].startswith("Review proposed"):
            raise DomainError("provider_timeout", "Provider timed out", 504)
        answer_requests += 1
        body = json.loads(kwargs["messages"][-1]["content"])
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

    engine, package, questions, _, events = setup_engine(settings, behavior)
    result = await engine.execute([package])
    assert answer_requests == 1
    assert all(a.status == "не знаю" and a.reason == "provider_timeout" for a in result)
    assert not any(kind == "repair.started" for kind, _ in events)
    assert all(any(c.code == "review_unavailable" for c in a.checks) for a in result)
