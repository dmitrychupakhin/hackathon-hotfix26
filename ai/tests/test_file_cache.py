import asyncio
import hashlib
import json
from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from app.domain import DomainError
from app.infrastructure.files import ExtractionLimits, ParsedFile, SourceLocation
from app.infrastructure.files.cache_models import SourceFile
from app.services.file_cache import FileCache


class Parser:
    def __init__(self, partial=False, delay=0):
        self.limits = ExtractionLimits()
        self.calls = 0
        self.partial = partial
        self.delay = delay

    async def parse(self, raw, name, media_type, file_id):
        self.calls += 1
        if self.delay:
            await asyncio.sleep(self.delay)
        return ParsedFile(
            name=name,
            text=raw.decode("utf-8"),
            file_id=file_id,
            media_type=media_type,
            original_sha256=hashlib.sha256(raw).hexdigest(),
            extractor="fake-text",
            partial=self.partial,
            warnings=["page_2_unreadable"] if self.partial else [],
            locations=[SourceLocation(start=0, end=len(raw.decode()), page=1)],
        )


@pytest.fixture
def setup(tmp_path):
    source_root = tmp_path / "sources"
    source_root.mkdir()
    original = source_root / "notice.txt"
    original.write_text("Обеспечение: 5%.\nСрок 60 дней.", encoding="utf-8")
    source = SourceFile(
        id="file-1",
        owner="user-1",
        version="v1",
        updated_at=datetime(2026, 11, 1, tzinfo=timezone.utc),
        filename="notice.txt",
        relative_path="notice.txt",
        sha256=hashlib.sha256(original.read_bytes()).hexdigest(),
        media_type="text/plain",
    )
    parser = Parser()
    cache = FileCache(source_root, tmp_path / "cache", parser)
    return source, original, parser, cache


async def test_cache_reuses_txt_and_keeps_original_untouched(setup):
    source, original, parser, cache = setup
    before = original.stat()
    first = await cache.prepare(source, source.owner)
    second = await cache.prepare(source, source.owner)
    assert not first.cache_hit and second.cache_hit
    assert parser.calls == 1
    assert first.parsed == second.parsed
    assert first.text_path.read_text() == original.read_text()
    assert (first.text_path.parent / "original.txt").read_bytes() == original.read_bytes()
    metadata = json.loads((first.text_path.parent / "metadata.json").read_text())
    assert metadata["source"]["sha256"] == source.sha256
    assert metadata["generated_at"]
    assert original.stat().st_mtime_ns == before.st_mtime_ns
    assert not (original.parent / "extracted.txt").exists()


async def test_owner_is_checked_before_read(setup):
    source, original, parser, cache = setup
    original.unlink()
    with pytest.raises(DomainError) as failure:
        await cache.prepare(source, "other-user")
    assert failure.value.code == "source_file_not_found"
    assert parser.calls == 0


async def test_actual_hash_checked_even_on_hit(setup):
    source, original, parser, cache = setup
    await cache.prepare(source, source.owner)
    original.write_text("Обеспечение уже 10%", encoding="utf-8")
    with pytest.raises(DomainError) as failure:
        await cache.prepare(source, source.owner)
    assert failure.value.code == "source_changed"
    assert parser.calls == 1


async def test_version_change_creates_immutable_artifact(setup):
    source, original, parser, cache = setup
    first = await cache.prepare(source, source.owner)
    original.write_text("Новое значение: 10%", encoding="utf-8")
    newer = source.model_copy(
        update={"version": "v2", "sha256": hashlib.sha256(original.read_bytes()).hexdigest()}
    )
    second = await cache.prepare(newer, source.owner)
    assert first.artifact_key != second.artifact_key
    assert "5%" in first.text_path.read_text()
    assert "10%" in second.text_path.read_text()
    assert parser.calls == 2


async def test_same_hash_new_version_still_separate(setup):
    source, original, parser, cache = setup
    first = await cache.prepare(source, source.owner)
    second = await cache.prepare(source.model_copy(update={"version": "v2"}), source.owner)
    assert first.artifact_key != second.artifact_key
    assert parser.calls == 2


