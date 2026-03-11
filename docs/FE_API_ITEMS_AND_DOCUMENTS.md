# Items & Documents API — Frontend Reference

Base URL: `/api`. All endpoints expect auth (Bearer token). Auth APIs are out of scope here.

---

## 1. Items API (`/api/items`)

Generic API for both **events** and **documents**: list, detail, revisions, revision snapshot. Use `item_type` query to choose `event` or `document`.

### List items

| Method | URL | Query |
|--------|-----|--------|
| GET | `/api/items/` | `page` (default 1), `page_size` (default 20), `item_type` (optional: `event` \| `document`) |

**Example:** `GET /api/items/?page=1&page_size=20&item_type=document`

**Response (paginated):**
```json
{
  "message": "Items fetched",
  "status": "success",
  "data": [
    {
      "id": 1,
      "item_type": "document",
      "name": "Testing doc",
      "document_type": "Policy",
      "version_display": "1.0",
      "status": "ACTIVE",
      "created_by": 1,
      "created_by_name": "John Doe",
      "created_at": "2025-03-09T10:00:00",
      "updated_at": "2025-03-09T10:00:00",
      "deactivated_by": null,
      "deactivated_by_name": null,
      "deactivated_at": null,
      "next_review_date": null,
      "revision": 0,
      "version": 1
    }
  ],
  "total": 1,
  "page": 1,
  "page_size": 20
}
```

---

### Get item detail

| Method | URL | Query |
|--------|-----|--------|
| GET | `/api/items/{item_id}` | `item_type` (required: `event` \| `document`) |

**Example:** `GET /api/items/5?item_type=document`

**Response (document detail):**
```json
{
  "message": "Item fetched",
  "status": "success",
  "data": {
    "id": 5,
    "name": "testing doc",
    "document_type": "Policy",
    "tags": ["hr", "policy"],
    "summary": "some summary",
    "legislation_id": null,
    "sub_legislation_id": null,
    "version": 1,
    "next_review_date": null,
    "download_allowed": true,
    "linked_document_ids": [],
    "applicability_type": "ALL",
    "applicability_refs": null,
    "status": "ACTIVE",
    "current_media_version": 1,
    "current_revision_number": 0,
    "version_display": "1.0",
    "change_remarks": null,
    "deactivate_remarks": null,
    "deactivated_at": null,
    "replaces_document_id": null,
    "created_by": 1,
    "created_by_name": "John Doe",
    "created_at": "2025-03-09T10:00:00",
    "updated_at": "2025-03-09T10:00:00",
    "files": [
      {
        "id": 1,
        "original_filename": "doc.pdf",
        "file_type": "PDF",
        "file_url": "/uploads/...",
        "media_versions": [1],
        "file_size_bytes": 1024
      }
    ],
    "linked_document_details": null
  }
}
```

**Note:** `revision_number` in the detail is `current_revision_number`. Display version is `version_display` (e.g. `"1.0"` = media_version 1, revision_number 0). `summary` can be `null`.

---

### List item revisions

| Method | URL | Query |
|--------|-----|--------|
| GET | `/api/items/{item_id}/revisions` | `item_type` (required: `event` \| `document`) |

**Example:** `GET /api/items/5/revisions?item_type=document`

**Response:**
```json
{
  "message": "Revisions fetched",
  "status": "success",
  "data": [
    {
      "id": 10,
      "media_version": 1,
      "revision_number": 0,
      "version_display": "1.0",
      "created_at": "2025-03-09T10:00:00",
      "change_remarks": null,
      "event_id": null,
      "document_id": 5
    }
  ]
}
```

---

### Get revision snapshot

| Method | URL | Query |
|--------|-----|--------|
| GET | `/api/items/{item_id}/revisions/{media_version}/{revision_number}` | `item_type` (required: `event` \| `document`) |

**Example:** `GET /api/items/5/revisions/1/0?item_type=document`

**Response (document snapshot):**
```json
{
  "message": "Revision fetched",
  "status": "success",
  "data": {
    "revision": {
      "id": 10,
      "document_id": 5,
      "media_version": 1,
      "revision_number": 0,
      "version_display": "1.0",
      "name": "testing doc",
      "document_type": "Policy",
      "tags": ["hr"],
      "summary": "some summary",
      "applicability_type": "ALL",
      "applicability_refs": null,
      "created_by": 1,
      "created_by_name": "John Doe",
      "created_at": "2025-03-09T10:00:00"
    },
    "files": [
      {
        "id": 1,
        "original_filename": "doc.pdf",
        "file_type": "PDF",
        "file_url": "/uploads/...",
        "media_versions": [1],
        "file_size_bytes": 1024
      }
    ]
  }
}
```

---

## 2. Documents API (`/api/documents`)

### List documents

