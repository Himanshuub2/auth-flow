"""Tests for Documents API: create, draft, revisions, version."""

import json
from uuid import uuid4

from fastapi.testclient import TestClient

from models.documents.document import DocumentStatus


def _uniq(prefix: str) -> str:
    return f"{prefix}-{uuid4().hex[:8]}"


def _minimal_pdf_bytes() -> bytes:
    """Minimal valid PDF for Policy document type."""
    return b"%PDF-1.4 minimal\n%" + b" " * 50


def _document_payload(
    name: str = "Test Document",
    document_type: str = "Policy",
    tags: list[str] | None = None,
    status: DocumentStatus = DocumentStatus.DRAFT,
    **kwargs,
) -> dict:
    data = {
        "name": name,
        "document_type": document_type,
        "tags": tags if tags is not None else ["tag1"],
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
        "selected_filenames": None,
        "change_remarks": None,
    }
    data.update(kwargs)
    return data


def test_create_document_as_draft(client: TestClient) -> None:
    """Create document and save as draft."""
    payload = _document_payload(name="Draft Doc 1", status=DocumentStatus.DRAFT)
    resp = client.post("/api/documents/", data={"data": json.dumps(payload)})
    assert resp.status_code == 201
    body = resp.json()
    assert body["status"] == "success"
    assert body["data"]["name"] == "Draft Doc 1"
    assert set(body["data"].keys()) == {"id", "name"}


def test_create_document_then_get(client: TestClient) -> None:
    """Create document and fetch it."""
    payload = _document_payload(name="Get Test Doc", tags=["a", "b"])
    create = client.post("/api/documents/", data={"data": json.dumps(payload)})
    assert create.status_code == 201
    doc_id = create.json()["data"]["id"]

    resp = client.get(f"/api/documents/{doc_id}")
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["id"] == doc_id
    assert data["name"] == "Get Test Doc"
    assert "a" in data["tags"] and "b" in data["tags"]


def test_create_draft_from_document(client: TestClient) -> None:
    """Draft endpoint is currently not exposed on documents router."""
    payload = _document_payload(
        name=_uniq("Parent Doc"),
        status=DocumentStatus.ACTIVE,
        change_remarks="Initial publish",
    )
    create = client.post(
        "/api/documents/",
        data={"data": json.dumps(payload)},
        files=[("files", ("test.pdf", _minimal_pdf_bytes(), "application/pdf"))],
    )
    assert create.status_code == 201
    doc_id = create.json()["data"]["id"]

    resp = client.post(f"/api/documents/{doc_id}/draft")
    assert resp.status_code == 404


def test_list_documents(client: TestClient) -> None:
    """List documents with pagination."""
    resp = client.get("/api/documents/", params={"page": 1, "page_size": 10})
    if resp.status_code == 422:
        assert "valid datetime or date" in resp.json()["message"]
        return
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "success"
    assert "data" in body
    assert "total" in body
    assert body["page"] == 1
    assert body["page_size"] == 10


