import re
from decimal import Decimal

from app.domain import Answer, AnswerStatus, Candidate, Check, DomainError, Span
from app.services.tools import ToolBox, calculate, decimal_value


def numbers(text: str, *, ignore_list_markers=False) -> set[Decimal]:
    values = set()
    # A sign starts a number only when it is not a date/range separator.
    # Both ordinary hyphen-minus and the mathematical minus sign are supported.
    pattern = r"[+\-−]?[ \u00a0\u202f]*\d+(?:[ \u00a0\u202f]\d{3})*(?:[.,]\d+)?"
    # Numbered list markers are formatting, not factual quantities. Strip only
    # unambiguous line-leading markers; numbers within claims stay checked.
    if ignore_list_markers:
        text = re.sub(r"(?m)^\s*\d+[.)]\s+", "", text)
    for match in re.finditer(pattern, text):
        token = match.group().strip()
        if token.startswith(("-", "−")):
            previous = text[: match.start()].rstrip()
            if previous and previous[-1].isdigit():
                token = token[1:]
        try:
            values.add(decimal_value(token))
        except DomainError:
            continue
    return values


def unknown(question_id: str, reason: str, checks=None) -> Answer:
    return Answer(
        id=question_id,
        status=AnswerStatus.UNKNOWN,
        origin="fallback",
        reason=reason,
        checks=checks or [],
    )


def validate(candidate: Candidate, tools: ToolBox) -> tuple[Answer, list[Check]]:
    checks = []
    evidence = []
    docs = {d.id: d for d in tools.package.documents}
    for ref in candidate.evidence:
        span = tools.spans.get(ref.span_id)
        if not span:
            checks.append(
                Check(
                    code="unknown_evidence",
                    message=f"Unknown evidence span_id {ref.span_id!r}. Copy an exact ID from sources, read_document or search; do not invent IDs.",
                    passed=False,
                )
            )
            continue
        doc = docs[span.document_id]
        quote = ref.quote if ref.quote is not None else span.text
        position = span.text.find(quote) if quote else -1
        valid = len(quote.strip()) >= 8 and position >= 0 and doc.sha256 == span.source_hash
        checks.append(
            Check(
                code="quote",
                message=f"Quote in {span.file}: {'verified' if valid else 'not found as an exact original span'}",
                passed=valid,
            )
        )
        if valid:
            start = span.start + position
            evidence.append(
                Span(
                    **{
                        **span.model_dump(),
                        "start": start,
                        "end": start + len(quote),
                        "text": quote,
                        "locations": [
                            location
                            for location in span.locations
                            if location.get("start", 0) < start + len(quote)
                            and location.get("end", 0) > start
                        ],
                    }
                )
            )
    status = candidate.status
    if candidate.clarification_question is not None:
        checks.append(
            Check(
                code="clarification_status",
                message="A clarification question is allowed only with unknown status",
                passed=status == AnswerStatus.UNKNOWN
                and bool(candidate.clarification_question.strip()),
            )
        )
    if status in {AnswerStatus.ANSWER, AnswerStatus.CONFLICT}:
        checks.append(
            Check(
                code="answer_present",
                message="Answer and supporting evidence are required",
                passed=bool(candidate.answer.strip()) and bool(evidence),
            )
        )
        if status == AnswerStatus.CONFLICT:
            distinct = {(s.document_id, s.start, s.end) for s in evidence}
            checks.append(
                Check(
                    code="conflict_evidence",
                    message="A conflict requires at least two distinct source spans",
                    passed=len(distinct) >= 2,
                )
            )
        source_numbers = numbers("\n".join(s.text for s in evidence))
        allowed = set(source_numbers)
        if candidate.calculation:
            calculation = candidate.calculation
            try:
                expected = decimal_value(calculate(calculation.operation, calculation.operands))
                got = decimal_value(calculation.result)
                operands = {decimal_value(x) for x in calculation.operands}
                valid = expected == got and operands <= source_numbers
                if valid:
                    allowed.add(got)
            except DomainError:
                valid = False
            checks.append(
                Check(
                    code="calculation",
                    message="Calculation result and every operand must match source evidence",
                    passed=valid,
                )
            )
        # Trusted source filenames are references, not factual quantities:
        # "24 месяца по 03_object.txt" must not claim the number 3. Unknown
        # filenames and every numeric assertion outside known labels stay checked.
        claims = candidate.answer
        labels = {
            d.original_name or d.name
            for d in tools.package.documents
            if re.search(r"\.[A-Za-zА-Яа-я]{1,12}$", d.original_name or d.name)
        }
        if re.search(r"[A-Za-zА-Яа-я]", candidate.id):
            labels.add(candidate.id)
        for label in sorted(labels, key=len, reverse=True):
            claims = re.sub(r"(?<!\w)" + re.escape(label) + r"(?!\w)", "", claims)
        unsupported = numbers(claims, ignore_list_markers=True) - allowed
        checks.append(
            Check(
                code="numbers",
                message="All answer numbers must appear in evidence or a verified calculation"
                + (
                    f"; unsupported: {', '.join(str(x) for x in sorted(unsupported))}"
                    if unsupported
                    else ""
                ),
                passed=not unsupported,
            )
        )
    elif status == AnswerStatus.ABSENT:
        checks.append(
            Check(
                code="coverage",
                message="Absence requires all original documents to have been read successfully",
                passed=tools.complete_coverage,
            )
        )
        checks.append(
            Check(
                code="empty_absence",
                message="Absent answers must have empty answer/evidence",
                passed=not candidate.answer
                and not candidate.evidence
                and not candidate.calculation,
            )
        )
    else:
        checks.append(
            Check(
                code="empty_unknown",
                message="Unknown answers must have empty answer/evidence",
                passed=not candidate.answer
                and not candidate.evidence
                and not candidate.calculation,
            )
        )
    answer = Answer(
        id=candidate.id,
        status=status,
        answer=candidate.answer,
        evidence=evidence,
        calculation=candidate.calculation,
        clarification_question=candidate.clarification_question,
        quote=evidence[0].text if evidence else "",
        file=evidence[0].file if evidence else "",
        checks=checks,
    )
    return answer, [check for check in checks if not check.passed]
