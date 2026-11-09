import hashlib
from pathlib import Path
from uuid import uuid4

import pytest
from conftest import wait_run

from app.domain import now


def source(
    client, settings, text="🙂 Условие договора: обеспечение 18000 рублей.", name="notice.txt"
):
    file_id = str(uuid4())
    root = Path(settings.source_root)
    root.mkdir(exist_ok=True)
    path = root / file_id
    path.write_text(text)
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    record = dict(
        id=file_id,
        owner="user-1",
        version=digest,
        updated_at=now(),
        filename=name,
        relative_path=file_id,
        sha256=digest,
        media_type="text/plain",
    )
    client.portal.call(client.app.state.store.create, "source_file", record, "user-1")
    return record, text


def test_preview_canonical_text_owner_scope_and_stale_hash(client, headers, settings):
    record, text = source(client, settings)
    path = f"/api/v1/files/{record['id']}/preview"
    response = client.get(path, headers=headers)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["text"] == text and body["text_sha256"] == record["sha256"]
    assert body["offset_unit"] == "unicode_code_points"
    assert body["name"] == "notice.txt" and body["format"] == "txt"
    assert "artifact_key" not in body and "relative_path" not in body
    assert client.get(path, headers={**headers, "X-User-ID": "other"}).status_code == 404
    assert client.get(path).status_code == 401
    assert client.get(path, headers=headers, params={"text_sha256": "0" * 64}).status_code == 409
    assert client.get(path, headers=headers, params={"version": "old"}).status_code == 409
    assert (
        client.get(
            path,
            headers=headers,
            params={"text_sha256": record["sha256"], "version": record["sha256"]},
        ).status_code
        == 200
    )


@pytest.mark.parametrize(
    "name,format_", [("note.md", "md"), ("note.csv", "txt"), ("note.json", "txt")]
)
def test_preview_text_formats(client, headers, settings, name, format_):
    record, _ = source(
        client,
        settings,
        name=name,
        text='{"notice": "Условие договора"}' if name.endswith(".json") else "Условие договора",
    )
    response = client.get(f"/api/v1/files/{record['id']}/preview", headers=headers)
    assert response.status_code == 200, response.text
    assert response.json()["format"] == format_


def test_chat_answer_evidence_keeps_trusted_file_provenance(client, headers, settings):
    record, text = source(client, settings)
    message_id = str(uuid4())
    response = client.post(
        "/api/v1/chat-runs",
        headers=headers,
        json={
            "chat_id": str(uuid4()),
            "message_id": message_id,
            "question": "Какой размер обеспечения?",
            "model": "test-model",
            "file_ids": [record["id"]],
        },
    )
    assert response.status_code == 202, response.text
    run = wait_run(client, headers, response.json()["id"])
    assert run["status"] == "completed", run
    span = run["result"]["answers"][0]["evidence"][0]
    assert span["source_file_id"] == record["id"]
    assert span["source_version"] == record["sha256"]
    assert span["original_sha256"] == record["sha256"]
    assert span["file"] == "notice.txt"
    assert text[span["start"] : span["end"]] == span["text"]


@pytest.mark.parametrize("format_", ["pdf", "docx"])
def test_preview_original_formats_and_page_coordinates(client, headers, settings, format_):
    from test_file_ingestion import archive, make_pdf

    raw = (
        make_pdf()
        if format_ == "pdf"
        else archive(
            {
                "word/document.xml": '<w:document xmlns:w="urn:w"><w:body><w:p><w:r><w:t>Price 18000</w:t></w:r></w:p></w:body></w:document>',
            }
        )
    )
    file_id = str(uuid4())
    root = Path(settings.source_root)
    root.mkdir(exist_ok=True)
    path = root / file_id
    path.write_bytes(raw)
    digest = hashlib.sha256(raw).hexdigest()
    record = dict(
        id=file_id,
        owner="user-1",
        version=digest,
        updated_at=now(),
        filename=f"notice.{format_}",
        relative_path=file_id,
        sha256=digest,
        media_type="application/octet-stream",
    )
    client.portal.call(client.app.state.store.create, "source_file", record, "user-1")
    response = client.get(f"/api/v1/files/{file_id}/preview", headers=headers)
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["format"] == format_ and "18000" in data["text"]
    assert data["text_sha256"] == hashlib.sha256(data["text"].encode()).hexdigest()
    if format_ == "pdf":
        assert data["locations"][0]["page"] == 1
        location = data["locations"][0]
        assert "18000" in data["text"][location["start"] : location["end"]]


def test_scanned_pdf_preview_keeps_original_without_claiming_extraction(client, headers, settings):
    from test_file_ingestion import make_pdf

    raw = make_pdf(text=False)
    file_id = str(uuid4())
    root = Path(settings.source_root)
    root.mkdir(exist_ok=True)
    (root / file_id).write_bytes(raw)
    digest = hashlib.sha256(raw).hexdigest()
    record = dict(
        id=file_id,
        owner="user-1",
        version=digest,
        updated_at=now(),
        filename="scan.pdf",
        relative_path=file_id,
        sha256=digest,
        media_type="application/pdf",
    )
    client.portal.call(client.app.state.store.create, "source_file", record, "user-1")
    path = f"/api/v1/files/{file_id}/preview"
    response = client.get(path, headers=headers)
    assert response.status_code == 200, response.text
    assert response.json()["format"] == "pdf" and response.json()["text"] == ""
    assert response.json()["partial"] and response.json()["warnings"] == ["ocr_required"]
    assert client.get(path, headers=headers, params={"text_sha256": "a" * 64}).status_code == 409
