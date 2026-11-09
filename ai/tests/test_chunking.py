import hashlib

import pytest

from app.domain import Document, Package
from app.services.chunking import split_text, token_estimate
from app.services.documents import spans_for


def test_chunks_bound_budget_overlap_and_preserve_original_tail():
    text = (
        "Заголовок.\n\n"
        + "Условие закупки исполнить полностью. " * 400
        + "Последнее изменение: 10%."
    )
    chunks = split_text(text, target_tokens=200, overlap_tokens=20)
    assert len(chunks) > 2
    assert chunks[0].start == 0 and chunks[-1].end == len(text)
    assert all(c.estimated_tokens <= 200 and text[c.start : c.end] == c.text for c in chunks)
    assert all(a.start < b.start < a.end for a, b in zip(chunks, chunks[1:]))
    covered = set(i for c in chunks for i in range(c.start, c.end))
    assert all(i in covered or char.isspace() for i, char in enumerate(text))


def test_sentence_overlap_preserves_clause_at_boundary():
    text = "Общие условия. " * 30 + "Обеспечение: 5 процентов. " + "Срок: 60 дней. " * 30
    chunks = split_text(text, target_tokens=100, overlap_tokens=20)
    assert any("Обеспечение: 5 процентов." in c.text for c in chunks)
    assert all(c.text in text for c in chunks)


def test_table_rows_stay_whole_when_they_fit():
    header = "Поле | Значение | Единица\n"
    row = "Обеспечение | 18000 | рубли\n"
    text = header + row * 20
    chunks = split_text(text, target_tokens=100, overlap_tokens=0)
    assert all(c.start == 0 or text[c.start - 1] == "\n" for c in chunks)
    assert all(c.end == len(text.rstrip()) or text[c.end] == "\n" for c in chunks)


def test_no_boundary_hard_split_progresses_and_is_bounded():
    text = "а" * 10000
    chunks = split_text(text, target_tokens=100, overlap_tokens=10)
    assert chunks[-1].end == len(text)
    assert all(c.estimated_tokens <= 100 for c in chunks)
    assert all(a.end - b.start == 20 for a, b in zip(chunks, chunks[1:]))
    assert token_estimate("абв") == 2


@pytest.mark.parametrize("target,overlap", [(10, 1), (100, 100), (100, -1), (100.0, 1)])
def test_invalid_chunk_configuration(target, overlap):
    with pytest.raises(ValueError):
        split_text("text", target_tokens=target, overlap_tokens=overlap)


def test_ids_are_stable_source_coordinates_and_change_on_revision():
    text = "Срок исполнения: 60 дней. " * 300
    doc = Document(
        id="doc", name="notice.txt", text=text, sha256=hashlib.sha256(text.encode()).hexdigest()
    )
    package = Package(code="P", name="P", documents=[doc])
    first = spans_for(package, target_tokens=100, overlap_tokens=10)
    assert first == spans_for(package, target_tokens=100, overlap_tokens=10)
    assert all(text[s.start : s.end] == s.text for s in first.values())
    package.documents[0].sha256 = "new-version"
    assert not set(first) & set(spans_for(package, target_tokens=100, overlap_tokens=10))
    assert spans_for(package, target_chars=1600)
