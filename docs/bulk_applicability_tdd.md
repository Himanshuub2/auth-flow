## Bulk Applicability Module -- TDD & API Documentation

**Base URL:** `/``api``/`\
**Auth:** All endpoints require `Authorization: Bearer <access_token>`.

## 1. MODULE OVERVIEW

The Bulk Applicability module allows admins to:

-   Download an Excel template for selected types (document types +
    events).
-   Upload a filled template for mass applicability updates.
-   Queue updates for **night-time processing** (off working hours) to
    reduce DB load during business hours.
-   Track processing and errors from a single **history API**.
-   Update applicability in bulk for multiple documents and events using
    one upload.

This document is a simple Technical Design Document (TDD) covering
features, APIs, flow, error handling, and schema at a high level.

### 1.1 Small Use Case Summary

-   Admin wants to update applicability of many documents and events in
    one go.
-   Admin downloads template, marks division applicability, uploads
    file.
-   System processes at night and updates `applicability_refs` in target
    tables.

## 2. MAIN MODULE COMPONENTS

### 2.1 Bulk Applicability Request

-   Stores one upload request as a durable DB record.
-   Tracks lifecycle status (`PENDING`, `IN_PROGRESS`, `COMPLETED`,
    `FAILED`).
-   Stores upload file blob path and processing outputs (including error
    message).
-   Supports dashboard table fields:
    -   `id`
    -   `updated_by`
    -   `updated_on`
    -   `status`
    -   `bulk_upload` (`file_sas_url`)
    -   `error` (`message`)
    -   `change_remarks`

### 2.2 Template & Upload Files

-   uploaded files are stored in Azure Blob.
-   DB stores blob path/key; API returns SAS URL (`file_sas_url`) to UI.
-   Template uses only these columns: `id`, `name`, `type`,
    `updated_on`, and division columns.
-   Division columns are generated from distinct `division_cluster`
    values from the users table.
-   Only division applicability is updated from this template (no
    designation columns in this version).

### 2.3 Night Scheduler (Cron)

-   Uses **Azure Function Timer Trigger** as cron scheduler.
-   Runs at configured night window (example: 01:00 local time).
-   Calls internal AKS processing API to process queued jobs.
-   Ensures heavy DB updates run after working hours.

### 2.4 Processor (AKS Backend)

-   Downloads upload file from blob.
-   Parses and validates Excel rows.
-   Applies updates in a DB transaction.
-   Writes status + error message back to request table.
-   Builds applicability payload and writes it to `applicability_refs`
    in:
    -   `documents.documents` (schema: `documents`)
    -   `events.events` (schema: `events`)

## 3. API LIST -- BULK APPLICABILITY

### 3.1 Bulk Applicability APIs

+---------------+---------------------------+----+--------------------+
| Function      | API                       | Me | > Role / Purpose   |
|               |                           | th |                    |
|               |                           | od |                    |
+===============+===========================+====+====================+
| Download      | `/``api``/bulk-applica    | PO | > Generate         |
| Template      | bility/download-template` | ST | > template for     |
|               |                           |    | > selected types   |
|               |                           |    | > and  file   |
|               |                           |    |     |
+---------------+---------------------------+----+--------------------+
| Upload Bulk   | `/``api``/b               | PO | > Upload `.xlsx`,csv,xls,  |
| File          | ulk-applicability/upload` | ST | > create request   |
|               |                           |    | > row as           |
|               |                           |    | > `PENDING`,       |
|               |                           |    | > return request   |
|               |                           |    | > id. No heavy DB  |
|               |                           |    | > update in this   |
|               |                           |    | > request.         |
+---------------+---------------------------+----+--------------------+
| History       | `/``api``/bu              | G  | > Paginated        |
|               | lk-applicability/history` | ET | > dashboard list   |
|               |                           |    | > with status and  |
|               |                           |    | > error field.     |
+---------------+---------------------------+----+--------------------+
| Internal      | `/``                      | PO | > Called by Azure  |
| Night         | api``/internal/bulk-appli | ST | > Function cron to |
| Processor     | cability/process-pending` |    | > process queued   |
|               |                           |    | > records in       |
|               |                           |    | > batch. Internal  |
|               |                           |    | > use only.        |
+---------------+---------------------------+----+--------------------+

### 3.2 History API Response Contract (Dashboard)

