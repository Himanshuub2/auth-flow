## Document Flow Module – API & Module Documentation

**Base URL:** `/api`  
**Auth:** All endpoints require `Authorization: Bearer <access_token>`.

All non-auth responses use the common envelope `{ "message", "status_code", "status", "data" }`. Paginated lists add `total`, `page`, `page_size`.

---

## 1. MODULE OVERVIEW

The Document Flow module allows admins to:

- Create, edit, and manage documents with multiple file attachments.
- Store and serve files from **Azure Blob Storage** using SAS URLs stored as `file_url`.
- Maintain document **versions and revisions** (draft vs active, history of changes).
- Filter and report on documents by type, status, owner, and review dates.

This section focuses on **what** the module provides (features, APIs, and flows), not low-level implementation details.

---

## 2. MAIN MODULE COMPONENTS

### 2.1 Documents

- Handle document metadata such as name, document type (Policy, EWS, Events, etc.), tags, summary, review dates, and status (Draft / Active / Inactive).
- Support draft-from-active flow where edits can be staged and then activated as a new version.
- Track current media version and revision so the system can show the latest or historical state.
- Allow linking up to **6** other documents to a document for cross-reference.
- Enforce a maximum of **6 files** per document.
- Respect `download_allowed`: when it is **true**, users can download files; when **false**, files can be viewed in the UI but not downloaded.

### 2.2 Files

- Store document attachments in Azure Blob Storage.
- Persist only the **SAS URLs** in the database so the frontend can directly download/view files.
- Associate each file with one or more document versions so older versions keep their original files.

### 2.3 Reference (Documents)

- Provide reference data for the UI:
  - List of document types (Policy, EWS, Events, FAQ, Latest News & Announcements, etc.).
  - List of legislations and sub-legislations for classification.

### 2.4 Storage (Azure)

- Use a configured Azure storage account and container for all document files.
- Generate SAS URLs for uploads so `file_url` can be used directly by clients without extra proxy logic.

---

## 3. API LIST – DOCUMENTS, FILTER & SUMMARY

(Excludes Auth/User and event-specific APIs.)

### 3.1 Document APIs

| Function                   | API                                  | Method | Role / Purpose |
|----------------------------|---------------------------------------|--------|----------------|
| Create Document            | `/api/documents/`                    | POST   | Create a new document with metadata and attached files (up to 6). Returns the created document. |
| Update Document            | `/api/documents/{document_id}`       | PUT    | Update an existing document (metadata and files). Supports appending new files and keeping/removing existing ones. |
| List Documents             | `/api/documents/`                    | GET    | Paginated list of documents. Can be filtered by status and document type. Used for document listing grids. |
| Get Document               | `/api/documents/{document_id}`       | GET    | Fetch full details of a single document, including current-version files. Used for view/edit screens. |
| Create Draft from Document | `/api/documents/{document_id}/draft` | POST   | Create a draft copy from an active document so changes can be staged before activation. |
| Toggle Document Status     | `/api/documents/{document_id}/toggle-status` | PATCH | Switch between ACTIVE and INACTIVE without changing version history. |
| Deactivate Document        | `/api/documents/{document_id}`       | DELETE | Deactivate a document with remarks (soft delete). |
| List Document Revisions    | `/api/documents/{document_id}/revisions/` | GET | List all revisions for a document for audit/history views. |
| Get Revision Snapshot      | `/api/documents/{document_id}/revisions/{media_version}/{revision_number}` | GET | Fetch metadata and files for a specific revision. |

**Special document-type behaviour**

- **FAQ**:
  - Only one active FAQ document is kept in the table.
  - FAQ documents accept a single **xlsx** file which is used to populate FAQ entries on the FAQ page.
  - An **Export** option allows admins to export the current FAQ data to CSV based on the filters applied on the FAQ listing.
- **Latest News & Announcements**:
  - Only **image** files are allowed for this document type.

---

### 3.2 Filter API – Combined Items (Events + Documents)

Although this API can search both events and documents, it is used here mainly for document dashboards and admin search.

| Function      | API                 | Method | Role / Purpose |
|---------------|---------------------|--------|----------------|
| Filter Items  | `/api/items/filter` | GET    | Search and filter items (including documents) using a set of AND-based filters. |

**Document-related filters:**

- `item_type` – when set to `document`, restricts results to documents.
- `document_type` – filter by type (Policy, EWS, Events, etc.).
- `document_id` – filter by a specific document (used by the “document name” dropdown).
- `status` – filter by status (e.g. ACTIVE, DRAFT, INACTIVE).
- `updated_by` – filter by who last updated the item.
- `updated_from` / `updated_to` – filter by last updated date range.
- `review_from` / `review_to` – filter by review date range.

All filters are combined with **AND** semantics so admins can narrow down to exactly the set of documents they need.

The UI typically:

1. Selects a document type (Policy, EWS, Events, etc.).
2. Loads the matching document names for that type.
3. Applies additional filters (status, updated by, last updated between, review date range).

---

### 3.3 Document Type Summary API

| Function               | API                      | Method | Role / Purpose |
|------------------------|--------------------------|--------|----------------|
| Document Type Summary  | `/api/documents/summary` | GET    | Provide counts per document type and status for dashboard tiles and reports. |

Typical summary fields per document type:

