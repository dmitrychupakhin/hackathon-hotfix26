import asyncio
import json

import pytest
from conftest import FakeModel, reply

from app.domain import Document, DomainError, Package, Question, RunCreate, Span
from app.services.facts import FactLedger
from app.services.harness import Harness


def span(sid="s1", start=0):
    text = "Обеспечение заявки: 18000 рублей."
    return Span(
        id=sid,
        document_id="d1",
        source_hash="hash",
        file="notice.txt",
        start=start,
        end=start + len(text),
        text=text,
    )


def selection(sid="s1", value="18000", relation="support"):
    return {
        "id": "q1",
        "span_ids": [sid],
        "facts": [
            {
                "field": "обеспечение заявки",
                "value": value,
                "unit": "рубли",
                "condition": "",
                "relation": relation,
                "evidence": [{"span_id": sid, "quote": "Обеспечение заявки: 18000 рублей."}],
            }
        ],
    }


def test_overlap_and_independent_scans_deduplicate_by_original_coordinates():
    ledger = FactLedger()
    ledger.add_selection(selection(), {"s1": span()}, stage="evidence_scan")
    ledger.add_selection(selection("s2"), {"s2": span("s2")}, stage="verification_scan")
    facts = ledger.as_list()
    assert len(facts) == 1
    assert facts[0]["observed_in"] == ["evidence_scan", "verification_scan"]
    assert facts[0]["provisional"]
    assert facts[0]["evidence"][0]["start"] == 0


def test_competing_values_and_amendments_are_never_overwritten():
    ledger = FactLedger()
    ledger.add_selection(selection(), {"s1": span()}, stage="evidence_scan")
    ledger.add_selection(
        selection(value="18000 (не применяется)", relation="amendment"),
        {"s1": span()},
        stage="verification_scan",
    )
    assert len(ledger.as_list()) == 2
    assert ledger.as_list({"other"}) == []


@pytest.mark.parametrize("mutation", ["quote", "foreign", "relation", "facts_type"])
def test_invalid_fact_is_rejected(mutation):
    row = selection()
    if mutation == "quote":
        row["facts"][0]["evidence"][0]["quote"] = "Несуществующая цитата"
    elif mutation == "foreign":
        row["facts"][0]["evidence"][0]["span_id"] = "foreign"
    elif mutation == "relation":
        row["facts"][0]["relation"] = "truth"
    else:
        row["facts"] = "bad"
    with pytest.raises(DomainError) as exc:
        FactLedger().add_selection(row, {"s1": span()}, stage="evidence_scan")
    assert exc.value.code == "scan_facts_invalid"


def test_old_selection_format_and_empty_chunk_do_not_infer_absence():
    ledger = FactLedger()
    ledger.add_selection({"id": "q1", "span_ids": []}, {}, stage="evidence_scan")
    assert ledger.as_list() == []


@pytest.mark.asyncio
async def test_late_fact_and_originals_reach_independent_critic(settings):
    settings = settings.model_copy(update={"context_window": 18000})
    early = "Обеспечение заявки: 18000 рублей."
    late = "Изменение извещения: обеспечение заявки теперь 27000 рублей."
    text = early + "\n" + "Общие условия исполнения. " * 4000 + "\n" + late
    package = Package(
        code="P", name="P", documents=[Document(name="notice.txt", text=text, sha256="hash")]
    )
    events = []

    async def emit(kind, data):
        events.append((kind, data))

    def behavior(kwargs, _):
        body = json.loads(kwargs["messages"][-1]["content"])
        system = kwargs["messages"][0]["content"]
        if system.startswith("Scan ORIGINAL"):
            rows = []
            refs = []
            for block in body["sources"]:
                for value, quote, relation in [
                    ("18000", early, "support"),
                    ("27000", late, "amendment"),
                ]:
                    if quote in block["text"]:
                        refs.append(block["span_id"])
                        rows.append(
                            {
                                "field": "обеспечение заявки",
                                "value": value,
                                "unit": "рубли",
                                "condition": "",
                                "relation": relation,
                                "evidence": [{"span_id": block["span_id"], "quote": quote}],
                            }
                        )
            return reply({"selections": [{"id": "q1", "span_ids": list(set(refs)), "facts": rows}]})
        if system.startswith("Review proposed"):
            assert {f["value"] for f in body["fact_ledger"]} == {"18000", "27000"}
            assert body["coverage"]["verification_scan"]["complete"]
            assert any(late in s["text"] for s in body["sources"])
            return reply(
                {
                    "reviews": [
                        {"id": "q1", "verdict": "supported", "reason": "Изменение явно меняет поле"}
                    ]
                }
            )
        body = json.loads(kwargs["messages"][1]["content"])
        assert {f["value"] for f in body["fact_ledger"]} == {"18000", "27000"}
        source = next(s for s in body["sources"] if late in s["text"])
        return reply(
            {
                "answers": [
                    {
                        "id": "q1",
                        "status": "ответ",
                        "answer": "27000 рублей",
                        "evidence": [{"span_id": source["span_id"], "quote": late}],
                    }
                ]
            }
        )

    request = RunCreate(
        questions=[Question(id="q1", package_id=package.id, text="Размер обеспечения?")]
    )
    engine = Harness(FakeModel(behavior), settings, request, emit, asyncio.Event())
    result = await engine.execute([package])
    assert result[0].answer == "27000 рублей"
    assert all(v["complete"] for v in engine.scan_coverage.values())
    assert any(
        kind == "context.batch_scanned" and data["provisional_facts"] for kind, data in events
    )


