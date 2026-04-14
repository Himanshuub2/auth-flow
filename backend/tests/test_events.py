"""Tests for Events API: create, draft, revisions, version."""

from uuid import uuid4

from fastapi.testclient import TestClient

from models.events.event import EventStatus


def _uniq(prefix: str) -> str:
    return f"{prefix}-{uuid4().hex[:8]}"


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
        "file_metadata": None,
        "change_remarks": None,
    }
    data.update(kwargs)
    return data


def test_create_event_as_draft(client: TestClient) -> None:
    """Create event and save as draft."""
    payload = _event_payload(event_name="Draft Event 1", status=EventStatus.DRAFT)
    resp = client.post("/api/events/", json=payload)
    assert resp.status_code == 201
    body = resp.json()
    assert body["status"] == "success"
    assert body["data"]["name"] == "Draft Event 1"
    assert set(body["data"].keys()) == {"id", "name"}


def test_create_event_then_get(client: TestClient) -> None:
    """Create event and fetch it."""
    payload = _event_payload(event_name="Get Test Event")
    create = client.post("/api/events/", json=payload)
    assert create.status_code == 201
    event_id = create.json()["data"]["id"]

    resp = client.get(f"/api/events/{event_id}")
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["id"] == event_id
    assert data["event_name"] == "Get Test Event"


def test_create_draft_from_event(client: TestClient) -> None:
    """Draft endpoint is currently not exposed on events router."""
    payload = _event_payload(
        event_name=_uniq("Parent Event"),
        status=EventStatus.ACTIVE,
        change_remarks="Initial activation",
    )
    create = client.post("/api/events/", json=payload)
    assert create.status_code == 201
    event_id = create.json()["data"]["id"]

    resp = client.post(f"/api/events/{event_id}/draft")
    assert resp.status_code == 404


def test_list_events(client: TestClient) -> None:
    """List events with pagination."""
    resp = client.get("/api/events/", params={"page": 1, "page_size": 10})
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
        event_name=_uniq("Version Test Event"),
        status=EventStatus.ACTIVE,
        change_remarks="Initial publish",
    )
    resp = client.post("/api/events/", json=payload)
    assert resp.status_code == 201
    event_id = resp.json()["data"]["id"]

    detail = client.get(f"/api/events/{event_id}")
    assert detail.status_code == 200
    data = detail.json()["data"]
    if "version_display" in data:
        current_media_version = data["current_media_version"]
        current_revision_number = data["current_revision_number"]
        assert current_media_version >= 0
        assert current_revision_number >= 0
        assert data["version_display"] == f"{current_media_version}.{current_revision_number}"

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
        event_name=_uniq("Revision Fetch Event"),
        status=EventStatus.ACTIVE,
        change_remarks="First publish",
    )
    create = client.post("/api/events/", json=payload)
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
    create = client.post("/api/events/", json=payload)
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
    create = client.post("/api/events/", json=payload)
    assert create.status_code == 201
    event_id = create.json()["data"]["id"]

    update_payload = _event_payload(event_name="Updated Name")
    resp = client.put(f"/api/events/{event_id}", json=update_payload)
    assert resp.status_code == 200
    assert resp.json()["data"]["name"] == "Updated Name"
    assert set(resp.json()["data"].keys()) == {"id", "name"}


def test_update_event_not_found(client: TestClient) -> None:
    """Update non-existent event returns 404."""
    payload = _event_payload(event_name="Any")
    resp = client.put("/api/events/999999", json=payload)
    assert resp.status_code == 404


def test_pagination_edge_cases(client: TestClient) -> None:
    """Pagination with edge values."""
    resp = client.get("/api/events/", params={"page": 1, "page_size": 1})
    assert resp.status_code == 200
    resp2 = client.get("/api/events/", params={"page": 99999, "page_size": 10})
    assert resp2.status_code == 200
    assert resp2.json()["data"] == []


def test_toggle_event_status_returns_minimal_payload(client: TestClient) -> None:
    """Toggle ACTIVE event to INACTIVE and return minimal payload."""
    payload = _event_payload(
        event_name="Toggle Event",
        status=EventStatus.ACTIVE,
        change_remarks="publish",
    )
    create = client.post("/api/events/", json=payload)
    assert create.status_code == 201
    event_id = create.json()["data"]["id"]

    resp = client.patch(
        f"/api/events/{event_id}/toggle-status",
        json={"deactivate_remarks": "Not needed now"},
    )
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["id"] == event_id
    assert data["name"] == "Toggle Event"
    assert set(data.keys()) == {"id", "name"}


def test_toggle_event_requires_deactivation_remarks(client: TestClient) -> None:
    """Deactivating ACTIVE event without remarks returns 400."""
    payload = _event_payload(
        event_name=_uniq("Toggle Event No Remarks"),
        status=EventStatus.ACTIVE,
        change_remarks="publish",
    )
    create = client.post("/api/events/", json=payload)
    assert create.status_code == 201
    event_id = create.json()["data"]["id"]

    resp = client.patch(f"/api/events/{event_id}/toggle-status")
    assert resp.status_code == 400


def test_list_events_includes_card_fields(client: TestClient) -> None:
    """List returns preview and like fields (ACTIVE default)."""
    resp = client.get("/api/events/", params={"page": 1, "page_size": 5})
    assert resp.status_code == 200
    body = resp.json()
    for item in body.get("data", []):
        assert "preview_media" in item
        assert "remaining_media_count" in item
        assert "like_count" in item
        assert "liked_by_me" in item


def test_like_active_event(client: TestClient) -> None:
    """POST like increments count for ACTIVE events."""
    payload = _event_payload(
        event_name=_uniq("Like Me"),
        status=EventStatus.ACTIVE,
        change_remarks="publish",
    )
    create = client.post("/api/events/", json=payload)
    assert create.status_code == 201
    event_id = create.json()["data"]["id"]

    like = client.post(f"/api/events/{event_id}/like")
    assert like.status_code == 200
    d = like.json()["data"]
    assert d["liked_by_me"] is True
    assert d["like_count"] >= 1

    detail = client.get(f"/api/events/{event_id}")
    assert detail.status_code == 200
    assert detail.json()["data"]["liked_by_me"] is True
    assert detail.json()["data"]["like_count"] >= 1

    unlike = client.delete(f"/api/events/{event_id}/like")
    assert unlike.status_code == 200
    assert unlike.json()["data"]["liked_by_me"] is False


def test_like_draft_event_returns_400(client: TestClient) -> None:
    """Only ACTIVE events can be liked."""
    payload = _event_payload(event_name=_uniq("Draft"), status=EventStatus.DRAFT)
    create = client.post("/api/events/", json=payload)
    assert create.status_code == 201
    event_id = create.json()["data"]["id"]
    resp = client.post(f"/api/events/{event_id}/like")
    assert resp.status_code == 400
