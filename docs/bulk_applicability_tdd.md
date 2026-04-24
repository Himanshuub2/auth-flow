## Bulk Applicability Module – TDD & API Documentation

**Base URL:** `/api`  
**Auth:** All endpoints require `Authorization: Bearer <access_token>`.

All JSON APIs follow the common envelope:
`{ "message", "status_code", "status", "data" }`.

---

## 1. MODULE OVERVIEW

The Bulk Applicability module allows admins to:

- Download a template for selected types (document types + events).
- Upload a filled file (`.xlsx`, `.xls`, `.csv`) for bulk applicability updates.
- Queue processing through request rows with status tracking.
- Process queued requests using a scheduled trigger or manual run.
- Track success/failure with error details in history.

Applicability updates are written to:

- `documents.documents`
- `events.events`

---

## 2. MAIN MODULE COMPONENTS

### 2.1 Request Tracker

Each upload creates one `bulk_applicability_requests` row:

- `status`: `PENDING` -> `IN_PROGRESS` -> `COMPLETED` / `FAILED`
- `uploaded_file_url`: blob path of uploaded file
- `error_message`: validation/processing failure details
- audit fields: `created_by`, `updated_by`, `created_at`, `updated_at`

### 2.2 Template and Parsing

- Template has two top rows:
  - Row 1: organization vertical reference values
  - Row 2: headers (`id`, `type`, `name`, `updated_at`, division columns...)
- Data starts from row 3.
- Division columns accept only `Y` / `N` (also `YES` / `NO` supported).
- If a row has no `Y/N` in division columns, it is ignored (no update).

### 2.3 Processing

- Uploaded request is saved first as `PENDING`.
- Processor reads file from blob, validates rows, resolves type (document/event), and applies batch updates.
- On error, request is marked `FAILED` with user-readable message.

---

## 3. API LIST – BULK APPLICABILITY

### 3.1 Bulk Applicability APIs

| Function | API | Method | Role / Purpose |
|----------|-----|--------|----------------|
| Download Template | `/api/bulk-applicability/download-template` | POST | Generate Excel template for selected types. |
| Upload Bulk File | `/api/bulk-applicability/upload` | POST | Upload file, create `PENDING` request, optionally start processing immediately. |
| History | `/api/bulk-applicability/history` | GET | Fetch paginated request history or single request details by id. |
| Process Pending | `/api/bulk-applicability/process-pending` | POST | Process all `PENDING` requests. Used by scheduler and can be triggered manually. |

---

## 4. API DETAILS (PAYLOAD & RESPONSE)

### 4.1 Download Template

**Endpoint:** `POST /api/bulk-applicability/download-template`  
**Content-Type:** `application/json`  
**Response Type:** File stream (`.xlsx`)

**Request payload**

```json
{
  "selected_types": ["POLICY", "EWS", "EVENTS"]
}
```

**Rules**

- `selected_types` is required.
- Allowed values are all document enum values plus `EVENTS`.
- Returns streamed Excel file with filename like:
  `bulk_applicability_template_policy_ews_events.xlsx`.

**Success response**

- `200 OK` with file stream and header:
  `Content-Disposition: attachment; filename="<generated-name>.xlsx"`.

**Validation error example**

```json
{
  "detail": [
    {
      "type": "value_error",
      "loc": ["body", "selected_types"],
      "msg": "Invalid type(s): ['ABC']. Allowed: [...]"
    }
  ]
}
```

---

### 4.2 Upload Bulk File

**Endpoint:** `POST /api/bulk-applicability/upload`  
**Content-Type:** `multipart/form-data`

**Form payload**

- `file` (required): `.xlsx` / `.xls` / `.csv`
- `selected_types` (optional): comma-separated string like `POLICY,EWS,EVENTS`
- `change_remarks` (optional): text
- `force_start` (optional): boolean, default `false`

**Example request (form-data)**

```text
file=<bulk_upload.xlsx>
selected_types=POLICY,EWS,EVENTS
change_remarks=April applicability update
force_start=false
```

**Success response (`202 Accepted`)**

```json
{
  "message": "File uploaded successfully. Processing queued.",
  "status_code": 202,
  "status": "success",
  "data": {
    "request_id": 42,
    "message": "Processing queued"
  }
}
```

If `force_start=true`, message becomes:

- top-level `message`: `"File uploaded and processing started."`
- `data.message`: `"Processing started"`

