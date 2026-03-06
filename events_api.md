# Event Flow Module – API & Module Documentation

**Base URL:** `/api`  
**Auth:** All endpoints (except Auth) require `Authorization: Bearer <access_token>`.

All non-auth responses use a standard envelope: `{ "message", "status_code", "status", "data" }`. Paginated lists add `total`, `page`, `page_size`. Errors use the same envelope with `status: "error"`.

---

## 1. MODULE OVERVIEW

The Event Flow module allows users to create, update, publish, and manage events with media (images/videos), applicability targeting, and revision history. It supports manual event creation, draft-from-published workflows, and a clear path for future event verification (e.g. AI-generated or auto-fetched events).

The module supports:

---

### 1.1 Manual Add Event

- **Create event and add content**
  - Create a new event (name, sub-event name, dates, description, tags).
  - Add content: attach images and/or videos with optional caption, description, and (for videos) thumbnail.
  - Save as **DRAFT** or publish directly as **PUBLISHED**; on publish, a revision snapshot is created and media is versioned.

- **Fetch and select linked case and proceeding**
  - Reference data for targeting is provided via **divisions** and **designations** (from the users table).
  - User selects applicability: **ALL**, **DIVISION**, or **EMPLOYEE**, and optionally selects division IDs and/or designation IDs so that only relevant users see the event when filtered by applicability.

- **Select / suggest upcoming events**
  - Event list supports filtering by status (DRAFT, PUBLISHED, ACTIVE, INACTIVE) and pagination.
  - Upcoming-event suggestion can be implemented on top of list and filters (e.g. by date, status) using the same event APIs.

---

### 1.2 Event Verification (AI Generated / Auto-Fetched Events)

- **AI creates Staged Event after extracting data**
  - A “staged” event can be represented as an event with status **DRAFT** created by the system (or by an integration) with extracted fields (name, dates, description, etc.).
  - The same create/update event APIs (`POST /api/events/`, `PUT /api/events/{event_id}`) are used to create or update this staged event.

- **On verification → the event becomes Approved Event**
  - Verification is done by updating the event and setting status to **PUBLISHED** (via the same save flow with `status: PUBLISHED`).
  - Publishing triggers version/revision logic: media version can bump or revision number increments, and an immutable **EventRevision** snapshot is stored.

- **Triggers activity creation**
  - Once the event is published (approved), downstream processes (e.g. activity creation, notifications) can be triggered by the same backend or by separate services consuming the published event data.
  - The current API returns the approved event in the response; activity creation is a follow-on step that can be implemented in the same service or a separate one.

---

### 1.3 Edge Workflow Handling

- **A. Draft from published event**
  - If a user edits a **PUBLISHED** event by saving as **DRAFT**, the backend creates a **child draft** (linked via `draft_parent_id`).
  - When that draft is published, the service either bumps the parent’s media version (if name or files changed) or increments revision number, then merges the draft into the parent (revisions and media move to the draft), parent is set to **INACTIVE**, and the draft becomes the new **PUBLISHED** event.

- **B. Toggle ACTIVE / INACTIVE**
  - Only events in **ACTIVE** or **INACTIVE** can be toggled; DRAFT and PUBLISHED cannot use the toggle-status API.
  - Toggle is used to show/hide events in the “live” list without deleting them.

- **C. Deactivate event**
  - **DELETE** sets the event status to **INACTIVE** (soft delete). No event or media rows are physically removed; the event is excluded from “active” visibility.

- **D. Media and versioning**
  - New uploads start in staging (media_version 0). On publish, staging files are assigned the new media version and an **EventRevision** row is created.
  - If the user only changes metadata (e.g. name) or reorders/keeps same files, the revision number increments without a new media version.

---

### 1.4 Role-Based Behaviour and Applicability

- **Who can create events**
  - **knowledge_hub_admin** and **policy_hub_admin** (and optionally **is_admin**) are the roles that are intended to create and manage events.
  - The backend currently accepts any authenticated user for create/update; role checks (e.g. allow only when `user.knowledge_hub_admin` or `user.policy_hub_admin` is true) can be added in the event router or a dependency so that only these admins can call create/update/delete/toggle.

