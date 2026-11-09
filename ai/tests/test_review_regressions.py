import asyncio
import copy
import json
from decimal import Decimal

import pytest
from conftest import FakeModel, reply

from app.domain import Candidate, DomainError, Package, Question, RunCreate, TextDocument
from app.infrastructure.store import Store
from app.services import official_checker
from app.services.documents import document_from_text, with_documents
from app.services.evaluation import compare_evaluations, evaluate_run, export_csv
from app.services.harness import Harness
from app.services.runner import Runner
from app.services.tools import ToolBox
from app.services.validation import numbers, validate


def source_package(settings, text):
    return with_documents(
        Package(code="P01", name="Test"),
        [document_from_text(TextDocument(name="notice.txt", text=text), settings)],
        settings,
    )


@pytest.mark.parametrize("second_action", ["cancel", "shutdown", "task_cancel"])
async def test_cancellation_during_finalization_persists_terminal_state(
    settings, monkeypatch, second_action
):
    store = Store(settings.db_file)
    await store.open()
    entered_model = asyncio.Event()
    entered_finalization = asyncio.Event()
    release_finalization = asyncio.Event()

    async def blocking_model(_kwargs, _count):
        entered_model.set()
        await asyncio.Event().wait()

    runner = Runner(store, FakeModel(blocking_model), settings)
    original_patch = store.patch_run

    async def delayed_patch(run_id, owner, patch, event_type=None, event_data=None):
        if event_type == "run.cancelled":
            entered_finalization.set()
            await release_finalization.wait()
        return await original_patch(run_id, owner, patch, event_type, event_data)

    monkeypatch.setattr(store, "patch_run", delayed_patch)
    closing = None
    try:
        package = source_package(settings, "Размер обеспечения: 18000 рублей.")
        await store.create("package", package.model_dump(), "owner")
        await store.create(
            "session", {"id": "session", "package_id": package.id, "messages": []}, "owner"
        )
        run = await runner.submit(
            RunCreate(
                session_id="session",
                questions=[Question(id="q", package_id=package.id, text="Какой размер?")],
            ),
            "owner",
        )
        task = runner.tasks[run["id"]]
        await asyncio.wait_for(entered_model.wait(), 2)
        await runner.cancel(run["id"], "owner")
        await asyncio.wait_for(entered_finalization.wait(), 2)
        if second_action == "cancel":
            await asyncio.gather(
                runner.cancel(run["id"], "owner"), runner.cancel(run["id"], "owner")
            )
        elif second_action == "shutdown":
            closing = asyncio.create_task(runner.close())
            await asyncio.sleep(0)
        else:
            task.cancel()
            await asyncio.sleep(0)
        release_finalization.set()
        await asyncio.wait_for(task, 2)
        if closing:
            await closing
        saved = await store.get("run", run["id"], "owner")
        assert saved["status"] == "cancelled"
        events = await store.events(run["id"], "owner")
        assert sum(event["type"] == "run.cancel_requested" for event in events) == 1
        assert sum(event["type"] == "run.cancelled" for event in events) == 1
        assert saved["result"]["answers"][0]["status"] == "не знаю"
        session = await store.get("session", "session", "owner")
        assert [m["role"] for m in session["messages"]] == ["user", "assistant"]
        assert not runner.active_sessions
        assert not runner.signals
        assert not runner.finalizing
    finally:
        release_finalization.set()
        await runner.close()
        await store.close()


async def test_verified_calculation_reaches_semantic_reviewer(settings):
    package = source_package(settings, "Цена: 100 рублей. Обеспечение: 20 процентов.")
    tools = ToolBox(package)
    tools.full_context()
    candidate = Candidate(
        id="q",
        status="ответ",
        answer="20 рублей",
        evidence=[{"span_id": next(iter(tools.spans))}],
        calculation={"operation": "percentage", "operands": ["100", "20"], "result": "20"},
    )
    answer, failures = validate(candidate, tools)
    assert not failures
    assert answer.model_dump()["calculation"] == candidate.calculation.model_dump()

    def reviewer(kwargs, _count):
        payload = json.loads(kwargs["messages"][-1]["content"])
        assert payload["proposed"][0]["calculation"] == candidate.calculation.model_dump()
        return reply({"reviews": [{"id": "q", "verdict": "supported", "reason": "Verified"}]})

    async def emit(_event, _data):
        pass

    question = Question(id="q", package_id=package.id, text="Размер обеспечения в рублях?")
    engine = Harness(
        FakeModel(reviewer), settings, RunCreate(questions=[question]), emit, asyncio.Event()
    )
    reviews = await engine._review(package, tools, [candidate], {"q": answer}, [question])
    assert reviews["q"].passed