@pytest.mark.asyncio
async def test_audit_preserves_all_package_attempts_and_detaches_result(settings):
    packages = [
        Package(
            code=f"P{i}",
            name="Procurement",
            documents=[
                Document(
                    name="notice.txt", text="Обеспечение заявки: 18000 рублей.", sha256=f"hash{i}"
                )
            ],
        )
        for i in range(2)
    ]
    request = RunCreate(
        questions=[
            Question(id=f"q{i}", package_id=p.id, text="Обеспечение?")
            for i, p in enumerate(packages)
        ]
    )

    async def emit(*args):
        pass

    engine = Harness(FakeModel(), settings, request, emit, asyncio.Event())
    await engine.execute(packages)
    audit = engine.audit_state()
    assert set(audit) == {p.id for p in packages}
    assert all(v["attempts"][0]["read_complete"] for v in audit.values())
    assert audit[packages[0].id]["attempts"][0]["accepted_question_ids"] == ["q0"]
    audit[packages[0].id]["attempts"][0]["fact_ledger"].append({"bad": "mutation"})
    assert engine.audit_state()[packages[0].id]["attempts"][0]["fact_ledger"] == []


@pytest.mark.asyncio
async def test_large_configured_chunk_shrinks_to_fit_smaller_window(settings):
    settings = settings.model_copy(
        update={
            "context_window": 16384,
            "chunk_target_tokens": 16000,
            "chunk_overlap_tokens": 3000,
        }
    )
    tail = "Обеспечение заявки: 18000 рублей."
    text = "Общие условия исполнения. " * 3000 + "\n" + tail
    package = Package(
        code="P", name="P", documents=[Document(name="notice.txt", text=text, sha256="hash")]
    )
    events = []
    sizes = []

    async def emit(kind, data):
        events.append((kind, data))

    def behavior(kwargs, _):
        body = json.loads(kwargs["messages"][-1]["content"])
        system = kwargs["messages"][0]["content"]
        if system.startswith("Scan ORIGINAL"):
            sizes.extend(len(s["text"]) for s in body["sources"])
            return reply(
                {
                    "selections": [
                        {
                            "id": "q1",
                            "span_ids": [
                                s["span_id"] for s in body["sources"] if tail in s["text"]
                            ],
                        }
                    ]
                }
            )
        if system.startswith("Review proposed"):
            return reply(
                {"reviews": [{"id": "q1", "verdict": "supported", "reason": "Подтверждено"}]}
            )
        body = json.loads(kwargs["messages"][1]["content"])
        source = next(s for s in body["sources"] if tail in s["text"])
        return reply(
            {
                "answers": [
                    {
                        "id": "q1",
                        "status": "ответ",
                        "answer": "18000 рублей",
                        "evidence": [{"span_id": source["span_id"], "quote": tail}],
                    }
                ]
            }
        )

    engine = Harness(
        FakeModel(behavior),
        settings,
        RunCreate(questions=[Question(id="q1", package_id=package.id, text="Размер обеспечения?")]),
        emit,
        asyncio.Event(),
    )
    result = await engine.execute([package])
    assert result[0].answer == "18000 рублей"
    assert max(sizes) <= ((16384 - settings.max_output_tokens) // 4) * 2
    prepared = next(data for kind, data in events if kind == "context.prepared")
    assert prepared["chunk_target_tokens"] < prepared["configured_chunk_target_tokens"]
    assert prepared["chunk_overlap_tokens"] <= prepared["chunk_target_tokens"] // 4
    assert engine.scan_coverage["verification_scan"]["complete"]