- **Who sees events (applicability)**
  - Each event has **applicability_type** (ALL, DIVISION, EMPLOYEE) and **applicability_refs** (e.g. division IDs, designation IDs).
  - **Users see events** based on applicability: list/get event APIs can filter or restrict so that:
    - **ALL**: event is visible to all authenticated users.
    - **DIVISION**: event is visible only to users whose `division_cluster` matches one of the selected division refs (reference data comes from `/api/reference/divisions`).
    - **EMPLOYEE**: event is visible only to users whose `designation` (and/or other refs) match the selected applicability refs (reference data from `/api/reference/designations`).
  - Filtering by current user’s division/designation can be implemented in the list-events (and optionally get-event) logic so that only applicable events are returned.

---

## 2. SERVICES USED IN THIS MODULE

Below is a module-scoped list of backend services participating in Event Flow and their responsibility. Roles (e.g. knowledge_hub_admin, policy_hub_admin) are enforced at the API layer so that only authorised users can create/update events; applicability is used to control which users see which events.

---

### 2.1 event_service

**Role in Event Flow**

- Create and update events (DRAFT or PUBLISHED); orchestrate media uploads and file metadata (caption, description, thumbnail).
- Get single event; list events with pagination and optional status filter (list returns events with `files: []` for performance).
- Create draft from published event; publish draft (merge and version bump or revision increment).
- Toggle event status (ACTIVE ↔ INACTIVE); soft-delete (set INACTIVE).
- Sync staging media (version 0) with selected filenames; apply file_metadata to existing media rows.
- Create immutable **EventRevision** snapshots on publish.

**Role / applicability (1–2 points)**

1. Event create/update/delete/toggle endpoints should restrict write operations to users with **knowledge_hub_admin** or **policy_hub_admin** (and/or **is_admin**); event_service is invoked only after this check.
2. List events (and optionally get event) should filter by **applicability** so users only see events targeting ALL or their division/designation, ensuring “users will see the events” only when applicable to them.

---

### 2.2 media_service

**Role in Event Flow**

- Upload event files (images/videos); support optional thumbnail uploads per video.
- Apply per-file **caption**, **description**, and **thumbnail_url** from `file_metadata` in the create/update payload.
- Validate file type (image/video) and size (configurable limits); store files via storage backend and create/update **EventMediaItem** rows with `media_versions` (e.g. staging 0, then published version).
- Return media items for an event (optionally for a specific media version) for GET event detail and revision snapshot.

**Role / applicability (1–2 points)**

1. Used when **knowledge_hub_admin** or **policy_hub_admin** (or other allowed roles) create/update events with attachments; uploads are scoped to the event and its applicability is set at the event level.
2. Media is returned only in the context of an event the user is allowed to see (via applicability filtering on the event).

---

### 2.3 revision_service

**Role in Event Flow**

- List revisions for an event (lightweight: id, event_id, media_version, revision_number, version_display, created_at).
- Get a single revision snapshot: full **EventRevision** plus all **EventMediaItem** rows that have that `media_version` in their `media_versions` array.

**Role / applicability (1–2 points)**

1. Revision list and snapshot are exposed only for events the user is allowed to see (same applicability rules as event list/get).
2. Used by **knowledge_hub_admin** / **policy_hub_admin** (and viewers) to inspect history of an event after it has been published.

---

### 2.4 reference (reference data from users table)

**Role in Event Flow**

- Expose distinct **divisions** (`division_cluster`) and **designations** (`designation`) from the users table for use in applicability (DIVISION / EMPLOYEE).
- No separate “case” or “proceeding” tables in the current schema; divisions and designations drive who sees events when applicability is not ALL.

**Role / applicability (1–2 points)**

1. Used when building event form (applicability step) so that **knowledge_hub_admin** / **policy_hub_admin** can select which divisions/designations an event targets.
2. The same reference values are used on the “read” side to filter events so **users will see the events** only when their profile matches the event’s applicability_refs.

---

### 2.5 storage (local)

**Role in Event Flow**

- Save uploaded files (main files and thumbnails) to local disk; return a URL path for serving.
- Used by media_service for all uploads; configurable via `LOCAL_UPLOAD_DIR` and `SERVE_FILES_URL_PREFIX`.

---

## 3. API LIST – EVENTS, REVISIONS, REFERENCE, MEDIA

(Excludes Auth/User APIs.)

---

### 3.1 Event APIs