async def test_dates_do_not_replace_hash_or_force_reparse(setup):
    source, original, parser, cache = setup
    first = await cache.prepare(source, source.owner)
    changed_date = source.model_copy(update={"updated_at": datetime.now(timezone.utc)})
    second = await cache.prepare(changed_date, source.owner)
    assert second.cache_hit and first.artifact_key == second.artifact_key
    assert parser.calls == 1


async def test_concurrent_calls_publish_once_across_cache_instances(setup):
    source, original, parser, cache = setup
    parser.delay = 0.05
    second_instance = FileCache(cache.source_root, cache.cache_root, parser)
    results = await asyncio.gather(
        *[([cache, second_instance][i % 2]).prepare(source, source.owner) for i in range(8)]
    )
    assert parser.calls == 1
    assert sum(not result.cache_hit for result in results) == 1
    assert len({result.artifact_key for result in results}) == 1
    assert not list(cache.cache_root.rglob(".extract-*"))


async def test_partial_results_and_locations_survive_cache_hit(setup):
    source, original, parser, cache = setup
    parser.partial = True
    first = await cache.prepare(source, source.owner)
    second = await cache.prepare(source, source.owner)
    assert first.parsed.partial and second.parsed.partial
    assert second.parsed.warnings == ["page_2_unreadable"]
    assert second.parsed.locations[0].page == 1


async def test_parser_settings_change_invalidates_cache(setup):
    source, original, parser, cache = setup
    first = await cache.prepare(source, source.owner)
    parser.limits = ExtractionLimits(ocr_enabled=True)
    second_cache = FileCache(cache.source_root, cache.cache_root, parser)
    second = await second_cache.prepare(source, source.owner)
    assert first.artifact_key != second.artifact_key
    assert not second.cache_hit


async def test_corrupt_txt_is_not_used(setup):
    source, original, parser, cache = setup
    first = await cache.prepare(source, source.owner)
    first.text_path.write_text("Поддельный ответ")
    with pytest.raises(DomainError) as failure:
        await cache.prepare(source, source.owner)
    assert failure.value.code == "file_cache_corrupt"
    assert parser.calls == 1


@pytest.mark.parametrize("component", ["file", "directory"])
async def test_source_symlink_escape_rejected(setup, tmp_path, component):
    source, original, parser, cache = setup
    external = tmp_path / "external"
    external.mkdir()
    (external / "secret.txt").write_bytes(original.read_bytes())
    if component == "file":
        original.unlink()
        original.symlink_to(external / "secret.txt")
    else:
        (cache.source_root / "link").symlink_to(external, target_is_directory=True)
        source = source.model_copy(update={"relative_path": "link/secret.txt"})
    with pytest.raises(DomainError) as failure:
        await cache.prepare(source, source.owner)
    assert failure.value.code == "unsafe_source_path"
    assert parser.calls == 0


async def test_cache_text_symlink_rejected(setup):
    source, original, parser, cache = setup
    first = await cache.prepare(source, source.owner)
    first.text_path.unlink()
    first.text_path.symlink_to(original)
    with pytest.raises(DomainError) as failure:
        await cache.prepare(source, source.owner)
    assert failure.value.code == "file_cache_corrupt"


async def test_cache_parent_symlink_rejected(setup, tmp_path):
    source, original, parser, cache = setup
    parts = cache._artifact_parts(source)
    outside = tmp_path / "outside"
    outside.mkdir()
    (cache.cache_root / parts[0]).symlink_to(outside)
    with pytest.raises(DomainError) as failure:
        await cache.prepare(source, source.owner)
    assert failure.value.code == "unsafe_cache_path"
    assert not list(outside.iterdir())


async def test_file_byte_limit_is_enforced_before_parse(setup):
    source, original, parser, cache = setup
    cache.max_bytes = 5
    with pytest.raises(DomainError) as failure:
        await cache.prepare(source, source.owner)
    assert failure.value.code == "file_too_large"
    assert parser.calls == 0


async def test_missing_source_has_explicit_error(setup):
    source, original, parser, cache = setup
    original.unlink()
    with pytest.raises(DomainError) as failure:
        await cache.prepare(source, source.owner)
    assert failure.value.code == "source_file_not_found"


async def test_metadata_provenance_corruption_rejected(setup):
    source, original, parser, cache = setup
    first = await cache.prepare(source, source.owner)
    path = first.text_path.parent / "metadata.json"
    data = json.loads(path.read_text())
    data["source"]["owner"] = "other-user"
    path.write_text(json.dumps(data))
    with pytest.raises(DomainError) as failure:
        await cache.prepare(source, source.owner)
    assert failure.value.code == "file_cache_corrupt"


