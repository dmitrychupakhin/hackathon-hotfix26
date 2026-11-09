import asyncio
import hashlib
import json

import pytest
from conftest import FakeModel, reply

from app.domain import Answer, Candidate, Document, Package, Question, RunCreate
from app.services.documents import document_text_complete
from app.services.harness import Harness
from app.services.tools import ToolBox
from app.services.validation import validate


@pytest.mark.parametrize(
    "warning,partial,text,expected",
    [
        ("docx_page_layout_unavailable", False, "Срок работ: 30 дней.", True),
        (None, False, "Срок работ: 30 дней.", True),
        ("docx_page_layout_unavailable", True, "Срок работ: 30 дней.", False),
        (
            "embedded_images_charts_or_objects_not_extracted;docx_page_layout_unavailable",
            True,
            "Срок работ: 30 дней.",
            False,
        ),
        (
            "embedded_images_charts_or_objects_not_extracted;docx_page_layout_unavailable",
            False,
            "Срок работ: 30 дней.",
            False,
        ),
        (
            "docx_page_layout_unavailable;unknown_parser_warning",
            False,
            "Срок работ: 30 дней.",
            False,
        ),
        ("page_2_has_no_text_layer_ocr_required", False, "Срок работ: 30 дней.", False),
        ("docx_page_layout_unavailable", False, "", False),
    ],
)
def test_content_coverage_and_critic_use_same_warning_classification(
    settings, warning, partial, text, expected
):
    doc = Document(
        id="d-1",
        name="contract.docx",
        text=text,
        sha256=hashlib.sha256(text.encode()).hexdigest(),
        warning=warning,
        partial=partial,
    )
    package = Package(id="p-1", code="P", name="Contract", documents=[doc])
    tools = ToolBox(package)
    assert not tools.complete_coverage  # actual reading is still required
    tools.full_context()
    assert document_text_complete(doc) is expected
    assert tools.complete_coverage is expected
    question = Question(id="q-1", package_id=package.id, text="Есть ли неустойка?")
    absence = Candidate(id=question.id, status="нет в документах")
    _, failures = validate(absence, tools)
    assert ("coverage" not in {item.code for item in failures}) is expected

    async def emit(*args):
        pass

    model = FakeModel(
        lambda kwargs, _: reply(
            {"reviews": [{"id": question.id, "verdict": "supported", "reason": "test"}]}
        )
    )
    harness = Harness(model, settings, RunCreate(questions=[question]), emit, asyncio.Event())
    answer = Answer(id=question.id, status="ответ", answer="30 дней")
    asyncio.run(harness._review(package, tools, [], {question.id: answer}, [question]))
    body = json.loads(model.calls[0]["messages"][1]["content"])
    assert body["documents_complete"] is expected