| Function              | API                          | Method | Purpose |
|-----------------------|------------------------------|--------|---------|
| Create Event          | `/api/events/`               | POST   | Create event (DRAFT or PUBLISHED). Body: multipart/form-data with `data` (JSON) and optional `files`. |
| Update Event          | `/api/events/{event_id}`    | PUT    | Update event (same body as create). |
| List Events           | `/api/events/`              | GET    | Paginated list; query: `page`, `page_size`, `status`. Response: `data` (events with `files: []`), `total`, `page`, `page_size`. |
| Get Event             | `/api/events/{event_id}`    | GET    | Single event with full `files` array. |
| Create Draft from Event | `/api/events/{event_id}/draft` | POST | Create child DRAFT from a PUBLISHED event. |
| Toggle Event Status   | `/api/events/{event_id}/toggle-status` | PATCH | Switch ACTIVE ↔ INACTIVE. |
| Deactivate Event     | `/api/events/{event_id}`    | DELETE | Set event status to INACTIVE (204 No Content). |

---

### 3.2 Media APIs

| Function       | API                                    | Method | Purpose |
|----------------|----------------------------------------|--------|---------|
| Get Media      | `/api/events/{event_id}/media/`       | GET    | List media items for the event. Optional query: `version` (default: event’s current_media_version). |

---

### 3.3 Revision APIs

| Function            | API                                                           | Method | Purpose |
|---------------------|---------------------------------------------------------------|--------|---------|
| List Revisions      | `/api/events/{event_id}/revisions/`                           | GET    | List revision summaries (id, event_id, media_version, revision_number, version_display, created_at). |
| Get Revision Snapshot | `/api/events/{event_id}/revisions/{media_version}/{revision_number}` | GET | Full revision + media items at that version. |

---

### 3.4 Reference APIs

| Function         | API                         | Method | Purpose |
|------------------|-----------------------------|--------|---------|
| List Divisions   | `/api/reference/divisions`  | GET    | Distinct division_cluster values (for applicability). |
| List Designations| `/api/reference/designations` | GET  | Distinct designation values (for applicability). |

---

## 4. DATA ORCHESTRATION WORKFLOWS

---

### 4.1 Workflow 1 – Manual Event Creation

