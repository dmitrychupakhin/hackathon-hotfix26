"""Exact source navigation metadata for plain answers, not factual verification."""

import hashlib

from app.domain import Answer, AnswerStatus, Package, Span


def attach_plain_anchor(answer: Answer, packages: list[Package], package_id: str) -> Answer:
    """Link only one exact occurrence in one explicitly named source.

    No normalization, model retry, answer correction or claim validation occurs.
    In particular, a real quote can accompany a false answer. Baseline/raw never
    call this helper, preserving their submission output and comparison policy.
    """
    if (
        answer.status not in {AnswerStatus.ANSWER, AnswerStatus.CONFLICT}
        or len(answer.quote.strip()) < 8
    ):
        return answer
    documents = [
        doc
        for package in packages
        if package.id == package_id
        for doc in package.documents
        if answer.file in {doc.name, doc.original_name}
    ]
    matches = []
    for doc in documents:
        start = doc.text.find(answer.quote)
        if start < 0:
            continue
        if doc.text.find(answer.quote, start + 1) >= 0:
            return answer
        matches.append((doc, start))
    if len(matches) != 1:
        return answer
    doc, start = matches[0]
    end = start + len(answer.quote)
    span = Span(
        id=hashlib.sha256(f"{doc.id}:{doc.sha256}:{start}:{end}".encode()).hexdigest()[:24],
        document_id=doc.id,
        file=doc.original_name or doc.name,
        source_hash=doc.sha256,
        source_file_id=doc.source_file_id,
        source_version=doc.source_version,
        original_sha256=doc.original_sha256,
        start=start,
        end=end,
        text=answer.quote,
        anchor_method="exact_text_match",
        locations=[
            location
            for location in doc.locations
            if location.get("start", 0) < end and location.get("end", 0) > start
        ],
    )
    return answer.model_copy(update={"evidence": [span]})
