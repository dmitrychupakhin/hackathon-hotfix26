import csv
import hashlib
import io
import json
import math
from collections import Counter, defaultdict

from app.domain import DomainError, now, uid
from app.services.official_checker import judge, norm


def export_csv(run):
    buffer = io.StringIO(newline="")
    writer = csv.DictWriter(
        buffer,
        fieldnames=["id", "status", "answer", "quote", "file"],
        delimiter=";",
        lineterminator="\n",
    )
    writer.writeheader()
    for answer in run["result"]["answers"]:
        # Organizer load_answers uses splitlines(); normalize line breaks only
        # in the export, preserving exact original evidence in the run JSON.
        writer.writerow(
            {key: " ".join((answer.get(key) or "").splitlines()) for key in writer.fieldnames}
        )
    return buffer.getvalue()


def evaluate_run(run: dict, references: list[dict]):
    if run["status"] != "completed":
        raise DomainError(
            "run_not_completed",
            "Technical failures have no factual-accuracy score; inspect partial answers and error",
            409,
        )
    questions = {q["id"]: q for q in run["request"]["questions"]}
    if len(references) != len(questions) or {r.get("id") for r in references} != set(questions):
        raise DomainError(
            "reference_scope_mismatch", "Reference IDs must match this run's questions exactly", 422
        )
    packages = {p["id"]: p for p in run["snapshot"]["packages"]}
    answer_rows = list(csv.DictReader(io.StringIO(export_csv(run)), delimiter=";"))
    answers = {a["id"]: a for a in answer_rows}
    original_answers = {a["id"]: a for a in run["result"]["answers"]}
    rows = []
    counts = Counter()
    grouped = defaultdict(Counter)
    for reference in references:
        q = questions[reference["id"]]
        package = packages[q["package_id"]]
        if reference.get("package") != package["code"]:
            raise DomainError(
                "reference_package_mismatch", "Reference package does not match the question", 422
            )
        if (
            reference.get("status") not in {"ответ", "расхождение", "нет в документах"}
            or reference.get("kind") not in {"num", "date", "yes", "no", "all_kw", "absent"}
            or not isinstance(reference.get("expected"), list)
            or not isinstance(reference.get("type"), str)
        ):
            raise DomainError(
                "invalid_reference", "Invalid reference status, kind, expected values or type", 422
            )
        if reference["kind"] == "num" and any(
            type(v) not in {int, float} or not math.isfinite(v) for v in reference["expected"]
        ):
            raise DomainError(
                "invalid_reference", "Numeric references must contain finite numbers", 422
            )
        if reference["kind"] == "date" and (
            len(reference["expected"]) != 2
            or not all(isinstance(v, str) for v in reference["expected"])
        ):
            raise DomainError(
                "invalid_reference", "Date references require date and time strings", 422
            )
        docs = {d["name"]: norm(d["text"]) for d in package["documents"]}
        try:
            verdict, reason = judge(reference, answers.get(reference["id"]), docs)
        except (TypeError, KeyError, AttributeError):
            raise DomainError(
                "invalid_reference", "Reference values cannot be evaluated", 422
            ) from None
        counts[verdict] += 1
        grouped[reference["type"]][verdict] += 1
        original = original_answers.get(reference["id"], {})
        rows.append(
            {
                "id": reference["id"],
                "type": reference["type"],
                "verdict": verdict,
                "reason": reason,
                "question": q["text"],
                "answer": answers.get(reference["id"]),
                "evidence": original.get("evidence", []),
                "checks": original.get("checks", []),
                "validation_failures": [],
            }
        )
    n = len(questions)
    input_signature = {
        "questions": run["request"]["questions"],
        "revisions": run["source_revisions"],
        "history": run["snapshot"].get("history", []),
        "question_grouping": run["request"].get("options", {}).get("question_grouping")
        or (
            "legacy_all_packages"
            if run["mode"] in {"baseline", "plain", "raw"} and len(packages) > 1
            else "per_package"
        ),
    }
    return {
        "id": uid(),
        "run_id": run["id"],
        "created_at": now(),
        "model": run["model"],
        "base_url": run.get("base_url"),
        "mode": run["mode"],
        "grouping": input_signature["question_grouping"],
        "source_revisions": run["source_revisions"],
        "run_metrics": run["metrics"],
        "prompt_hashes": run["prompt_hashes"],
        "prompt_snapshots": run["snapshot"].get("prompts", {}),
        "effective_options": run["request"].get("options", {}),
        "reference_hash": hashlib.sha256(
            json.dumps(
                sorted(references, key=lambda r: r["id"]), ensure_ascii=False, sort_keys=True
            ).encode()
        ).hexdigest(),
        "input_signature": hashlib.sha256(
            json.dumps(input_signature, sort_keys=True).encode()
        ).hexdigest(),
        "questions": n,
        "correct": counts["верно"],
        "errors": counts["обман"],
        "careful": counts["осторожно"],
        "trust_index": round((counts["верно"] - counts["обман"]) / n * 100, 1) if n else 0,
        "by_type": {kind: dict(values) for kind, values in grouped.items()},
        "rows": rows,
        "warning": "Raw mode without status fields is not a factual-accuracy score."
        if run["mode"] == "raw"
        else "Official score does not prove complete semantic correctness; inspect evidence and validation traces.",
    }


def compare_evaluations(before: dict, after: dict):
    if before.get("base_url") != after.get("base_url"):
        raise DomainError(
            "different_providers",
            "Before/after evaluation must use the same provider base URL",
            422,
        )
    if before["model"] != after["model"]:
        raise DomainError(
            "different_models", "Before/after evaluation must use the same model", 422
        )
    returned_before = set(before.get("run_metrics", {}).get("returned_models", []))
    returned_after = set(after.get("run_metrics", {}).get("returned_models", []))
    if returned_before and returned_after and returned_before != returned_after:
        raise DomainError(
            "different_returned_models",
            "Provider returned different model versions; paired delta is not comparable",
            422,
        )
    if (
        before["reference_hash"] != after["reference_hash"]
        or before["input_signature"] != after["input_signature"]
    ):
        raise DomainError(
            "different_inputs",
            "Before/after runs must use identical questions, source versions and references",
            422,
        )
    earlier = {row["id"]: row for row in before["rows"]}
    changed = [
        {"id": row["id"], "before": earlier[row["id"]], "after": row}
        for row in after["rows"]
        if row["verdict"] != earlier[row["id"]]["verdict"]
    ]
    return {
        "changed_questions": changed,
        "before": before,
        "after": after,
        "delta": {
            key: round(after[key] - before[key], 1)
            for key in ("correct", "errors", "careful", "trust_index")
        },
        "warning": "One paired run is an observation, not a statistical guarantee. Raw mode has a different output contract."
        if "raw" in {before["mode"], after["mode"]}
        else "One paired run is an observation, not a statistical guarantee.",
    }
