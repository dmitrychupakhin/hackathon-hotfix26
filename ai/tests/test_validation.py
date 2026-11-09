import pytest

from app.domain import Candidate, DomainError, Package, TextDocument
from app.services.documents import decode_text, document_from_text, with_documents
from app.services.tools import ToolBox, calculate
from app.services.validation import validate


def test_list_numbering_is_not_a_claim_but_actual_numbers_stay_checked(settings):
    tools = toolbox(settings, ["Обеспечение: 18000 рублей."])
    row = candidate(tools)
    row.answer = "1) Обеспечение: 18000 рублей.\n2. Сумма: 18000 рублей."
    assert not validate(row, tools)[1]
    row.answer += "\n3. Срок: 999 дней."
    assert any(c.code == "numbers" for c in validate(row, tools)[1])


def toolbox(settings, texts):
    package = Package(code="P01", name="test")
    docs = [
        document_from_text(TextDocument(name=f"{i}.txt", text=text), settings)
        for i, text in enumerate(texts)
    ]
    return ToolBox(with_documents(package, docs, settings))


def candidate(tools, **kwargs):
    return Candidate(
        id="P01-01",
        status="ответ",
        answer="18000",
        evidence=[{"span_id": next(iter(tools.spans))}],
        **kwargs,
    )


def test_known_source_names_are_not_numeric_claims_and_unknown_values_stay_checked(settings):
    package = Package(code="P06", name="references")
    docs = [
        document_from_text(TextDocument(name=name, text=text), settings)
        for name, text in [
            ("03_object.txt", "Гарантия: 24 месяца."),
            ("04_contract.txt", "Гарантия: 36 месяцев."),
        ]
    ]
    tools = ToolBox(with_documents(package, docs, settings))
    row = Candidate(
        id="P06-09",
        status="расхождение",
        answer="24 месяца по 03_object.txt; 36 месяцев по 04_contract.txt.",
        evidence=[{"span_id": span_id} for span_id in tools.spans],
    )
    assert not validate(row, tools)[1]
    row.answer += " Ещё 72 месяца."
    assert any(c.code == "numbers" for c in validate(row, tools)[1])
    row.answer = "24 месяца по 99_invented.txt; 36 месяцев по 04_contract.txt."
    assert any(c.code == "numbers" for c in validate(row, tools)[1])
    row.id, row.answer = "72", "72 месяца."
    assert any(c.code == "numbers" for c in validate(row, tools)[1])


def test_real_quote_and_positions(settings):
    tools = toolbox(settings, ["\n  Обеспечение: 18 000 рублей.\n"])
    answer, failures = validate(candidate(tools), tools)
    assert not failures
    span = answer.evidence[0]
    assert tools.package.documents[0].text[span.start : span.end] == answer.quote
    assert answer.file == "0.txt"


def test_fabricated_quote_rejected(settings):
    tools = toolbox(settings, ["Обеспечение: 18 000 рублей."])
    row = candidate(tools)
    row.evidence[0].quote = "Обеспечение: 99 000 рублей."
    _, failures = validate(row, tools)
    assert "quote" in {failure.code for failure in failures}


def test_real_quote_does_not_allow_wrong_number(settings):
    tools = toolbox(settings, ["Обеспечение: 18 000 рублей."])
    row = candidate(tools)
    row.answer = "90000 рублей"
    _, failures = validate(row, tools)
    assert any(f.code == "numbers" for f in failures)


def test_calculation_requires_both_operands(settings):
    tools = toolbox(settings, ["Цена: 1 800 000 рублей. Обеспечение: 5 процентов."])
    row = candidate(
        tools,
        calculation={"operation": "percentage", "operands": ["1800000", "5"], "result": "90000"},
    )
    row.answer = "90000 рублей"
    assert not validate(row, tools)[1]
    row.calculation.operands = ["2000000", "4.5"]
    assert any(f.code == "calculation" for f in validate(row, tools)[1])


@pytest.mark.parametrize(
    "operation, operands",
    [
        ("shell", ["1", "2"]),
        ("divide", ["1", "0"]),
        ("add", ["NaN", "1"]),
        ("multiply", ["1e100", "1"]),
    ],
)
def test_calculator_rejects_unbounded_or_invalid_operations(operation, operands):
    with pytest.raises(DomainError):
        calculate(operation, operands)


def test_conflict_requires_two_real_spans(settings):
    tools = toolbox(settings, ["Работы: 60 календарных дней.", "Работы: 75 календарных дней."])
    row = Candidate(
        id="P01-01",
        status="расхождение",
        answer="60 и 75 дней",
        evidence=[{"span_id": next(iter(tools.spans))}],
    )
    assert any(f.code == "conflict_evidence" for f in validate(row, tools)[1])
    row = Candidate(
        id="P01-01",
        status="расхождение",
        answer="60 и 75 дней",
        evidence=[{"span_id": span_id} for span_id in tools.spans],
    )
    assert not validate(row, tools)[1]


def test_absence_requires_complete_reading(settings):
    tools = toolbox(settings, ["Общие условия закупки."])
    row = Candidate(id="P01-01", status="нет в документах")
    assert any(f.code == "coverage" for f in validate(row, tools)[1])
    tools.full_context()
    assert not validate(row, tools)[1]
    incomplete = toolbox(settings, ["Общие условия закупки.", ""])
    incomplete.full_context()
    assert any(f.code == "coverage" for f in validate(row, incomplete)[1])


def test_tools_cannot_read_outside_package(settings):
    tools = toolbox(settings, ["Документ с данными."])
    with pytest.raises(DomainError):
        tools.read_document("../../.env")
    with pytest.raises(DomainError):
        tools.read_evidence("foreign-span")
    with pytest.raises(DomainError):
        tools.call("execute_shell", {"command": "echo ignored"})


def test_cp1251_and_binary():
    text, encoding = decode_text("Обеспечение не требуется".encode("cp1251"))
    assert text == "Обеспечение не требуется" and encoding == "cp1251"
    with pytest.raises(DomainError):
        decode_text(b"binary\0data")
