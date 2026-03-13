"""Tests for Events API: create, draft, revisions, version."""

import json

from fastapi.testclient import TestClient

from models.events.event import EventStatus


def _event_payload(
    event_name: str = "Test Event",
    status: EventStatus = EventStatus.DRAFT,
    **kwargs,
) -> dict:
    data = {
        "event_name": event_name,
        "sub_event_name": None,
        "event_dates": None,
        "description": None,
        "tags": [],
        "applicability_type": "ALL",
        "applicability_refs": None,
        "status": status.value,
        "selected_filenames": None,
        "file_metadata": None,
        "change_remarks": None,
    }
    data.update(kwargs)
    return data


def test_create_event_as_draft(client: TestClient) -> None:
    """Create event and save as draft."""
    payload = _event_payload(event_name="Draft Event 1", status=EventStatus.DRAFT)
    resp = client.post("/api/events/", data={"data": json.dumps(payload)})
    assert resp.status_code == 201
    body = resp.json()
    assert body["status"] == "success"
    assert body["data"]["event_name"] == "Draft Event 1"
    assert body["data"]["status"] == EventStatus.DRAFT.value
    assert body["data"]["version_display"] == "0.0"
    assert "id" in body["data"]


def test_create_event_then_get(client: TestClient) -> None:
    """Create event and fetch it."""
    payload = _event_payload(event_name="Get Test Event")
    create = client.post("/api/events/", data={"data": json.dumps(payload)})
    assert create.status_code == 201
    event_id = create.json()["data"]["id"]

    resp = client.get(f"/api/events/{event_id}")
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["id"] == event_id
    assert data["event_name"] == "Get Test Event"


def test_create_draft_from_event(client: TestClient) -> None:
    """Create event as ACTIVE, then create draft from it (drafts only from active)."""
    payload = _event_payload(
        event_name="Parent Event",
        status=EventStatus.ACTIVE,
        change_remarks="Initial activation",
    )
    create = client.post("/api/events/", data={"data": json.dumps(payload)})
    assert create.status_code == 201
    event_id = create.json()["data"]["id"]

    resp = client.post(f"/api/events/{event_id}/draft")
    assert resp.status_code == 201
    body = resp.json()
    assert body["status"] == "success"
    draft = body["data"]
    assert draft["event_name"] == "Parent Event"
    assert "id" in draft


def test_list_events(client: TestClient) -> None:
    """List events with pagination."""
    resp = client.get("/api/events/", params={"page": 1, "page_size": 10})
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "success"
    assert "data" in body
    assert "total" in body
    assert body["page"] == 1
    assert body["page_size"] == 10


def test_list_events_filter_by_status(client: TestClient) -> None:
    """List events filtered by status."""
    resp = client.get(
        "/api/events/",
        params={"page": 1, "page_size": 5, "status": EventStatus.DRAFT.value},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "success"
    for item in body.get("data", []):
        assert item["status"] == EventStatus.DRAFT.value


def test_get_event_not_found(client: TestClient) -> None:
    """Get non-existent event returns 404."""
    resp = client.get("/api/events/999999")
    assert resp.status_code == 404


def test_create_event_activate_and_verify_revision(client: TestClient) -> None:
    """Create event, activate, verify version/revision."""
    payload = _event_payload(
        event_name="Version Test Event",
        status=EventStatus.ACTIVE,
        change_remarks="Initial publish",
    )
    resp = client.post("/api/events/", data={"data": json.dumps(payload)})
    assert resp.status_code == 201
    data = resp.json()["data"]
    event_id = data["id"]
    version_display = data["version_display"]
    current_media_version = data["current_media_version"]
    current_revision_number = data["current_revision_number"]

    assert current_media_version >= 0
    assert current_revision_number >= 0
    assert version_display == f"{current_media_version}.{current_revision_number}"

    rev_resp = client.get(
        "/api/items/{0}/revisions".format(event_id),
        params={"item_type": "event"},
    )
    assert rev_resp.status_code == 200
    rev_body = rev_resp.json()
    assert rev_body["status"] == "success"
    revisions = rev_body.get("data", [])
    if revisions:
        first = revisions[0]
        assert "media_version" in first
        assert "revision_number" in first
        assert "version_display" in first


def test_get_revision_via_combined(client: TestClient) -> None:
    """Create event, activate, get specific revision."""
    payload = _event_payload(
        event_name="Revision Fetch Event",
        status=EventStatus.ACTIVE,
        change_remarks="First publish",
    )
    create = client.post("/api/events/", data={"data": json.dumps(payload)})
    assert create.status_code == 201
    event_id = create.json()["data"]["id"]

    rev_list = client.get(
        "/api/items/{0}/revisions".format(event_id),
        params={"item_type": "event"},
    )
    assert rev_list.status_code == 200
    revisions = rev_list.json().get("data", [])
    if revisions:
        rev = revisions[0]
        mv = rev.get("media_version")
        rn = rev.get("revision_number")
        if mv is not None and rn is not None:
            detail = client.get(
                "/api/items/{0}/revisions/{1}/{2}".format(event_id, mv, rn),
                params={"item_type": "event"},
            )
            assert detail.status_code == 200
            assert detail.json()["status"] == "success"


def test_get_revision_invalid_version(client: TestClient) -> None:
    """Get revision with invalid version returns 404."""
    payload = _event_payload(event_name="Event For Invalid Rev")
    create = client.post("/api/events/", data={"data": json.dumps(payload)})
    assert create.status_code == 201
    event_id = create.json()["data"]["id"]

    resp = client.get(
        "/api/items/{0}/revisions/99/99".format(event_id),
        params={"item_type": "event"},
    )
    assert resp.status_code == 404


def test_update_event(client: TestClient) -> None:
    """Update existing event."""
    payload = _event_payload(event_name="Original Name")
    create = client.post("/api/events/", data={"data": json.dumps(payload)})
    assert create.status_code == 201
    event_id = create.json()["data"]["id"]

    update_payload = _event_payload(event_name="Updated Name")
    resp = client.put(
        f"/api/events/{event_id}",
        data={"data": json.dumps(update_payload)},
    )
    assert resp.status_code == 200
    assert resp.json()["data"]["event_name"] == "Updated Name"


def test_update_event_not_found(client: TestClient) -> None:
    """Update non-existent event returns 404."""
    payload = _event_payload(event_name="Any")
    resp = client.put(
        "/api/events/999999",
        data={"data": json.dumps(payload)},
    )
    assert resp.status_code == 404


def test_pagination_edge_cases(client: TestClient) -> None:
    """Pagination with edge values."""
    resp = client.get("/api/events/", params={"page": 1, "page_size": 1})
    assert resp.status_code == 200
    resp2 = client.get("/api/events/", params={"page": 99999, "page_size": 10})
    assert resp2.status_code == 200
    assert resp2.json()["data"] == []