**Error response examples**

Invalid extension:

```json
{
  "detail": "Invalid file extension '.txt'. Allowed: csv, xls, xlsx"
}
```

Blob upload failure:

```json
{
  "detail": "Failed to upload file to blob storage."
}
```

---

### 4.3 History

**Endpoint:** `GET /api/bulk-applicability/history`

**Query params**

- `page` (default `1`, min `1`)
- `page_size` (default `10`, min `1`, max `100`)
- `request_id` (optional): return only one request with `file_sas_url`

#### A) Paginated history response

`GET /api/bulk-applicability/history?page=1&page_size=10`

```json
{
  "message": "History fetched",
  "status_code": 200,
  "status": "success",
  "data": [
    {
      "id": 42,
      "updated_by": "A12345",
      "updated_on": "2026-04-20T05:30:00Z",
      "status": "FAILED",
      "file_name": "bulk_upload.xlsx",
      "file_sas_url": null,
      "error": "Validation errors (fix each row/column, then re-upload): ...",
      "change_remarks": "April applicability update"
    }
  ],
  "total": 12,
  "page": 1,
  "page_size": 10
}
```

#### B) Single request response

`GET /api/bulk-applicability/history?request_id=42`

```json
{
  "message": "History fetched",
  "status_code": 200,
  "status": "success",
  "data": {
    "id": 42,
    "updated_by": "A12345",
    "updated_on": "2026-04-20T05:30:00Z",
    "status": "COMPLETED",
    "file_name": "bulk_upload.xlsx",
    "file_sas_url": "https://<storage>/<container>/...<sas-token>",
    "error": null,
    "change_remarks": "April applicability update"
  }
}
```

Not found (`404`):

```json
{
  "detail": "Bulk applicability request not found"
}
```

---

### 4.4 Process Pending

**Endpoint:** `POST /api/bulk-applicability/process-pending`  
**Purpose:** Process all requests currently in `PENDING`.

**Request payload**

- No request body.

**Success response (`200 OK`)**

```json
{
  "message": "Processing complete",
  "status_code": 200,
  "status": "success",
  "data": {
    "processed": 3,
    "failed": 1,
    "total": 4
  }
}
```

---

## 5. ORCHESTRATION FLOW

### 5.1 Upload and Queue

1. Admin uploads file to `/api/bulk-applicability/upload`.
2. Backend validates extension and uploads file to blob.
3. Backend creates request row as `PENDING`.
4. Response returns `request_id` with `202 Accepted`.

### 5.2 Processing

1. Scheduler or admin triggers `/api/bulk-applicability/process-pending`.
2. Service picks all `PENDING` requests in created order.
3. For each request:
   - set `IN_PROGRESS`
   - download and parse file
   - validate rows and IDs
   - batch update document/event applicability
   - set `COMPLETED` or `FAILED`

### 5.3 Failure Behavior

- Bad structure/content -> `FAILED` with clear validation message.
- Missing IDs in DB -> `FAILED`.
- DB update error -> update transaction rolled back, request marked `FAILED`.

---

## 6. DB SCHEMA – BULK APPLICABILITY REQUESTS

### 6.1 `documents.bulk_applicability_requests`

| Column | Type / Notes |
|--------|--------------|
| `id` | Integer, PK, autoincrement |
| `file_name` | String(255), required |
| `uploaded_file_url` | String(500), required (blob path/key) |
| `selected_types` | JSONB list, required |
| `status` | Enum: `PENDING`, `IN_PROGRESS`, `COMPLETED`, `FAILED` |
| `error_message` | Text, nullable |
| `change_remarks` | Text, nullable |
| `created_by` | FK `users.users.staff_id`, required |
| `updated_by` | FK `users.users.staff_id`, nullable |
| `created_at` | Timestamp with timezone |
| `updated_at` | Timestamp with timezone |

Recommended indexes:

- `(status, created_at)` for pending pickup.
- `(updated_at)` for history sorting.

---

## 7. Notes

- Allowed upload formats: `xlsx`, `xls`, `csv`.
- Row updates support both document types and events in one file.
- Division `Y` values map to:
  - `applicability_type = DIVISION`
  - `applicability_refs = { "divisions": [...], "designations": [] }`
- No selected division (`all N`) maps to:
  - `applicability_type = ALL`
  - `applicability_refs = null`
