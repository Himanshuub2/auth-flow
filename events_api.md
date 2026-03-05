# Events API Reference

APIs for Events, Revisions, Media, and Reference data. All endpoints require authentication (exclude Auth/User APIs).

**Base URL:** `/api`  
**Auth:** Send `Authorization: Bearer <access_token>` header.

All non-auth APIs now return a **standard envelope**:

```json
{
  "message": "string",
  "status_code": 200,
  "status": "success | error",
  "data": {},              // actual payload (object, list, etc.)
  "pagination": null | {
    "total": 0,
    "page": 1,
    "page_size": 20
  }
}
```

Errors also use the same structure with `status = "error"` and an appropriate `status_code` and `message`.

---

## 1. Events

**Prefix:** `/api/events`

| Method | Path | Purpose |
|--------|------|--------|
| POST | `/api/events/` | Create event (draft or publish) |
| PUT | `/api/events/{event_id}` | Update event (draft or publish) |
| GET | `/api/events/` | List events (paginated, optional status filter) |
| GET | `/api/events/{event_id}` | Get single event (full details + files) |
| POST | `/api/events/{event_id}/draft` | Create draft from a published event |
| PATCH | `/api/events/{event_id}/toggle-status` | Toggle ACTIVE ↔ INACTIVE |
| DELETE | `/api/events/{event_id}` | Deactivate event (soft delete, sets INACTIVE) |

### Create event — `POST /api/events/`

**Request:** `multipart/form-data`

- `data` (required): JSON string, see **EventSavePayload** below.
- `files` (optional): list of file uploads (e.g. images/videos).

**Response:** `APIResponse` with `data: EventOut`

---

### Update event — `PUT /api/events/{event_id}`

**Request:** Same as create (`data` + optional `files`).

**Response:** `APIResponse` with `data: EventOut`

---

### List events — `GET /api/events/`

**Query params:**

| Param | Type | Default | Description |
|-------|------|---------|-------------|
| page | int | 1 | Page number |
| page_size | int | 20 | Items per page (max 100) |
| status | string | — | Optional: `DRAFT`, `PUBLISHED`, `ACTIVE`, `INACTIVE` |

**Response:** `APIResponse` with:

- `data`: list of events (`EventOut`-like, `files: []`)
- `pagination`: `{ total, page, page_size }`

---

### Get event — `GET /api/events/{event_id}`

**Response:** `APIResponse` with `data: EventOut` (includes `files`)

---

### Create draft from event — `POST /api/events/{event_id}/draft`

**Request:** No body.

**Response:** `APIResponse` with `data: EventOut` (the new draft). Only for published events.

---

### Toggle event status — `PATCH /api/events/{event_id}/toggle-status`

**Request:** No body.

**Response:** `APIResponse` with `data: EventOut`. Only for ACTIVE/INACTIVE events.

---

### Deactivate event — `DELETE /api/events/{event_id}`

**Response:** `204 No Content`. Sets event status to INACTIVE.

---

## 2. Media (per event)

**Prefix:** `/api/events/{event_id}/media`

| Method | Path | Purpose |
|--------|------|--------|
| GET | `/api/events/{event_id}/media/` | Get media for event (optionally for a version) |

**Query params:**

| Param | Type | Description |
|-------|------|-------------|
| version | int | Optional. Omit to use event’s current version. |

**Response:** `APIResponse` with `data: list[MediaItemOut]`

---

## 3. Revisions (per event)

**Prefix:** `/api/events/{event_id}/revisions`

| Method | Path | Purpose |
|--------|------|--------|
| GET | `/api/events/{event_id}/revisions/` | List all revisions for the event |
| GET | `/api/events/{event_id}/revisions/{media_version}/{revision_number}` | Get one revision snapshot (revision + media at that version) |

### List revisions — `GET /api/events/{event_id}/revisions/`

**Response:** `APIResponse` with `data: list[RevisionOut]`

---

### Get revision snapshot — `GET /api/events/{event_id}/revisions/{media_version}/{revision_number}`

**Path params:** `media_version` (int), `revision_number` (int). Example: `1` and `3` for version `1.3`.

