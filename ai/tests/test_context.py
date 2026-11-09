import asyncio
import json

import pytest
from conftest import FakeModel, reply

from app.domain import Candidate, Package, Question, RunCreate, TextDocument
from app.services.context import source_batches
from app.services.documents import document_from_text, with_documents
from app.services.harness import Harness
from app.services.tools import ToolBox
from app.services.validation import validate


def test_batches_preserve_tail_and_overlap():
    sources = list(range(9))
    batches = source_batches(sources, lambda values: len(values) <= 3)
    assert {v for batch in batches for v in batch} == set(sources)
    assert batches[-1][-1] == 8
    assert all(a[-1] == b[0] for a, b in zip(batches, batches[1:]))


def large_package(settings):
    return with_documents(
        Package(code="P01", name="Long"),
        [
            document_from_text(
                TextDocument(
                    name="notice.txt",
                    text="Общие условия исполнения. " * 4000
                    + "\nОбеспечение заявки: 18000 рублей.",
                ),
                settings,
            )
        ],
        settings,
    )


@pytest.mark.asyncio
async def test_long_package_scans_all_originals_and_independently_checks_again(settings):
    settings = settings.model_copy(update={"context_window": 18000})
    package = large_package(settings)
    scanned = {"generation": set(), "verification": set()}
    events = []

    async def emit(kind, data):
        events.append((kind, data))

    def behavior(kwargs, _):
        body = json.loads(kwargs["messages"][-1]["content"])
        system = kwargs["messages"][0]["content"]
        if system.startswith("Scan ORIGINAL"):
            stage = "verification" if "proposed" in body else "generation"
            scanned[stage].update(s["span_id"] for s in body["sources"])
            chosen = [s["span_id"] for s in body["sources"] if "18000" in s["text"]]
            return reply({"selections": [{"id": "q1", "span_ids": chosen}]})
        if system.startswith("Review proposed"):
            assert body["documents_complete"]
            assert "independent_scan" in body["source_mode"]
            return reply(
                {"reviews": [{"id": "q1", "verdict": "supported", "reason": "Подтверждено"}]}
            )
        original = json.loads(kwargs["messages"][1]["content"])
        source = next(s for s in original["sources"] if "18000" in s["text"])
        return reply(
            {
                "answers": [
                    {
                        "id": "q1",
                        "status": "ответ",
                        "answer": "18000 руб.",
                        "evidence": [
                            {
                                "span_id": source["span_id"],
                                "quote": "Обеспечение заявки: 18000 рублей.",
                            }
                        ],
                    }
                ]
            }
        )

    request = RunCreate(
        questions=[Question(id="q1", package_id=package.id, text="Размер обеспечения?")]
    )
    engine = Harness(FakeModel(behavior), settings, request, emit, asyncio.Event())
    result = await engine.execute([package])
    assert result[0].status == "ответ"
    all_ids = set(ToolBox(package).spans)
    assert scanned["generation"] == scanned["verification"] == all_ids
    assert engine.usage.calls > 4
    assert any(kind == "context.batch_scanned" for kind, _ in events)


@pytest.mark.asyncio
async def test_independent_scan_finds_unquoted_contradiction(settings):
    settings = settings.model_copy(update={"context_window": 18000})
    package = large_package(settings)
    package = with_documents(
        package,
        [
            document_from_text(
                TextDocument(name="contract.txt", text="Обеспечение заявки: 75000 рублей."),
                settings,
            )
        ],
        settings,
    )
    tools = ToolBox(package)
    span = next(s for s in tools.spans.values() if "18000" in s.text)
    candidate = Candidate(
        id="q1", status="ответ", answer="18000 рублей", evidence=[{"span_id": span.id}]
    )
    answer, failures = validate(candidate, tools)
    assert not failures

    def behavior(kwargs, _):
        body = json.loads(kwargs["messages"][-1]["content"])
        if kwargs["messages"][0]["content"].startswith("Scan ORIGINAL"):
            return reply(
                {
                    "selections": [
                        {
                            "id": "q1",
                            "span_ids": [
                                s["span_id"] for s in body["sources"] if "75000" in s["text"]
                            ],
                        }
                    ]
                }
            )
        assert any("75000" in s["text"] for s in body["sources"])
        return reply(
            {"reviews": [{"id": "q1", "verdict": "revise", "reason": "Найдено второе значение"}]}
        )

    async def emit(*args):
        pass

    request = RunCreate(
        questions=[Question(id="q1", package_id=package.id, text="Размер обеспечения?")]
    )
    engine = Harness(FakeModel(behavior), settings, request, emit, asyncio.Event())
    reviews = await engine._review(package, tools, [candidate], {"q1": answer}, request.questions)
    assert not reviews["q1"].passed