def test_sign_change_rejected_and_negative_calculation_accepted(settings):
    tools = ToolBox(source_package(settings, "Цена: 100 рублей; изменение: −20 рублей."))
    evidence = [{"span_id": next(iter(tools.spans))}]
    incorrect = Candidate(id="q", status="ответ", answer="+20 рублей", evidence=evidence)
    assert any(c.code == "numbers" for c in validate(incorrect, tools)[1])
    correct = Candidate(
        id="q",
        status="ответ",
        answer="−120 рублей",
        evidence=evidence,
        calculation={"operation": "subtract", "operands": ["−20", "100"], "result": "−120"},
    )
    assert not validate(correct, tools)[1]


@pytest.mark.parametrize(
    "text, expected",
    [
        ("2026-11-07", {"2026", "11", "7"}),
        ("от 10-20 дней", {"10", "20"}),
        ("от 10 - 20 дней", {"10", "20"}),
        ("Изменение − 20 рублей", {"-20"}),
        ("Значения: -20,-10", {"-20", "-10"}),
    ],
)
def test_number_signs_preserve_dates_and_ranges(text, expected):
    assert numbers(text) == {Decimal(value) for value in expected}


@pytest.mark.parametrize(
    "separator",
    ["\r\n", "\r", "\n", "\v", "\f", "\x1c", "\x1d", "\x1e", "\x85", "\u2028", "\u2029"],
)
def test_csv_unicode_lines_match_official_loader(separator, monkeypatch):
    quote = f"Цена:{separator}18000 рублей."
    row = {
        "id": "q",
        "status": "ответ",
        "answer": "18000 рублей",
        "quote": quote,
        "file": "notice.txt",
    }
    exported = export_csv({"result": {"answers": [row]}})
    monkeypatch.setattr(official_checker, "read_file", lambda _path: exported)
    loaded = official_checker.load_answers("unused.csv")
    assert set(loaded) == {"q"}
    assert loaded["q"]["quote"] == "Цена: 18000 рублей."
    assert row["quote"] == quote
    verdict, _ = official_checker.judge(
        {"status": "ответ", "kind": "num", "expected": [18000]},
        loaded["q"],
        {"notice.txt": official_checker.norm(quote)},
    )
    assert verdict == "верно"


def test_comparison_rejects_different_dialogue_histories(settings):
    package = source_package(settings, "Обеспечение: 18000 рублей.")
    run = {
        "id": "r",
        "status": "completed",
        "model": "test-model",
        "mode": "harness",
        "request": {"questions": [{"id": "q", "package_id": package.id, "text": "А размер?"}]},
        "snapshot": {
            "packages": [package.model_dump()],
            "history": [{"role": "user", "content": "Обсудим заявку"}],
        },
        "result": {"answers": [{"id": "q", "status": "не знаю"}]},
        "source_revisions": {package.id: package.revision},
        "metrics": {},
        "prompt_hashes": {},
    }
    refs = [
        {
            "id": "q",
            "package": "P01",
            "status": "ответ",
            "kind": "num",
            "expected": [18000],
            "type": "цена",
        }
    ]
    first = evaluate_run(run, refs)
    same = evaluate_run(copy.deepcopy(run), refs)
    assert compare_evaluations(first, same)["delta"]["trust_index"] == 0
    run["snapshot"]["history"][0]["content"] = "Обсудим контракт"
    different = evaluate_run(run, refs)
    with pytest.raises(DomainError, match="identical questions"):
        compare_evaluations(first, different)