| Method | URL | Query |
|--------|-----|--------|
| GET | `/api/documents/` | `page`, `page_size`, `status` (optional), `document_type` (optional) |

**Example:** `GET /api/documents/?page=1&page_size=20&status=ACTIVE`

---

### Get document

| Method | URL |
|--------|-----|
| GET | `/api/documents/{document_id}` |

Same response shape as **Get item detail** with `item_type=document` (see above).

---

### Create document

| Method | URL | Body |
|--------|-----|------|
| POST | `/api/documents/` | **multipart/form-data:** `data` (JSON string), optional `files` (array of files) |

**Payload (JSON in `data` field):**
```json
{
  "name": "testing doc",
  "document_type": "Policy",
  "tags": ["hr", "policy"],
  "summary": "some summary",
  "legislation_id": null,
  "sub_legislation_id": null,
  "version": 1,
  "next_review_date": null,
  "download_allowed": true,
  "linked_document_ids": [],
  "applicability_type": "ALL",
  "applicability_refs": null,
  "status": "DRAFT",
  "selected_filenames": ["doc.pdf"],
  "change_remarks": null
}
```

- `summary` can be `null`.
- `document_type`: use label (e.g. `"Policy"`) or enum (e.g. `"POLICY"`).
- `status`: `"DRAFT"` or `"ACTIVE"`. For `ACTIVE`, at least one file is required.
- `selected_filenames`: list of filenames (existing + new). New files go in the `files` part of the form.

---

### Update document

| Method | URL | Body |
|--------|-----|------|
| PUT | `/api/documents/{document_id}` | **multipart/form-data:** `data` (JSON string), optional `files` (new files only) |

Same payload shape as create. Include `change_remarks` when re-activating an existing ACTIVE document.

**Example payload (edit, save as draft):**
```json
{
  "name": "testing doc",
  "document_type": "Policy",
  "tags": ["hr"],
  "summary": null,
  "legislation_id": null,
  "sub_legislation_id": null,
  "version": 1,
  "next_review_date": null,
  "download_allowed": true,
  "linked_document_ids": [3, 4],
  "applicability_type": "DIVISION",
  "applicability_refs": { "divisions": [1], "designations": [2], "employees": [] },
  "status": "DRAFT",
  "selected_filenames": ["doc.pdf", "new.pdf"],
  "change_remarks": null
}
```

---

### Linked options (for wizard)

| Method | URL | Query |
|--------|-----|--------|
| GET | `/api/documents/linked-options` | `document_type`, `exclude_id` (optional, e.g. current doc when editing) |

**Example:** `GET /api/documents/linked-options?document_type=Policy&exclude_id=5`

Returns list of documents that can be linked (e.g. `{ id, name, ... }`).

---

## 3. Document wizard — which API and payload per action

| User action | API call | Payload / notes |
|-------------|----------|------------------|
| **Open wizard (new)** | None | Load reference data (document types, legislation, divisions, designations) as needed. |
| **Open wizard (edit)** | `GET /api/items/{id}?item_type=document` or `GET /api/documents/{id}` | Use response to fill form; `current_revision_number` and `version_display` are in the detail. |
| **Next / Back** | None | Client-only step change. |
| **Save as Draft** | **New:** `POST /api/documents/` with multipart (`data` + optional `files`). **Edit:** `PUT /api/documents/{id}` with multipart. | `data`: JSON payload with `status: "DRAFT"`. `name`, `document_type`, `tags` required; `summary` can be `null`. |
| **Activate Now** | Same as Save as Draft | `data`: same JSON with `status: "ACTIVE"`. At least one file required. If editing an ACTIVE doc, set `change_remarks`. |

**Detail response fields for revision display:**  
Use `current_revision_number`, `current_media_version`, and `version_display` (e.g. `"1.0"`) from the item/document detail. To show a specific revision, call **Get revision snapshot** with `media_version` and `revision_number` from the revisions list.

---

## 4. Quick examples

**Create document (draft):**
- `POST /api/documents/`
- Form: `data` = `{"name":"testing doc","document_type":"Policy","tags":["hr"],"summary":null,"legislation_id":null,"sub_legislation_id":null,"version":1,"next_review_date":null,"download_allowed":true,"linked_document_ids":[],"applicability_type":"ALL","applicability_refs":null,"status":"DRAFT","selected_filenames":[],"change_remarks":null}`

**Get document detail (for edit / revision display):**
- `GET /api/items/5?item_type=document`  
  → use `data.current_revision_number`, `data.version_display`, `data.name`, `data.summary`, etc.

**Get a specific revision snapshot:**
- `GET /api/items/5/revisions/1/0?item_type=document`  
  → `data.revision` has `name`, `summary`, `revision_number`, etc.; `data.files` has files at that version.