async def test_direct_upload_publishes_original_and_reuses_same_id(setup):
    source, original, parser, cache = setup
    first = await cache.prepare_bytes(
        original.read_bytes(), "notice.txt", source.owner, "text/plain", file_id="upload-1"
    )
    second = await cache.prepare_bytes(
        original.read_bytes(), "notice.txt", source.owner, "text/plain", file_id="upload-1"
    )
    assert not first.cache_hit and second.cache_hit
    assert parser.calls == 1
    assert first.parsed.file_id == "upload-1"
    assert first.text_path.read_text() == original.read_text()


async def test_upload_limit_rejects_before_parsing(setup):
    source, original, parser, cache = setup
    cache.max_bytes = 1
    with pytest.raises(DomainError) as failure:
        await cache.prepare_bytes(b"ab", "a.txt", source.owner)
    assert failure.value.code == "file_too_large"
    assert parser.calls == 0


@pytest.mark.parametrize(
    "path", ["/etc/passwd", "../secret", "nested/../secret", "a//b", "a/./b", "a\\b"]
)
def test_metadata_rejects_unsafe_relative_paths(setup, path):
    source, *_ = setup
    values = source.model_dump()
    values["relative_path"] = path
    with pytest.raises(ValidationError):
        SourceFile.model_validate(values)


def test_metadata_requires_aware_time_and_valid_hash(setup):
    source, *_ = setup
    for update in ({"updated_at": "2026-11-07T10:00:00"}, {"sha256": "bad"}):
        with pytest.raises(ValidationError):
            SourceFile.model_validate({**source.model_dump(), **update})


async def test_missing_txt_is_rebuilt_atomically(setup):
    source, original, parser, cache = setup
    first = await cache.prepare(source, source.owner)
    first.text_path.unlink()
    second = await cache.prepare(source, source.owner)
    assert not second.cache_hit
    assert parser.calls == 2
    assert second.text_path.read_text() == original.read_text()
    assert len(list(second.text_path.parent.parent.glob(".incomplete-*"))) == 1


async def test_lock_symlink_does_not_touch_external_file(setup, tmp_path):
    source, original, parser, cache = setup
    parts = cache._artifact_parts(source)
    parent = cache._safe_cache_parent(parts[:-1])
    secret = tmp_path / "secret"
    secret.write_text("private")
    (parent / (parts[-1] + ".lock")).symlink_to(secret)
    with pytest.raises(DomainError) as failure:
        await cache.prepare(source, source.owner)
    assert failure.value.code == "unsafe_cache_path"
    assert secret.read_text() == "private"


async def test_real_text_parser_extracts_and_cache_does_not_reparse(setup):
    import httpx

    from app.infrastructure.files import FileIngestor

    source, original, parser, cache = setup
    async with httpx.AsyncClient() as client:
        ingestor = FileIngestor(client)
        real_cache = FileCache(cache.source_root, cache.cache_root, ingestor)
        first = await real_cache.prepare(source, source.owner)
        second = await real_cache.prepare(source, source.owner)
    assert not first.cache_hit and second.cache_hit
    assert first.parsed.text == original.read_text()
    assert first.parsed.extractor != "fake-text"


@pytest.mark.parametrize("name", ["../x.pdf", "nested/x.pdf", "x\\y.pdf", "", "x" * 201])
async def test_upload_invalid_filename_returns_domain_error(setup, name):
    source, original, parser, cache = setup
    with pytest.raises(DomainError) as failure:
        await cache.prepare_bytes(b"data", name, source.owner)
    assert failure.value.code == "invalid_filename"
    assert failure.value.status == 422
    assert name not in failure.value.message or name == ""
    assert parser.calls == 0
    assert not list(cache.cache_root.iterdir())


async def test_upload_invalid_other_metadata_returns_domain_error(setup):
    source, original, parser, cache = setup
    with pytest.raises(DomainError) as failure:
        await cache.prepare_bytes(b"data", "x.txt", source.owner, file_id="../not-an-id")
    assert failure.value.code == "invalid_source_metadata"
    assert failure.value.status == 422
    assert parser.calls == 0