- Total documents.
- Counts by status (Published/Active, Draft, Inactive).
- Counts for **due for review** and **overdue for review**, based on the review date and current date.

This API is read-only and returns only aggregated numbers, not full document rows.

---

### 3.4 Reference APIs (Documents)

| Function              | API                                          | Method | Role / Purpose |
|-----------------------|----------------------------------------------|--------|----------------|
| List Document Types   | `/api/reference/documents/document-types`    | GET    | Populate document type dropdowns (Policy, EWS, Events, etc.). |
| List Legislations     | `/api/reference/documents/legislation`       | GET    | Populate legislation dropdowns. |
| List Sub-Legislations | `/api/reference/documents/sub-legislation`   | GET    | Populate sub-legislation dropdowns filtered by a legislation id. |

---

## 4. ORCHESTRATION FLOWS – DOCUMENTS

### 4.1 Manual Document Creation

1. Admin opens **Add Document** and fills in document details (name, type, summary, tags, review date, etc.).
2. Admin uploads one or more files that will be stored in Azure and referenced by SAS URL.
3. Admin chooses whether to save the new document as **Draft** or immediately mark it **Active**.
4. Backend creates the document record, uploads files to Azure, and associates the files with the first version of the document.
5. List and detail APIs then surface the new document for further viewing and editing.

---

### 4.2 Document Update (Append / Remove Files)

1. Admin opens an existing document using the **Get Document** API.
2. Admin can change metadata (name, summary, review date, tags, status) and:
   - Append new files.
   - Remove files that should no longer be part of the latest version.
3. The update call sends the full set of filenames that should belong to the latest version, plus any new uploads.
4. Backend updates the document, uploads any new files to Azure, and updates version information so that:
   - New files are added to the latest version.
   - Removed files stay only on older versions and no longer appear in the current one.

---

### 4.3 Draft from Active & Publish Draft

1. From an **Active** document, an admin creates a **Draft** copy to make changes without affecting users immediately.
2. The draft starts with the same metadata and files as the active document.
3. Admin edits the draft (metadata and files) and then activates it.
4. On activation, the draft becomes the new active version:
   - A new version or revision is recorded.
   - History remains available through the revision APIs.

These flows together provide a complete lifecycle for documents: creation, editing, versioning, filtering, and reporting, all backed by Azure-based file storage.

---

## 5. DB SCHEMA – DOCUMENTS

High-level view of the main tables used for documents and their files.

### 5.1 documents

| Column                 | Type / Notes |
|------------------------|--------------|
| id                     | Integer, PK, autoincrement |
| name                   | String(255), required |
| document_type          | Enum: POLICY, GUIDANCE_NOTE, LAW_REGULATION, TRAINING_MATERIAL, EWS, FAQ, LATEST_NEWS_AND_ANNOUNCEMENTS |
| tags                   | JSON/JSONB, list of strings |
| summary                | Text, nullable |
| legislation_id         | Integer, nullable |
| sub_legislation_id     | Integer, nullable |
| version                | Integer, default 1 |
| next_review_date       | Date, nullable |
| download_allowed       | Boolean, default true; when false, files are view-only (no download) |
| linked_document_ids    | JSON/JSONB array of integers; up to 6 linked documents |
| applicability_type     | Enum (ALL, DIVISION, EMPLOYEE) |
| applicability_refs     | JSON/JSONB, nullable |
| status                 | Enum: DRAFT, ACTIVE, INACTIVE |
| current_media_version  | Integer, default 0 (latest published media version; 0 means no published files yet) |
| current_revision_number| Integer, default 0 (latest revision number within current_media_version) |
| staging_file_ids       | JSON/JSONB array of integers; IDs of files currently in draft/staging (used before publish) |
| replaces_document_id   | FK documents(id), nullable (used for draft-from-active workflow) |
| created_by             | FK users(id) |
| created_at             | Timestamp with time zone |
| updated_at             | Timestamp with time zone |

### 5.2 document_revisions

| Column          | Type / Notes |
|-----------------|--------------|
| id              | Integer, PK, autoincrement |
| document_id     | FK documents(id), CASCADE |
| media_version   | Integer, required |
| revision_number | Integer, required |
| name            | String(255), required |
| document_type   | Enum, required |
| tags            | JSON/JSONB, nullable |
| summary         | Text, nullable |
| applicability_type | Enum, required |
| applicability_refs | JSON/JSONB, nullable |
| file_ids        | JSON/JSONB array of integers; immutable list of file IDs that belong to this revision/media_version |
| created_by      | FK users(id), required |
| created_at      | Timestamp with time zone |
| Unique          | (document_id, media_version, revision_number) |

### 5.3 document_files

| Column           | Type / Notes |
|------------------|--------------|
| id               | Integer, PK, autoincrement |
| document_id      | FK documents(id), CASCADE |
| file_type        | Enum: IMAGE, DOCUMENT |
| file_url         | String(500), required (Azure SAS URL) |
| original_filename| String(255), required |
| file_size_bytes  | BigInteger, required |
| sort_order       | Integer, default 0 |
| created_at       | Timestamp with time zone |

Constraints and rules:

- A document can have at most **6** rows in `document_files` for the current version.
- FAQ documents are constrained to a single xlsx file.
- Latest News & Announcements documents are constrained to files with image file_type.

