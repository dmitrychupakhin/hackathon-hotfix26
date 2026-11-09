"""Optional paid provider integration check on a tiny synthetic package."""

import argparse
import asyncio
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.config import get_settings  # noqa: E402
from app.domain import Package, Question, RunCreate, RunOptions, TextDocument  # noqa: E402
from app.infrastructure.llm import ApiMira  # noqa: E402
from app.services.documents import document_from_text, with_documents  # noqa: E402
from app.services.harness import Harness  # noqa: E402


async def run():
    settings = get_settings().model_copy(update={"max_output_tokens": 2000, "max_model_calls": 4})
    package = Package(code="SMOKE", name="Synthetic smoke test")
    package = with_documents(
        package,
        [
            document_from_text(
                TextDocument(
                    name="notice.txt",
                    text="Синтетическая закупка. Размер обеспечения заявки: 18 000 рублей. Обеспечение исполнения контракта: 5 процентов.",
                ),
                settings,
            )
        ],
        settings,
    )
    request = RunCreate(
        model=settings.model,
        questions=[
            Question(
                id="SMOKE-01",
                package_id=package.id,
                text="Какой размер обеспечения заявки в рублях?",
            )
        ],
        options=RunOptions(
            max_calls=4, max_repairs=1, max_rounds_per_package=4, timeout_seconds=150
        ),
    )
    events = []

    async def emit(event_type, data):
        events.append({"type": event_type, "data": data})

    provider = ApiMira(settings)
    engine = Harness(provider, settings, request, emit, asyncio.Event())
    started = time.monotonic()
    try:
        async with asyncio.timeout(150):
            answers = await engine.execute([package])
    finally:
        await provider.close()
    result = {
        "synthetic_test": True,
        "model": settings.model,
        "elapsed_seconds": round(time.monotonic() - started, 3),
        "metrics": engine.usage.snapshot(settings),
        "answers": [a.model_dump(mode="json") for a in answers],
        "events": events,
    }
    output = ROOT / "output" / "live-smoke.json"
    output.parent.mkdir(exist_ok=True)
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    answer = answers[0]
    passed = (
        answer.status == "ответ"
        and "18000" in answer.answer.replace(" ", "").replace("\u00a0", "")
        and any(c.code == "semantic_review" and c.passed for c in answer.checks)
    )
    print(
        json.dumps(
            {
                "passed": passed,
                "model": settings.model,
                "elapsed_seconds": result["elapsed_seconds"],
                "model_calls": engine.usage.calls,
                "usage": result["metrics"],
                "status": answer.status,
                "answer": answer.answer,
                "report": str(output),
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    if not passed:
        raise SystemExit(1)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--run", action="store_true", help="Authorize at most four paid model calls."
    )
    if parser.parse_args().run:
        asyncio.run(run())
    else:
        print("No API calls. Pass --run to execute the paid synthetic smoke test.")