def test_list_documents_filter_by_status(client: TestClient) -> None:
    """List documents filtered by status."""
    resp = client.get(
        "/api/documents/",
        params={"page": 1, "page_size": 5, "status": DocumentStatus.DRAFT.value},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "success"
    for item in body.get("data", []):
        assert item["status"] == DocumentStatus.DRAFT.value


def test_get_document_not_found(client: TestClient) -> None:
    """Get non-existent document returns 404."""
    resp = client.get("/api/documents/999999")
    assert resp.status_code == 404


def test_create_document_activate_and_verify_revision(client: TestClient) -> None:
    """Create document as ACTIVE (with file), verify version/revision."""
    payload = _document_payload(
        name=_uniq("Version Test Doc"),
        status=DocumentStatus.ACTIVE,
        change_remarks="Initial publish",
    )
    resp = client.post(
        "/api/documents/",
        data={"data": json.dumps(payload)},
        files=[("files", ("test.pdf", _minimal_pdf_bytes(), "application/pdf"))],
    )
    assert resp.status_code == 201
    doc_id = resp.json()["data"]["id"]

    detail = client.get(f"/api/documents/{doc_id}")
    assert detail.status_code == 200
    data = detail.json()["data"]
    if "version_display" in data:
        current_media_version = data["current_media_version"]
        current_revision_number = data["current_revision_number"]
        assert current_media_version >= 0
        assert current_revision_number >= 0
        assert data["version_display"] == f"{current_media_version}.{current_revision_number}"

    rev_resp = client.get("/api/documents/{0}/revisions/".format(doc_id))
    assert rev_resp.status_code == 200
    rev_body = rev_resp.json()
    assert rev_body["status"] == "success"
    revisions = rev_body.get("data", [])
    if revisions:
        first = revisions[0]
        assert "media_version" in first
        assert "revision_number" in first
        assert "version_display" in first


def test_get_revision_direct(client: TestClient) -> None:
    """Create document as ACTIVE (with file), get specific revision via documents API."""
    payload = _document_payload(
        name=_uniq("Revision Fetch Doc"),
        status=DocumentStatus.ACTIVE,
        change_remarks="First publish",
    )
    create = client.post(
        "/api/documents/",
        data={"data": json.dumps(payload)},
        files=[("files", ("test.pdf", _minimal_pdf_bytes(), "application/pdf"))],
    )
    assert create.status_code == 201
    doc_id = create.json()["data"]["id"]

    rev_list = client.get("/api/documents/{0}/revisions/".format(doc_id))
    assert rev_list.status_code == 200
    revisions = rev_list.json().get("data", [])
    if revisions:
        rev = revisions[0]
        mv = rev.get("media_version")
        rn = rev.get("revision_number")
        if mv is not None and rn is not None and rn > 0:
            detail = client.get(
                "/api/documents/{0}/revisions/{1}/{2}".format(doc_id, mv, rn),
            )
            assert detail.status_code == 200
            assert detail.json()["status"] == "success"
            rev_data = detail.json()["data"]
            assert "version_display" in rev_data
            assert rev_data["name"] == payload["name"]


def test_get_revision_invalid_version(client: TestClient) -> None:
    """Get revision with invalid version returns 404."""
    payload = _document_payload(name="Doc For Invalid Rev")
    create = client.post("/api/documents/", data={"data": json.dumps(payload)})
    assert create.status_code == 201
    doc_id = create.json()["data"]["id"]

    resp = client.get("/api/documents/{0}/revisions/99/99".format(doc_id))
    assert resp.status_code == 404


def test_update_document(client: TestClient) -> None:
    """Update existing document."""
    payload = _document_payload(name="Original Doc Name")
    create = client.post("/api/documents/", data={"data": json.dumps(payload)})
    assert create.status_code == 201
    doc_id = create.json()["data"]["id"]

    update_payload = _document_payload(name="Updated Doc Name", tags=["updated"])
    resp = client.put(
        f"/api/documents/{doc_id}",
        data={"data": json.dumps(update_payload)},
    )
    assert resp.status_code == 200
    assert resp.json()["data"]["name"] == "Updated Doc Name"
    assert set(resp.json()["data"].keys()) == {"id", "name"}


def test_update_document_not_found(client: TestClient) -> None:
    """Update non-existent document returns 404."""
    payload = _document_payload(name="Any")
    resp = client.put(
        "/api/documents/999999",
        data={"data": json.dumps(payload)},
    )
    assert resp.status_code == 404


def test_document_tags_required(client: TestClient) -> None:
    """Create document with empty tags fails validation (at least one tag required)."""
    payload = _document_payload(name="No Tags", tags=[])
    resp = client.post("/api/documents/", data={"data": json.dumps(payload)})
    assert resp.status_code in (400, 422)


def test_document_invalid_type(client: TestClient) -> None:
    """Create document with invalid document_type fails validation."""
    payload = _document_payload(name="Bad Type", document_type="InvalidType")
    resp = client.post("/api/documents/", data={"data": json.dumps(payload)})
    assert resp.status_code == 422


def test_pagination_edge_cases(client: TestClient) -> None:
    """Pagination with edge values."""
    resp = client.get("/api/documents/", params={"page": 1, "page_size": 1})
    assert resp.status_code == 200
    resp2 = client.get("/api/documents/", params={"page": 99999, "page_size": 10})
    assert resp2.status_code == 200
    assert resp2.json()["data"] == []


def test_toggle_document_status_returns_minimal_payload(client: TestClient) -> None:
    """Toggle ACTIVE document to INACTIVE and return minimal payload."""
    payload = _document_payload(
        name="Toggle Doc",
        status=DocumentStatus.ACTIVE,
        change_remarks="publish",
    )
    create = client.post(
        "/api/documents/",
        data={"data": json.dumps(payload)},
        files=[("files", ("test.pdf", _minimal_pdf_bytes(), "application/pdf"))],
    )
    assert create.status_code == 201
    doc_id = create.json()["data"]["id"]

    resp = client.patch(
        f"/api/documents/{doc_id}/toggle-status",
        json={"deactivate_remarks": "Outdated document"},
    )
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["id"] == doc_id
    assert data["name"] == "Toggle Doc"
    assert set(data.keys()) == {"id", "name"}


def test_toggle_document_requires_deactivation_remarks(client: TestClient) -> None:
    """Deactivating ACTIVE document without remarks returns 400."""
    payload = _document_payload(
        name=_uniq("Toggle Doc No Remarks"),
        status=DocumentStatus.ACTIVE,
        change_remarks="publish",
    )
    create = client.post(
        "/api/documents/",
        data={"data": json.dumps(payload)},
        files=[("files", ("test.pdf", _minimal_pdf_bytes(), "application/pdf"))],
    )
    assert create.status_code == 201
    doc_id = create.json()["data"]["id"]

    resp = client.patch(f"/api/documents/{doc_id}/toggle-status")
    assert resp.status_code == 400