History table row fields returned by API:

-   `id`: Request id (or display id)
-   `updated_by`: User name/id who last updated the request
-   `updated_on`: Last updated timestamp
-   `status`: `PENDING` / `IN_PROGRESS` / `COMPLETED` / `FAILED`
-   `bulk_upload`: `file_name` and when user click send the url 
-   `error`: processing error message (null when success)
-   `change_remarks`: optional remarks for this bulk request

Example `data.items[]`:

    {
      "id": "0042",
      "updated_by": "username",
      "updated_on": "2026-04-10",
      "status": "FAILED",
      "bulk_upload": "file_name.xlsx",
      "error": "Row 23: Invalid value 'X' in column HR. Allowed values: Y/N.",
      "change_remarks": "April applicability correction"
    }

## 4. ORCHESTRATION FLOWS -- BULK APPLICABILITY

### 4.1 Upload and Queue (Day-time)

1.  Admin uploads Excel using `POST /api/bulk-applicability/upload`.
2.  Backend validates file extension and stores file in Azure Blob.
3.  Backend inserts request row with:
    -   `status = PENDING`
    -   upload blob path
    -   `change_remarks`
    -   audit fields (`created_by`, `updated_by`)
4.  Backend returns `202 Accepted` with request id.
5.  No heavy update is executed in this request.

### 4.2 Night Processing via Cron (Off-hours)

1.  Azure Function timer runs on schedule (example: 01:00 daily).
2.  Function calls internal API:
    `POST /api/internal/bulk-applicability/process-pending`.
3.  Backend picks `PENDING` records (ordered by creation time).
4.  For each record:
    -   mark `IN_PROGRESS`
    -   download blob file
    -   parse and validate all rows
    -   prepare applicability payload from division columns
    -   apply updates in one transaction to `documents.documents` and
        `events.events`
    -   set `COMPLETED` or `FAILED` with `error`
5.  Admin checks status/error from
    `GET /api/bulk-applicability/history`.

### 4.3 Failure Scenarios

-   **Template/upload format error**: request marked `FAILED`; error
    message saved in `error`.
-   **Validation error (row/column)**: transaction not applied; request
    marked `FAILED`.
-   **DB exception during update**: full rollback and mark `FAILED` with
    sanitized error message.
-   **Function unable to call AKS internal API**: records stay
    `PENDING`; next cron run retries.
-   **Pod restart while processing**: stale `IN_PROGRESS` can be
    recovered by nightly retry rule (age threshold + safe requeue
    strategy).

### 4.4 Rollback Rule (All-or-Nothing)

-   Processing runs in a single DB transaction for one uploaded file.
-   If any record fails, the whole transaction is rolled back.
-   No partial update is kept for that upload.

## 5. DB SCHEMA -- BULK APPLICABILITY

High-level schema for request tracking table.

### 5.1 bulk_applicability_requests

  -----------------------------------------------------------------------
  Column                    Type / Notes
  ------------------------- ---------------------------------------------
  id                        Integer, PK, autoincrement
  file_name                 String, file name


  uploaded_file_url         String, blob path/key for uploaded file

  selected_types            JSON/JSONB list

  status                    Enum: `PENDING`, `IN_PROGRESS`, `COMPLETED`,
                            `FAILED`


  error_message             Text, nullable (used as `error` in history
                            UI)

  change_remarks            Text, nullable

  created_by                FK user identifier

  updated_by                FK user identifier

  created_at                Timestamp with time zone

  updated_at                Timestamp with time zone
  -----------------------------------------------------------------------

Recommended indexes:

-   `(status, created_at)` for cron pickup.
-   `(updated_at)` for history sorting.
-   `(id)` unique for UI lookup.

## 6. NON-FUNCTIONAL NOTES

-   Heavy DB updates are intentionally moved to night schedule to reduce
    business-hour impact.
-   Keep processor idempotent and status-driven
    (`PENDING -> IN_PROGRESS -> terminal`) to avoid duplicate execution.
-   Internal processor API should be private/authenticated (Function
    identity or API key).
-   Keep errors concise for UI (`error` string), while detailed logs
    remain in server logs.
-   Runtime stack for this use case:
    -   PostgreSQL for request tracking and applicability updates
    -   Azure Functions (timer/cron) for night trigger
    -   AKS backend service for processing, validation, and DB write
        execution
