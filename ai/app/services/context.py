"""Budgeted batches of original blocks; no source truncation or generated summaries."""

from app.domain import DomainError


def compact_sources(sources, facts, *, margin=160):
    """Exact source slices, not generated summaries or a relevance top-K.

    A selected block without validated facts is kept in full. Repeated text is
    collapsed only inside the same document version; all distinct alternatives
    remain. Coordinates and IDs always refer to the original source.
    """
    quotes = {}
    for fact in facts:
        for ref in fact["evidence"]:
            quotes.setdefault(ref["span_id"], []).append(ref["quote"])
    result, seen = [], {}
    for source in sources:
        text = source["text"]
        intervals = []
        for quote in quotes.get(source["span_id"], []):
            position = text.find(quote)
            if position >= 0:
                intervals.append(
                    (max(0, position - margin), min(len(text), position + len(quote) + margin))
                )
        if not intervals:
            intervals = [(0, len(text))]
        merged = []
        for start, end in sorted(intervals):
            if merged and start <= merged[-1][1]:
                merged[-1] = (merged[-1][0], max(end, merged[-1][1]))
            else:
                merged.append((start, end))
        for start, end in merged:
            excerpt = text[start:end]
            # No cross-document dedup: identical clauses in two contracts may
            # have different authority, which the critic must be able to see.
            key = (source.get("document_id", source["file"]), source.get("source_hash"), excerpt)
            if key in seen:
                result[seen[key]]["occurrences"] += 1
                continue
            seen[key] = len(result)
            result.append(
                {
                    **source,
                    "text": excerpt,
                    "start": source.get("start", 0) + start,
                    "end": source.get("start", 0) + end,
                    "original_span_start": source.get("start", 0),
                    "original_span_end": source.get("end", len(text)),
                    "occurrences": 1,
                }
            )
    return result


def source_batches(sources, fits):
    batches = []
    batch = []
    for source in sources:
        if fits(batch + [source]):
            batch.append(source)
            continue
        if not batch:
            raise DomainError(
                "context_budget_exceeded", "One source block exceeds the context budget", 422
            )
        batches.append(batch)
        # One original block of overlap preserves local clause continuity where possible.
        overlap = batch[-1:]
        batch = overlap + [source] if fits(overlap + [source]) else [source]
        if not fits(batch):
            raise DomainError(
                "context_budget_exceeded", "One source block exceeds the context budget", 422
            )
    if batch:
        batches.append(batch)
    return batches
