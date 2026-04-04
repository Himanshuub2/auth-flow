"""Tests for Combined Items API (events + documents): list, detail, revisions."""

import json

from fastapi.testclient import TestClient

from constants import DOCUMENT, EVENT
from models.documents.document import DocumentStatus
from models.events.event import EventStatus


def test_list_combined_all(client: TestClient) -> None:
    """List combined items (events + documents) without filter."""
    resp = client.post("/api/items/", json={"page": 1, "page_size": 20})
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "success"
    assert "data" in body
    assert "total" in body
    for item in body.get("data", []):
        assert "document_type" in item
        assert "name" in item
        assert "version_display" in item
        assert "status" in item


def test_list_combined_filter_event(client: TestClient) -> None:
    """List combined items filtered by item_type=event."""
    resp = client.post(
        "/api/items/",
        json={"page": 1, "page_size": 10, "item_type": EVENT},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "success"
    for item in body.get("data", []):
        assert item["document_type"] == EVENT


def test_list_combined_filter_document(client: TestClient) -> None:
    """List combined items filtered by item_type=document."""
    resp = client.post(
        "/api/items/",
        json={"page": 1, "page_size": 10, "item_type": DOCUMENT},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "success"
    for item in body.get("data", []):
        assert item["document_type"] != EVENT  # documents have type label (Policy, EWS, etc.)


def test_get_item_detail_event(client: TestClient) -> None:
    """Create event, fetch via combined detail API."""
    payload = {
        "event_name": "Combined Test Event",
        "sub_event_name": None,
        "event_dates": None,
        "description": None,
        "tags": [],
        "applicability_type": "ALL",
        "applicability_refs": None,
        "status": EventStatus.DRAFT.value,
        "file_metadata": None,
        "change_remarks": None,
    }
    create = client.post("/api/events/", json=payload)
    assert create.status_code == 201
    event_id = create.json()["data"]["id"]

    resp = client.get(
        "/api/items/{0}".format(event_id),
        params={"item_type": EVENT},
    )
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["event_name"] == "Combined Test Event"


def test_get_item_detail_document(client: TestClient) -> None:
    """Create document, fetch via combined detail API."""
    payload = {
        "name": "Combined Test Doc",
        "document_type": "Policy",
        "tags": ["t1"],
        "summary": None,
        "legislation_id": None,
        "sub_legislation_id": None,
        "version": 1,
        "next_review_date": None,
        "download_allowed": True,
        "linked_document_ids": None,
        "applicability_type": "ALL",
        "applicability_refs": None,
        "status": DocumentStatus.DRAFT.value,
        "selected_filenames": None,
        "change_remarks": None,
    }
    create = client.post("/api/documents/", data={"data": json.dumps(payload)})
    assert create.status_code == 201
    doc_id = create.json()["data"]["id"]

    resp = client.get(
        "/api/items/{0}".format(doc_id),
        params={"item_type": DOCUMENT},
    )
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["name"] == "Combined Test Doc"


def test_get_item_detail_invalid_type(client: TestClient) -> None:
    """Get item detail with invalid item_type returns 400."""
    resp = client.get(
        "/api/items/1",
        params={"item_type": "invalid"},
    )
    assert resp.status_code == 400


def test_get_item_detail_not_found(client: TestClient) -> None:
    """Get item detail for non-existent item returns 404."""
    resp = client.get(
        "/api/items/999999",
        params={"item_type": EVENT},
    )
    assert resp.status_code == 404


def test_item_revisions_event(client: TestClient) -> None:
    """Create event, list revisions via combined API."""
    payload = {
        "event_name": "Rev List Event",
        "sub_event_name": None,
        "event_dates": None,
        "description": None,
        "tags": [],
        "applicability_type": "ALL",
        "applicability_refs": None,
        "status": EventStatus.DRAFT.value,
        "file_metadata": None,
        "change_remarks": None,
    }
    create = client.post("/api/events/", json=payload)
    assert create.status_code == 201
    event_id = create.json()["data"]["id"]

    resp = client.get(
        "/api/items/{0}/revisions".format(event_id),
        params={"item_type": EVENT},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "success"
    assert isinstance(body["data"], list)


def test_item_revisions_document(client: TestClient) -> None:
    """Create document, list revisions via combined API."""
    payload = {
        "name": "Rev List Doc",
        "document_type": "Policy",
        "tags": ["t1"],
        "summary": None,
        "legislation_id": None,
        "sub_legislation_id": None,
        "version": 1,
        "next_review_date": None,
        "download_allowed": True,
        "linked_document_ids": None,
        "applicability_type": "ALL",
        "applicability_refs": None,
        "status": DocumentStatus.DRAFT.value,
        "selected_filenames": None,
        "change_remarks": None,
    }
    create = client.post("/api/documents/", data={"data": json.dumps(payload)})
    assert create.status_code == 201
    doc_id = create.json()["data"]["id"]

    resp = client.get(
        "/api/items/{0}/revisions".format(doc_id),
        params={"item_type": DOCUMENT},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "success"
    assert isinstance(body["data"], list)


def test_item_revisions_invalid_type(client: TestClient) -> None:
    """List revisions with invalid item_type returns 400."""
    resp = client.get(
        "/api/items/1/revisions",
        params={"item_type": "bad"},
    )
    assert resp.status_code == 400


def test_list_combined_missing_item_type_ok(client: TestClient) -> None:
    """List without item_type returns both events and documents."""
    resp = client.post("/api/items/", json={"page": 1, "page_size": 5})
    assert resp.status_code == 200


def test_list_combined_page_size_too_large(client: TestClient) -> None:
    """Page size above allowed limit returns validation error."""
    resp = client.post("/api/items/", json={"page": 1, "page_size": 101})
    assert resp.status_code == 422


def test_list_combined_page_zero_invalid(client: TestClient) -> None:
    """Page less than 1 returns validation error."""
    resp = client.post("/api/items/", json={"page": 0, "page_size": 10})
    assert resp.status_code == 422
