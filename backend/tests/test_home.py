"""Tests for Home API endpoints."""

import json
from uuid import uuid4

from fastapi.testclient import TestClient

from models.documents.document import DocumentStatus


def _uniq(prefix: str) -> str:
    return f"{prefix}-{uuid4().hex[:8]}"


def _minimal_pdf_bytes() -> bytes:
    return b"%PDF-1.4 minimal\n%" + b" " * 50


def _minimal_png_bytes() -> bytes:
    # Minimal PNG signature + IHDR/IEND chunks.
    return (
        b"\x89PNG\r\n\x1a\n"
        b"\x00\x00\x00\rIHDR"
        b"\x00\x00\x00\x01\x00\x00\x00\x01\x08\x02\x00\x00\x00"
        b"\x90wS\xde"
        b"\x00\x00\x00\x00IEND\xaeB`\x82"
    )


def _document_payload(
    name: str,
    document_type: str,
    status: DocumentStatus = DocumentStatus.DRAFT,
    **kwargs,
) -> dict:
    data = {
        "name": name,
        "document_type": document_type,
        "tags": ["home"],
        "summary": None,
        "legislation_id": None,
        "sub_legislation_id": None,
        "version": 1,
        "next_review_date": None,
        "download_allowed": True,
        "linked_document_ids": None,
        "applicability_type": "ALL",
        "applicability_refs": None,
        "status": status.value,
        "selected_file_ids": None,
        "change_remarks": "initial publish" if status == DocumentStatus.ACTIVE else None,
    }
    data.update(kwargs)
    return data


def _create_active_document(
    client: TestClient,
    *,
    name: str,
    document_type: str,
    filename: str = "test.pdf",
    content_type: str = "application/pdf",
    file_bytes: bytes | None = None,
) -> int:
    payload = _document_payload(name=name, document_type=document_type, status=DocumentStatus.ACTIVE)
    resp = client.post(
        "/api/documents/",
        data={"data": json.dumps(payload)},
        files=[("files", (filename, file_bytes or _minimal_pdf_bytes(), content_type))],
    )
    assert resp.status_code == 201
    return resp.json()["data"]["id"]


def test_home_whats_new_excludes_faq_and_latest_news(client: TestClient) -> None:
    """What's new should not include FAQ or Latest News docs."""
    _create_active_document(client, name=_uniq("Policy-Home"), document_type="Policy")
    _create_active_document(
        client,
        name=_uniq("LatestNews-Home"),
        document_type="Latest News and Announcements",
    )

    resp = client.get("/api/home/whats-new", params={"page": 1, "page_size": 50})
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "success"

    items = body["data"]
    assert isinstance(items, list)
    assert all("id" in d and "name" in d and "document_type" in d for d in items)
    assert all(
        d["document_type"] not in {"FAQ", "Latest News and Announcements"}
        for d in items
    )


def test_home_document_gallery_returns_files_for_type(client: TestClient) -> None:
    """Gallery endpoint returns minimal document data and file URLs for a type."""
    created_name = _uniq("Gallery-LatestNews")
    _create_active_document(
        client,
        name=created_name,
        document_type="Latest News and Announcements",
        filename="home.png",
        content_type="image/png",
        file_bytes=_minimal_png_bytes(),
    )

    resp = client.get(
        "/api/home/document-gallery",
        params={"document_type": "Latest News and Announcements", "page": 1, "page_size": 10},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "success"
    rows = body["data"]
    assert isinstance(rows, list)

    assert any(r["name"] == created_name for r in rows)
    for row in rows:
        assert set(row.keys()) == {"id", "name", "document_type", "files"}
        assert row["document_type"] == "Latest News and Announcements"
        for f in row["files"]:
            assert {"id", "original_filename", "file_type", "file_url"} <= set(f.keys())
            assert f["file_type"] == "IMAGE"
            assert isinstance(f["file_url"], str) and f["file_url"]


def test_home_document_gallery_invalid_document_type(client: TestClient) -> None:
    resp = client.get("/api/home/document-gallery", params={"document_type": "NoSuchType"})
    assert resp.status_code == 400