1. User opens “Add Event” and enters details (event name, sub-event name, dates, description, tags).
2. User uploads files (images/videos), optionally adds caption, description, and for videos a thumbnail; payload includes `file_metadata` per file.
3. User selects applicability (ALL / DIVISION / EMPLOYEE) and optionally division/designation refs (from reference APIs).
4. User saves as DRAFT or PUBLISHED.
5. **UI → POST /api/events/** with multipart/form-data: `data` (JSON: EventSavePayload including `file_metadata`), `files` (main + optional thumbnails).
6. **event_service.save_event** (no event_id): creates Event, calls **media_service.upload_files** with `file_metadata`, syncs staging, applies file_metadata; if status=PUBLISHED runs _publish_event (version/revision and EventRevision created).
7. Response returns the created event (with files if GET single; list returns `files: []`).
8. **Applicability:** When list/get are filtered by current user, only events applicable to that user (ALL or matching division/designation) are returned so **users see the events** as intended. **Creation** is restricted to **knowledge_hub_admin** / **policy_hub_admin** (when role checks are added).

---

### 4.2 Workflow 2 – Event Update

1. User opens an existing event (GET /api/events/{event_id}).
2. User edits details and/or uploads/removes files, updates caption/description/thumbnail via `file_metadata`.
3. User saves (DRAFT or PUBLISHED).
4. **UI → PUT /api/events/{event_id}** with same multipart structure as create.
5. **event_service.save_event** (event_id set): loads event, updates fields, uploads new files and applies file_metadata, syncs staging, applies file_metadata to existing items; if PUBLISHED runs _publish_event or _publish_draft.
6. Response returns updated event. Role and applicability behaviour same as 4.1.

---

### 4.3 Workflow 3 – Event Verification (Staged → Approved)

1. System or integration creates a “staged” event (e.g. DRAFT with extracted data) via **POST /api/events/** (or PUT if updating).
2. User opens the event for verification (GET event, GET media).
3. User corrects content and approves.
4. **UI → PUT /api/events/{event_id}** with `status: PUBLISHED`.
5. **event_service.save_event** publishes the event → it becomes the “Approved Event” (status PUBLISHED, revision snapshot created).
6. Downstream **activity creation** (or other triggers) can be implemented to run after publish; event data is available in the response and in DB.
7. **knowledge_hub_admin** / **policy_hub_admin** (or designated verifiers) perform verification; end **users see the events** after publish according to applicability.

---

### 4.4 Workflow 4 – Draft from Published & Publish Draft

1. User opens a PUBLISHED event and chooses “Create draft” or saves as DRAFT.
2. **UI → POST /api/events/{event_id}/draft** (creates child draft) or PUT with DRAFT (may create or reuse draft depending on implementation).
3. **event_service.create_draft_from_event** (or save_event with DRAFT) creates/reuses draft, copies parent content and media (with version 0 for draft).
4. User edits draft and submits with **status: PUBLISHED**.
5. **event_service.save_event** runs _publish_draft: compares draft to parent (name, files); bumps media version or revision; moves revisions and media to draft; parent set INACTIVE, draft becomes PUBLISHED.
6. List/Get filtered by applicability so only applicable users see the updated event.

---

## 5. DB SCHEMA (PostgreSQL – schema `ecp_events`)

---

### 5.1 events

| Column                 | Type / Notes |
|------------------------|--------------|
| id                     | Integer, PK, autoincrement |
| event_name             | String(255), required |
| sub_event_name         | String(255), nullable |
| event_dates            | JSONB, nullable |
| description            | Text, nullable |
| tags                   | JSONB, nullable |
| current_media_version  | Integer, default 0 |
| current_revision_number| Integer, default 0 |
| status                 | Enum: DRAFT, PUBLISHED, ACTIVE, INACTIVE |
| applicability_type    | Enum: ALL, DIVISION, EMPLOYEE |
| applicability_refs    | JSONB, nullable (e.g. division_ids, designation_ids) |
| draft_parent_id        | FK events(id), nullable, SET NULL on delete |
| created_by             | FK users(id), required |
| created_at             | Timestamp with time zone |
| updated_at             | Timestamp with time zone |

---

### 5.2 event_revisions

| Column          | Type / Notes |
|-----------------|--------------|
| id              | Integer, PK, autoincrement |
| event_id        | FK events(id), CASCADE |
| media_version   | Integer, required |
| revision_number | Integer, required |
| event_name      | String(255), required |
| sub_event_name  | String(255), nullable |
| event_dates     | JSONB, nullable |
| description     | Text, nullable |
| tags            | JSONB, nullable |
| created_by      | FK users(id), required |
| created_at      | Timestamp with time zone |
| Unique          | (event_id, media_version, revision_number) |

---

### 5.3 files (event_media_item)

| Column           | Type / Notes |
|------------------|--------------|
| id               | Integer, PK, autoincrement |
| event_id         | FK events(id), CASCADE |
| media_versions   | ARRAY(Integer), required (e.g. [0], [1], [1,2]) |
| file_type        | Enum: IMAGE, VIDEO |
| file_url         | String(500), required |
| thumbnail_url    | String(500), nullable |
| caption          | String(255), nullable |
| description      | Text, nullable |
| sort_order       | Integer, default 0 |
| file_size_bytes  | BigInteger, required |
| original_filename| String(255), required |
| created_at       | Timestamp with time zone |

---

### 5.4 users

| Column             | Type / Notes |
|--------------------|--------------|
| id                 | Integer, PK, autoincrement |
| email              | String(255), unique, required |
| password_hash      | String(255), required |
| full_name          | String(255), required |
| division_cluster   | String(100), nullable (used for divisions reference & applicability) |
| designation        | String(100), nullable (used for designations reference & applicability) |
| policy_hub_admin   | Boolean, default false |
| is_admin           | Boolean, default false |
| knowledge_hub_admin| Boolean, default false |
| created_at         | Timestamp with time zone |

---

**Payload reference (create/update):**  
`data` (JSON string in form) = **EventSavePayload**: event_name, sub_event_name, event_dates, description, tags, applicability_type, applicability_refs, status, selected_filenames, file_metadata (array of { original_filename, caption, description, thumbnail_original_filename }).  
`files` = main files + optional thumbnail files; order: main files first, then thumbnails, with `file_metadata` linking thumbnails to main files by filename.
