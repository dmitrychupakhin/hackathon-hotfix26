import asyncio
import json

import pytest
from conftest import FakeModel, reply

from app.domain import Document, Package, Question, RunCreate
from app.services.context import compact_sources
from app.services.harness import Harness
from app.services.tools import ToolBox

EARLY = "Обеспечение заявки: 18000 рублей."
LATE = "Изменение извещения: вместо 18000 рублей обеспечение заявки составляет 27000 рублей."
BOILERPLATE = "Общие условия исполнения."


def test_compaction_never_merges_versions_or_unrepresented_blocks():
    blocks = [
        {
            "span_id": str(i),
            "file": "notice.txt",
            "document_id": doc,
            "source_hash": version,
            "text": EARLY,
            "start": i * 100,
            "end": i * 100 + len(EARLY),
        }
        for i, (doc, version) in enumerate([("a", "v1"), ("a", "v1"), ("b", "v1"), ("a", "v2")])
    ]
    result = compact_sources(blocks, [])
    assert len(result) == 3
    assert result[0]["occurrences"] == 2
    assert all(s["text"] == EARLY for s in result)
    assert blocks[0].get("occurrences") is None


def long_package():
    text = EARLY + "\n" + (BOILERPLATE + " ") * 8040 + "\n" + LATE
    assert len(text) > 200000
    return Package(
        code="P", name="Long", documents=[Document(name="notice.txt", text=text, sha256="v1")]
    )


def behavior(scanned, summaries):
    def complete(kwargs, _):
        body = json.loads(kwargs["messages"][-1]["content"])
        system = kwargs["messages"][0]["content"]
        if system.startswith("Scan ORIGINAL"):
            stage = "verification" if "proposed" in body else "generation"
            scanned[stage].update(s["span_id"] for s in body["sources"])
            facts = []
            for block in body["sources"]:
                for value, quote, relation in [
                    ("18000", EARLY, "support"),
                    ("27000", LATE, "amendment"),
                    ("указаны", BOILERPLATE, "support"),
                ]:
                    if quote in block["text"]:
                        facts.append(
                            {
                                "field": "обеспечение заявки"
                                if value.isdecimal()
                                else "общие условия",
                                "value": value,
                                "unit": "рубли" if value.isdecimal() else "",
                                "condition": "",
                                "relation": relation,
                                "evidence": [{"span_id": block["span_id"], "quote": quote}],
                            }
                        )
            return reply(
                {
                    "selections": [
                        {
                            "id": "q1",
                            "span_ids": [s["span_id"] for s in body["sources"]],
                            "facts": facts,
                        }
                    ]
                }
            )
        summaries.append(body)
        assert any(LATE in s["text"] for s in body["sources"])
        if system.startswith("Review proposed"):
            assert body["coverage"]["verification_scan"]["complete"]
            assert {"18000", "27000"} <= {f["value"] for f in body["fact_ledger"]}
            return reply(
                {
                    "reviews": [
                        {"id": "q1", "verdict": "supported", "reason": "Позднее явное изменение"}
                    ]
                }
            )
        source = next(s for s in body["sources"] if LATE in s["text"])
        return reply(
            {
                "answers": [
                    {
                        "id": "q1",
                        "status": "ответ",
                        "answer": "27000 рублей",
                        "evidence": [{"span_id": source["span_id"], "quote": LATE}],
                    }
                ]
            }
        )

    return complete


@pytest.mark.asyncio
async def test_201k_all_selected_compacts_then_independently_checks_late_amendment(settings):
    settings = settings.model_copy(update={"context_window": 18000})
    package = long_package()
    scanned = {"generation": set(), "verification": set()}
    summaries, events = [], []

    async def emit(kind, data):
        events.append((kind, data))

    request = RunCreate(
        questions=[Question(id="q1", package_id=package.id, text="Какое обеспечение заявки?")]
    )
    engine = Harness(
        FakeModel(behavior(scanned, summaries)), settings, request, emit, asyncio.Event()
    )
    result = await engine.execute([package])
    assert result[0].answer == "27000 рублей"
    all_ids = set(ToolBox(package).spans)
    assert scanned["generation"] == scanned["verification"] == all_ids
    compact_event = next(data for kind, data in events if kind == "context.evidence_compacted")
    assert compact_event["source_excerpts"] < compact_event["original_selected_blocks"]
    assert len(engine.fact_ledger.as_list()) > len(engine.fact_ledger.compact_list())
    assert engine.usage.calls <= request.options.max_calls
    for body in summaries:
        for source in body["sources"]:
            assert source["text"] == package.documents[0].text[source["start"] : source["end"]]


@pytest.mark.asyncio
async def test_cannot_approve_after_scan_when_independent_review_budget_insufficient(settings):
    settings = settings.model_copy(update={"context_window": 18000})
    package = long_package()
    scanned = {"generation": set(), "verification": set()}

    async def emit(*args):
        pass

    request = RunCreate(
        questions=[Question(id="q1", package_id=package.id, text="Какое обеспечение заявки?")],
        options={"max_calls": 14, "max_repairs": 0},
    )
    engine = Harness(FakeModel(behavior(scanned, [])), settings, request, emit, asyncio.Event())
    result = await engine.execute([package])
    assert result[0].status == "не знаю"
    assert any(
        check.code == "review_unavailable" and check.message == "call_budget_exhausted"
        for check in result[0].checks
    )
    assert engine.usage.calls <= 14
    assert not scanned["verification"]


@pytest.mark.asyncio
async def test_independent_synthesis_preserves_small_answer_when_other_question_cannot_fit(
    settings,
):
    settings = settings.model_copy(update={"context_window": 18000})
    text = "\n".join(
        f"Уникальный пункт {i}: дополнительные условия договора и ограничения." for i in range(1800)
    )
    package = Package(
        code="P",
        name="Two questions",
        documents=[
            Document(name="small.txt", text=EARLY, sha256="small"),
            Document(name="large.txt", text=text, sha256="large"),
        ],
    )
    generated = []

    async def emit(*args):
        pass

    def complete(kwargs, _):
        body = json.loads(kwargs["messages"][-1]["content"])
        if kwargs["messages"][0]["content"].startswith("Scan ORIGINAL"):
            return reply(
                {
                    "selections": [
                        {
                            "id": qid,
                            "span_ids": [
                                s["span_id"] for s in body["sources"] if s["file"] == name
                            ],
                        }
                        for qid, name in [("q1", "small.txt"), ("q2", "large.txt")]
                    ]
                }
            )
        assert [q["id"] for q in body["questions"]] == ["q1"]
        generated.append("q1")
        source = next(s for s in body["sources"] if EARLY in s["text"])
        return reply(
            {
                "answers": [
                    {
                        "id": "q1",
                        "status": "ответ",
                        "answer": "18000 рублей",
                        "evidence": [{"span_id": source["span_id"], "quote": EARLY}],
                    }
                ]
            }
        )

    request = RunCreate(
        questions=[Question(id=qid, package_id=package.id, text="Вопрос") for qid in ["q1", "q2"]],
        options={"semantic_review": False},
    )
    engine = Harness(FakeModel(complete), settings, request, emit, asyncio.Event())
    result = await engine.execute([package])
    assert result[0].answer == "18000 рублей"
    assert result[1].status == "не знаю"
    assert result[1].reason == "context_budget_exceeded"
    assert generated == ["q1"]