**Response:** `APIResponse` with `data: RevisionDetailOut` (`revision` + `media_items`)

---

## 4. Reference

**Prefix:** `/api/reference`

| Method | Path | Purpose |
|--------|------|--------|
| GET | `/api/reference/divisions` | List distinct division names (for applicability) |
| GET | `/api/reference/designations` | List distinct designation names (for applicability) |

**Response:** `APIResponse` with `data: list[DivisionOut]` or `list[DesignationOut]` (each: `id`, `name`)

---

# Payload & response types

## EventSavePayload (for create/update `data`)

Send as JSON string in form field `data`.

```json
{
  "event_name": "string",
  "sub_event_name": "string | null",
  "event_dates": ["string"] | null,
  "description": "string | null",
  "tags": ["string"] | null,
  "applicability_type": "ALL | DIVISION | EMPLOYEE",
  "applicability_refs": { "division_ids": [1, 2], "designation_ids": [3] } | null,
  "status": "DRAFT | PUBLISHED",
  "selected_filenames": ["file1.jpg", "file2.png"] | null,
  "file_metadata": [
    {
      "original_filename": "file1.jpg",
      "caption": "string | null",
      "description": "string | null",
      "thumbnail_url": "string | null"
    }
  ] | null
}
```

---

## EventOut

```json
{
  "id": 1,
  "event_name": "string",
  "sub_event_name": "string | null",
  "event_dates": [] | null,
  "description": "string | null",
  "tags": [] | null,
  "current_media_version": 1,
  "current_revision_number": 0,
  "version_display": "1.0",
  "status": "DRAFT | PUBLISHED | ACTIVE | INACTIVE",
  "applicability_type": "ALL | DIVISION | EMPLOYEE",
  "applicability_refs": {} | null,
  "draft_parent_id": null | number,
  "created_by": 1,
  "created_by_name": "string",
  "created_at": "ISO datetime",
  "updated_at": "ISO datetime",
  "files": []
}
```

`files` is an array of **MediaFileSummary** (id, original_filename, file_type, file_url, thumbnail_url, caption, description, media_versions). For list endpoint, `files` is always `[]`.

---

## EventListOut

```json
{
  "items": [ "EventOut" ],
  "total": 100,
  "page": 1,
  "page_size": 20
}
```

---

## MediaFileSummary (inside EventOut)

```json
{
  "id": 1,
  "original_filename": "string",
  "file_type": "IMAGE | VIDEO",
  "file_url": "string",
  "thumbnail_url": "string | null",
  "caption": "string | null",
  "description": "string | null",
  "media_versions": [1, 2]
}
```

---

## MediaItemOut (media list / revision snapshot)

```json
{
  "id": 1,
  "event_id": 1,
  "media_versions": [1, 2],
  "file_type": "IMAGE | VIDEO",
  "file_url": "string",
  "thumbnail_url": "string | null",
  "caption": "string | null",
  "description": "string | null",
  "sort_order": 0,
  "file_size_bytes": 12345,
  "original_filename": "string",
  "created_at": "ISO datetime"
}
```

Prepend backend base URL to `file_url` when displaying (e.g. `http://localhost:8000`).

---

## RevisionOut

```json
{
  "id": 1,
  "event_id": 1,
  "media_version": 1,
  "revision_number": 0,
  "version_display": "1.0",
  "event_name": "string",
  "sub_event_name": "string | null",
  "event_dates": [] | null,
  "description": "string | null",
  "tags": [] | null,
  "created_by": 1,
  "created_by_name": "string",
  "created_at": "ISO datetime"
}
```

---

## RevisionDetailOut

```json
{
  "revision": { "RevisionOut" },
  "media_items": [ "MediaItemOut" ]
}
```

---

## DivisionOut / DesignationOut

```json
{
  "id": 1,
  "name": "string"
}
```

---

## Enums

- **EventStatus:** `DRAFT`, `PUBLISHED`, `ACTIVE`, `INACTIVE`
- **ApplicabilityType:** `ALL`, `DIVISION`, `EMPLOYEE`
- **FileType:** `IMAGE`, `VIDEO`
