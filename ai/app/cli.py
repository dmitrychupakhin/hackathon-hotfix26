"""CLI for reproducible dataset import, runs, exports and isolated evaluation."""

import argparse
import csv
import json
import sys
import time
from pathlib import Path

import httpx

from app.config import get_settings
from app.services.documents import decode_text


def dataset_payload(directory: Path):
    with (directory / "questions.csv").open(encoding="utf-8-sig", newline="") as stream:
        questions = list(csv.DictReader(stream, delimiter=";"))
    packages = []
    for path in sorted((directory / "packages").iterdir()):
        if not path.is_dir():
            continue
        documents = [
            {"name": f.name, "text": decode_text(f.read_bytes())[0]}
            for f in sorted(path.glob("*"))
            if f.is_file() and f.suffix.lower() in {".txt", ".md"}
        ]
        packages.append({"code": path.name, "name": path.name, "documents": documents})
    return {"name": directory.name, "packages": packages, "questions": questions}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--api-url", default="http://127.0.0.1:8010")
    parser.add_argument("--user-id", default="local")
    commands = parser.add_subparsers(dest="command", required=True)
    importing = commands.add_parser("import")
    importing.add_argument("directory", type=Path)
    running = commands.add_parser("run")
    running.add_argument("dataset_id")
    running.add_argument(
        "--mode", choices=["plain", "harness", "raw", "baseline"], default="harness"
    )
    running.add_argument("--model")
    running.add_argument("--output", type=Path, required=True)
    running.add_argument("--references", type=Path)
    running.add_argument("--timeout", type=int, default=900)
    evaluating = commands.add_parser("evaluate")
    evaluating.add_argument("run_id")
    evaluating.add_argument("references", type=Path)
    comparing = commands.add_parser("compare")
    comparing.add_argument("before_evaluation_id")
    comparing.add_argument("after_evaluation_id")
    args = parser.parse_args()
    settings = get_settings()
    headers = {"X-User-ID": args.user_id}
    if settings.service_key.get_secret_value():
        headers["X-AI-Service-Key"] = settings.service_key.get_secret_value()

    with httpx.Client(
        base_url=args.api_url.rstrip("/") + "/api/v1/", headers=headers, timeout=30
    ) as client:

        def call(method, path, **kwargs):
            response = client.request(method, path, **kwargs)
            if response.is_error:
                print(f"API error {response.status_code}: {response.text}", file=sys.stderr)
                raise SystemExit(1)
            return response

        if args.command == "import":
            print(
                json.dumps(
                    call("POST", "datasets", json=dataset_payload(args.directory)).json(),
                    ensure_ascii=False,
                    indent=2,
                )
            )
        elif args.command == "evaluate":
            references = json.loads(args.references.read_text(encoding="utf-8"))
            print(
                json.dumps(
                    call(
                        "POST",
                        f"runs/{args.run_id}/evaluate",
                        json={"reference_answers": references},
                    ).json(),
                    ensure_ascii=False,
                    indent=2,
                )
            )
        elif args.command == "compare":
            print(
                json.dumps(
                    call(
                        "POST",
                        "comparisons",
                        json={
                            "before_evaluation_id": args.before_evaluation_id,
                            "after_evaluation_id": args.after_evaluation_id,
                        },
                    ).json(),
                    ensure_ascii=False,
                    indent=2,
                )
            )
        else:
            body = {"mode": args.mode}
            if args.model:
                body["model"] = args.model
            run = call("POST", f"datasets/{args.dataset_id}/runs", json=body).json()
            run_id = run["id"]
            print(f"Run: {run_id}", file=sys.stderr)
            started = time.monotonic()
            try:
                while run["status"] not in {"completed", "failed", "cancelled", "interrupted"}:
                    if time.monotonic() - started > args.timeout:
                        call("POST", f"runs/{run_id}/cancel")
                        raise SystemExit("Wait timeout; cancellation requested")
                    time.sleep(1)
                    run = call("GET", f"runs/{run_id}").json()
            except KeyboardInterrupt:
                call("POST", f"runs/{run_id}/cancel")
                raise SystemExit(130) from None
            args.output.mkdir(parents=True, exist_ok=True)
            (args.output / "run.json").write_text(
                json.dumps(run, ensure_ascii=False, indent=2) + "\n"
            )
            (args.output / "answers.csv").write_bytes(
                call("GET", f"runs/{run_id}/answers.csv").content
            )
            (args.output / "inputs.json").write_text(
                json.dumps(
                    call("GET", f"runs/{run_id}/inputs").json(), ensure_ascii=False, indent=2
                )
                + "\n"
            )
            events, cursor = [], 0
            while True:
                page = call(
                    "GET", f"runs/{run_id}/events", params={"after": cursor, "limit": 500}
                ).json()
                if not page:
                    break
                events.extend(page)
                cursor = page[-1]["seq"]
            (args.output / "events.json").write_text(
                json.dumps(events, ensure_ascii=False, indent=2) + "\n"
            )
            if args.references:
                evaluation = call(
                    "POST",
                    f"runs/{run_id}/evaluate",
                    json={"reference_answers": json.loads(args.references.read_text())},
                ).json()
                (args.output / "evaluation.json").write_text(
                    json.dumps(evaluation, ensure_ascii=False, indent=2) + "\n"
                )
            print(
                json.dumps(
                    {
                        "run_id": run_id,
                        "status": run["status"],
                        "metrics": run["metrics"],
                        "output": str(args.output),
                    },
                    ensure_ascii=False,
                    indent=2,
                )
            )
            if run["status"] != "completed":
                raise SystemExit(1)


if __name__ == "__main__":
    main()
