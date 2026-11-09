"""Provisional model findings anchored to original source coordinates.

A ledger validates citations, not semantic truth. It never turns a chunk-local
empty selection into a package-level absence verdict.
"""

from app.domain import DomainError

RELATIONS = {"support", "refute", "amendment", "exception"}


class FactLedger:
    def __init__(self):
        self._facts = {}

    def add_selection(self, row, spans, *, stage):
        facts = row.get("facts", [])
        if not isinstance(facts, list) or len(facts) > 100:
            self._invalid()
        additions = {}
        for fact in facts:
            if not isinstance(fact, dict) or set(fact) != {
                "field",
                "value",
                "unit",
                "condition",
                "relation",
                "evidence",
            }:
                self._invalid()
            if (
                any(
                    not isinstance(fact[k], str) or len(fact[k]) > 2000
                    for k in ("field", "value", "unit", "condition", "relation")
                )
                or not fact["field"].strip()
                or fact["relation"] not in RELATIONS
            ):
                self._invalid()
            refs = fact["evidence"]
            if not isinstance(refs, list) or not 1 <= len(refs) <= 20:
                self._invalid()
            coordinates = []
            evidence = []
            for ref in refs:
                if not isinstance(ref, dict) or set(ref) != {"span_id", "quote"}:
                    self._invalid()
                span_id, quote = ref["span_id"], ref["quote"]
                if not isinstance(span_id, str) or span_id not in spans:
                    self._invalid()
                span = spans[span_id]
                if not isinstance(quote, str) or len(quote.strip()) < 8 or quote not in span.text:
                    self._invalid()
                start = span.start + span.text.index(quote)
                end = start + len(quote)
                coordinate = (span.document_id, span.source_hash, start, end)
                if coordinate in coordinates:
                    continue
                coordinates.append(coordinate)
                evidence.append(
                    {
                        "span_id": span_id,
                        "document_id": span.document_id,
                        "source_hash": span.source_hash,
                        "file": span.file,
                        "start": start,
                        "end": end,
                        "quote": quote,
                    }
                )
            key = (
                row["id"],
                *(fact[k].strip() for k in ("field", "value", "unit", "condition", "relation")),
                tuple(sorted(coordinates)),
            )
            if key in self._facts:
                self._facts[key]["observed_in"].add(stage)
                continue
            additions[key] = {
                "question_id": row["id"],
                **{k: fact[k] for k in fact if k != "evidence"},
                "evidence": evidence,
                "observed_in": {stage},
                "provisional": True,
            }
        self._facts.update(additions)

    def merge(self, other):
        for key, value in other._facts.items():
            if key in self._facts:
                self._facts[key]["observed_in"].update(value["observed_in"])
            else:
                self._facts[key] = value

    def as_list(self, question_ids=None):
        return [
            {**fact, "observed_in": sorted(fact["observed_in"])}
            for fact in self._facts.values()
            if question_ids is None or fact["question_id"] in question_ids
        ]

    def compact_list(self, question_ids=None):
        """Prompt view only: collapse identical repeated findings, never alternatives.

        The full coordinate ledger remains untouched for audit. Identical text in
        a different document/version, or a different condition/relation, is not
        interchangeable and must still reach the generator and critic.
        """
        grouped = {}
        for fact in self.as_list(question_ids):
            key = (
                fact["question_id"],
                *(fact[k] for k in ("field", "value", "unit", "condition", "relation")),
                tuple(
                    sorted(
                        (r["document_id"], r["source_hash"], r["quote"]) for r in fact["evidence"]
                    )
                ),
            )
            if key not in grouped:
                grouped[key] = {**fact, "occurrences": 1}
            else:
                existing = grouped[key]
                existing["occurrences"] += 1
                existing["observed_in"] = sorted(
                    set(existing["observed_in"]) | set(fact["observed_in"])
                )
        return list(grouped.values())

    @staticmethod
    def _invalid():
        raise DomainError(
            "scan_facts_invalid",
            "Provisional facts contain invalid fields or source quotations",
            422,
        )
