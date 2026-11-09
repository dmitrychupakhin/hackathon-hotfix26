"""Lossless organizer CSV/JSON parsing. No model may rewrite the gold standard."""

import csv
import io
import json
import math

from app.domain import DomainError, Question


def parse_inputs(questions_text: str, references_text: str):
    try:
        reader = csv.DictReader(io.StringIO(questions_text.lstrip("\ufeff")), delimiter=";")
        if reader.fieldnames != ["id", "package", "question"]:
            raise ValueError
        source = list(reader)
        if not 1 <= len(source) <= 200 or any(set(r) != set(reader.fieldnames) for r in source):
            raise ValueError
        questions = [
            Question(id=r["id"], package_id=r["package"], text=r["question"]) for r in source
        ]
        if any(not q.package_id or q.package_id.strip() != q.package_id for q in questions):
            raise ValueError
        by_id = {q.id: q for q in questions}
        if len(by_id) != len(questions):
            raise ValueError
        refs = json.loads(references_text.lstrip("\ufeff"))
        if not isinstance(refs, list) or len(refs) != len(questions):
            raise ValueError
        if {r["id"] for r in refs} != set(by_id):
            raise ValueError
        for r in refs:
            if (
                r["package"] != by_id[r["id"]].package_id
                or r["status"] not in {"ответ", "расхождение", "нет в документах"}
                or r["kind"] not in {"num", "date", "yes", "no", "all_kw", "absent"}
                or not isinstance(r["type"], str)
                or not r["type"]
                or not isinstance(r["expected"], list)
            ):
                raise ValueError
            values = r["expected"]
            if r["kind"] == "num":
                if not values or any(
                    type(v) not in (int, float) or not math.isfinite(v) for v in values
                ):
                    raise ValueError
            elif r["kind"] == "date":
                if len(values) != 2 or not all(isinstance(v, str) and v for v in values):
                    raise ValueError
            elif r["kind"] == "absent":
                if values or r["status"] != "нет в документах":
                    raise ValueError
            elif not values or not all(isinstance(v, str) and v for v in values):
                raise ValueError
            if r["status"] == "нет в документах" and r["kind"] != "absent":
                raise ValueError
        return questions, refs
    except (ValueError, TypeError, KeyError, AttributeError, OverflowError):
        raise DomainError(
            "invalid_comparison_inputs",
            "Use original questions.csv (id;package;question) and answers_public.json with exactly matching IDs/packages. Values are not inferred or rewritten.",
            422,
        ) from None
