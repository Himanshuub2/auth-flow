## Compliance HelpDesk Module – API & Module Documentation

**Base URL:** `/api`
**Auth:** All endpoints require `Authorization: Bearer <access_token>`.

All non-auth responses use the common envelope `{ "message", "status_code", "status", "data" }`. Paginated lists add `total`, `page`, `page_size`.

---

## 1. MODULE OVERVIEW

The Compliance HelpDesk module provides a unified portal for employees and admins to manage compliance-related interactions:

- **Queries** – Employees raise compliance questions; admins assign, respond, and resolve.
- **Complaints** – Employees report compliance violations (COBCE, COI, Others); admins investigate and respond.
- **Self Declarations** – Employees (or on behalf of others) declare awareness of policy violations with structured line items.
- **Gift Declarations** – Employees declare gifts given/received with full details (value, ringi approval, parties involved).
- **Annual Declarations** – Admin-initiated yearly cycles (COBCE/COI and R5.18) where every active employee must declare or confirm "nothing to declare".

**Roles:**

- **Employee** – Can view their own requests, raise queries/complaints, submit self/gift declarations, respond to annual declarations assigned to them.
- **Admin / Compliance Team** – Can view all requests, assign requests to specific admins, respond to queries/complaints, initiate annual declaration cycles, export data, and manage schemas.

**Key Capabilities:**

- KPI dashboard tiles: Total Due to Respond, Total Overdue to Respond, counts by type (Annual Declarations, Self Declarations, Queries, Complaints).
- Due / Overdue logic driven by configurable SLA per request type.
- Similar-request lookup based on request type and title for complaints.
- XLSX export of filtered grid data; for annual cycles, full per-year detail export.
- Email notifications via **Azure Communication Service** with deep links to the specific request.
- File attachments stored in **Azure Blob Storage** using SAS URLs.
- Discussion thread on each request for admin-user back-and-forth communication.

**Pages:**

- **Compliance HelpDesk** – Accessible by both employees and admins. Employees see their own records; admins see all records.
- **Annual Declarations (Admin)** – Admin-only page to initiate and manage annual declaration cycles.

---

## 2. MAIN MODULE COMPONENTS

### 2.1 Requests

A single unified table holds all 5 request types: Query, Complaint, Self Declaration, Gift Declaration, and Annual Declaration.

- Each request has a `request_type` and optional `sub_type` enum.
- Identified by a `display_id` in format `<Staff ID>-<Sr. No>` for **all** request types. Example: `259039-0001`. Serial number is auto-incremented per employee.
- Tracks `overall_status` (NOT_STARTED, IN_PROGRESS, COMPLETED, CLOSED) and `response_status` (DUE, OVERDUE, NOT_REQUIRED).
- Supports two tabs: **Due to Respond** (items where current user/admin must act) and **All** (completed/closed items).

### 2.2 Responses & Discussion Thread

- Each request has a chronological discussion thread where admins and users exchange messages.
- Each response can have file attachments (images, documents).
- Responses are authored by either USER or ADMIN role with timestamp.

### 2.3 Assignments

- Each request supports a single admin assignee at a time.
- Admin can assign any request to a specific compliance team member via a dedicated button on each record.
- Assignment history is tracked for audit purposes (who assigned, when, previous assignee).

### 2.4 Files

- Attachments are stored per-request (at creation) and per-response (in discussion thread).
- Files stored in Azure Blob Storage; only SAS URLs persisted in database.
- **Allowed file formats**: PDF, DOC, DOCX, XLS, XLSX, JPG, JPEG, PNG.
- **Max file size**: 10 MB per file (same as Orchestration → Add Document).
- **Max files per request**: 6 files.

### 2.5 Annual Declaration Cycles & Schemas

- Admin opens a yearly cycle for a given sub-type (COBCE_COI or R5_18).
- Opening a cycle bulk-creates one request per active employee with `display_id` = `<Staff ID>-<Sr. No>` (same format as all other requests).
- Each cycle locks the schema version it uses; viewing historical records always renders against the locked schema.
- **COBCE/COI** annual declaration: Simple Yes/No declaration with optional details field.
- **R5.18** annual declaration: Structured form with admin-defined fields; format may change year-to-year but past years preserve their respective format.
- Per-year detail download in XLSX for all items using the preserved schema of that year.
- If an employee has nothing to declare, the request auto-completes and moves to the All tab.

### 2.6 Self Declaration

- **Declaration Type** (mandatory radio button): COBCE, COI, or Others.
- **Yes/No questions**: All compliance questions rendered as mandatory Yes/No radio buttons. Must be answered before submission.
- **Violation table** (for COBCE type): Multi-row structured data — each row has serial number, brief description of violation, and person responsible. Rows can be added/removed dynamically.
- Can be filed on behalf of another person (e.g., reporting someone else's violation).
- Supports **Save as Draft** and **Submit** actions.

### 2.7 Gift Declaration Details

- **Gift Declaration ID**: Auto-generated on successful submission (format: `<Staff ID>-<Sr. No>`).
- **Title**: Plain text, required.
- **Description**: Plain text, max 500 words.
- **Status** (radio button, required): To be given, Already given, To be received, Already received.
- **From/To Person**: Person name (text field).
- **From/To Organization**: Organization name (text field).
- **Approx. Value (INR)**: Numeric field for approximate monetary value.
- **Ringi Approval Taken** (radio button): Yes / No.
- **Ringi Number**: Text field, required if Ringi Approval = Yes.
- **Upload Supporting Documents**: With hint text "(Ringi copy, Ringi attachments, Gift photo etc.)".
- **Confirmation dialogue** on submit: "Do you want to submit &lt;Gift title&gt;?"
- **Success popup**: "&lt;Gift ID&gt; submitted successfully".

### 2.8 Notifications

- Email sent via **Azure Communication Service** on the following events:
  - Request created (Query/Complaint/Self/Gift Declaration) → email to **all admins** and to **assigning admins** for assignment, with direct link to the compliance helpdesk page.
  - Request assigned → email to assigned admin with deep link.
  - Response posted → email to the other party (admin→user or user→admin) with deep link.
  - Request became overdue → email to assignee and creator with deep link.
- Each email contains a direct link URL to the compliance helpdesk page / specific request.

### 2.9 Similar Requests

- When viewing a complaint, the system suggests similar existing requests.
- Matching logic: same `request_type` + fuzzy/keyword match on `title`.
- Displayed in an expandable "Look for Similar Request" section on the request detail page.

### 2.10 Summary / KPIs

- Dashboard tiles providing at-a-glance metrics:
  - **Total Due to Respond** – requests awaiting response within SLA.
  - **Total Overdue to Respond** – requests past their response due date.
  - **Annual Declarations** – count of active annual declaration requests.
  - **Self Declarations** – count of self declaration requests.
  - **Queries** – count of query requests.
  - **Complaints** – count of complaint requests.
- Scoped by role: employees see only their own counts; admins see global counts.

### 2.11 Export & Filters

- **Export**: Download current filtered grid as XLSX. For annual cycles, export all items with the preserved year-specific schema.
- **Filters**: request_type, sub_type, response_status, overall_status, assignee, created_by, date ranges (created, due), free-text search on title.

---

## 3. API LIST – COMPLIANCE HELPDESK

### 3.1 Request APIs

| Function | API | Method | Role / Purpose |
|----------|-----|--------|----------------|
| Create Request | `/api/compliance/requests/` | POST | Create a new Query, Complaint, Self Declaration, or Gift Declaration. Supports `on_behalf_of_employee_id` for filing on behalf of another person. Triggers email notification to all admins. Returns the created request with generated `display_id`. |
| List Requests | `/api/compliance/requests/` | GET | Paginated list of requests. Employees see only their own; admins see all. Supports filters: `request_type`, `sub_type`, `response_status`, `overall_status`, `assignee_id`, `created_by`, `subject_employee_id`, `created_from`, `created_to`, `due_from`, `due_to`, `tab` (due_to_respond / all), `q` (text search). |
| Get Request Detail | `/api/compliance/requests/{id}` | GET | Full detail of a single request including discussion thread, files, assignment info, and similar-request suggestions. |
| Assign Request | `/api/compliance/requests/{id}/assign` | PATCH | Admin-only. Assigns a single admin to the request. Sends email notification to the assignee with deep link. Unassigns previous assignee if any. |
| Post Response | `/api/compliance/requests/{id}/responses` | POST | Add a reply to the discussion thread. Supports file attachments. Author role (USER/ADMIN) is determined from the authenticated user. Sends email to the other party. |
| Update Status | `/api/compliance/requests/{id}/status` | PATCH | Admin-only. Transition the request status: close, reopen, or mark complete. Validates allowed transitions. |
| Nothing to Declare | `/api/compliance/requests/{id}/nothing-to-declare` | POST | Annual declaration only. Employee confirms they have nothing to declare. Auto-sets `overall_status` = COMPLETED and moves request to the All tab. |
| Get Similar Requests | `/api/compliance/requests/{id}/similar` | GET | Returns a list of similar requests based on `request_type` and fuzzy match on `title`. Used for the "Look for Similar Request" section. |
| Export Requests | `/api/compliance/requests/export` | GET | Export current filtered request list as XLSX. Applies same filters as the List API. For annual declarations, uses the preserved year-specific schema for column headers. |

---

### 3.2 Annual Cycle & Schema APIs

| Function | API | Method | Role / Purpose |
|----------|-----|--------|----------------|
| Open Annual Cycle | `/api/compliance/annual-cycles/` | POST | Admin-only. Opens a new annual declaration cycle for a given `year` and `sub_type` (COBCE_COI or R5_18). Bulk-creates one request per active employee with `display_id` = `<staff_id>-<sr_no>`. Locks the associated schema. |
| List Annual Cycles | `/api/compliance/annual-cycles/` | GET | List all cycles with status, year, sub_type, completion percentage. |
| Get Annual Cycle | `/api/compliance/annual-cycles/{cycle_id}` | GET | Detail of a specific cycle including status, progress stats, and associated schema. |
| Close Annual Cycle | `/api/compliance/annual-cycles/{cycle_id}/close` | PATCH | Admin-only. Closes an open cycle. Validates all requests are in a terminal state (COMPLETED or CLOSED). |
| Export Annual Cycle | `/api/compliance/annual-cycles/{cycle_id}/export` | GET | Export all requests in this cycle as XLSX using the preserved schema of that year. Includes all employee responses and declaration data. |
| Create/Update Schema | `/api/compliance/annual-schemas/` | POST | Admin-only. Define or update the form schema for a given `year` and `sub_type`. Schema becomes immutable once a cycle uses it. |
| Get Schema | `/api/compliance/annual-schemas/` | GET | Retrieve schema by `year` and `sub_type`. Used to render the declaration form for the current or historical year. |
| List Schema History | `/api/compliance/annual-schemas/history` | GET | List all schema versions for a given `sub_type` across years. Used to show format evolution and for historical exports. |

---

### 3.3 Summary API

| Function | API | Method | Role / Purpose |
|----------|-----|--------|----------------|
| Get KPI Summary | `/api/compliance/summary` | GET | Returns KPI tile data: Total Due to Respond, Total Overdue to Respond, Annual Declarations count, Self Declarations count, Gift Declarations count, Queries count, Complaints count. Scoped by role — employees see their own metrics, admins see global. |

---

### 3.4 Reference APIs

| Function | API | Method | Role / Purpose |
|----------|-----|--------|----------------|
| List Request Types | `/api/reference/compliance/request-types` | GET | Returns all valid request types: QUERY, COMPLAINT, SELF_DECLARATION, GIFT_DECLARATION, ANNUAL_DECLARATION. |
| List Sub-Types | `/api/reference/compliance/sub-types` | GET | Returns valid sub-types filtered by `request_type`. E.g., for COMPLAINT: COBCE, COI, OTHERS. |
| List Gift Statuses | `/api/reference/compliance/gift-statuses` | GET | Returns gift status options: TO_BE_GIVEN, ALREADY_GIVEN, TO_BE_RECEIVED, ALREADY_RECEIVED. |
| List Assignable Admins | `/api/reference/compliance/assignable-admins` | GET | Returns list of admin users who can be assigned to requests. |

---

### 3.5 SLA Configuration APIs

| Function | API | Method | Role / Purpose |
|----------|-----|--------|----------------|
| Get SLA Config | `/api/compliance/sla-config` | GET | Returns current SLA (response due days) configuration per request type. |
| Update SLA Config | `/api/compliance/sla-config` | PATCH | Admin-only. Update the number of days allowed for response per request type. |

---

## 4. ORCHESTRATION FLOWS

### 4.1 Employee Raises a Query

1. Employee clicks **"+ Raise a Query"** button on the Compliance HelpDesk page.
2. Query form opens with the following fields:
   - **Sub-Type** (radio button, required): COBCE, COI, ComplyShield, Gift, R5.18, Other.
   - **Title**: Plain text, required.
   - **Description**: Text box (scrollable), max 500 words.
   - **Upload Supporting Documents**: Drag & drop or browse. Allowed: PDF, DOC, DOCX, XLS, XLSX, JPG, JPEG, PNG. Max 10 MB per file.
3. **Clear Form** button resets all text, attachments, and radio buttons.
4. On **Submit Query**:
   - Validates all required fields are filled.
   - If validation fails → inline error messages, submission blocked.
   - If valid → backend creates the request with `request_type` = QUERY, selected `sub_type`, `overall_status` = IN_PROGRESS, `response_status` = DUE, and calculates `response_due_date` from SLA config.
   - Generates `display_id` = `<Staff ID>-<Sr. No>` (e.g., `259039-0001`).
   - Success → popup: **"Query Submitted Successfully!"**
   - Failure → popup: **"Query failed to submit"**
5. Email notification sent via Azure Communication Service to **all admins** and to assigning admins for assignment, with direct link to the compliance helpdesk page.
6. Request appears in the admin's **Due to Respond** tab awaiting assignment.

---

### 4.2 Employee Raises a Complaint

1. Employee clicks **"+ Raise a Complaint"** button on the Compliance HelpDesk page.
2. Complaint form opens with the following fields:
   - **Complaint Type** (radio button, required): COBCE, COI.
   - **Complaint Details**: Text box (scrollable), max 500 words.
   - **Upload Supporting Documents**: Drag & drop or browse. Allowed: PDF, DOC, DOCX, XLS, XLSX, JPG, JPEG, PNG. Max 10 MB per file.
3. **Clear Form** button resets all text, attachments, and radio buttons.
4. On **Submit Complaint**:
   - Validates all required fields are filled.
   - If validation fails → inline error messages, submission blocked.
   - If valid → backend creates the request with `request_type` = COMPLAINT, selected `sub_type`, `overall_status` = IN_PROGRESS, `response_status` = DUE, and calculates `response_due_date` from SLA config.
   - Generates `display_id` = `<Staff ID>-<Sr. No>`.
   - Success → popup: **"Complaint Submitted Successfully!"**
   - Failure → popup: **"Complaint failed to submit"**
5. Email notification sent via Azure Communication Service to **all admins** and to assigning admins for assignment, with direct link to the compliance helpdesk page.
6. Similar-request suggestions are precomputed and available on the detail page.

---

### 4.3 Admin Assigns a Request

1. Admin views an unassigned request and clicks the **"Respond"** / assign button.
2. Admin selects an assignee from the list of compliance team members.
3. Backend sets `assignee_admin_id`, creates an assignment audit record, and sends email to the assignee.
4. Request now appears in the assignee's personal **Due to Respond** queue.

---

### 4.4 Discussion Thread (Query / Complaint Resolution)

1. Assigned admin posts a response with optional attachments.
2. Employee receives email notification and can view + reply via the HelpDesk.
3. Admin and employee exchange messages until resolution.
4. Admin marks the request as COMPLETED or CLOSED via the status update API.
5. Completed requests move from **Due to Respond** tab to the **All** tab.
6. If `response_due_date` passes without admin response, `response_status` transitions to OVERDUE (via scheduled job or on-read check) and overdue email is triggered.

---

### 4.5 Self Declaration Submission

1. Employee clicks **"+ Self Declaration"** button on the Compliance HelpDesk page.
2. Self Declaration form opens with the following fields:
   - **Declaration Type** (radio button, mandatory): COBCE, COI, Others.
   - **Yes/No Questions**: All compliance questions rendered as mandatory Yes/No radio buttons (must all be answered before submission).
   - **Violation Table** (for COBCE type): Rows with S.No, Brief description of violation, Person Responsible. Add (+) / Remove (🗑) row actions.
   - Optionally filed on behalf of another employee using `on_behalf_of_employee_id`.
3. Form validation:
   - All radio buttons (Declaration Type + Yes/No questions) must be selected.
   - If mandatory fields are not filled → Submit button disabled with inline validation messages.
   - If form fails to load → error state displayed, user cannot proceed.
4. **Save as Draft** → creates request with `overall_status` = NOT_STARTED (no email triggered).
5. On **Submit**:
   - Generates `display_id` = `<Staff ID>-<Sr. No>`.
   - Creates request with `overall_status` = IN_PROGRESS, `response_status` = DUE.
   - Email notification sent to all admins and assigning admins with direct link to compliance helpdesk.
   - Request enters standard assign → discuss → resolve flow.
6. Only one instance of the Self Declaration form can be open at a time (prevents duplicate submissions from multiple clicks).

---

### 4.6 Gift Declaration Submission

1. Employee clicks **"+ Gift Declaration"** button on the Compliance HelpDesk page.
2. Gift Declaration form opens (title: "Gift Declaration") with the following fields:
   - **Gift Declaration ID**: Auto-populated on successful submission (read-only placeholder shown).
   - **Title**: Plain text, required.
   - **Description**: Text box (scrollable), max 500 words.
   - **Status** (radio button, required): To be given, Already given, To be received, Already received.
   - **From/To (Person Name)**: Text field.
   - **From/To (Organization Name)**: Text field.
   - **Approx. Value (INR)**: Numeric field.
   - **Ringi Approval Taken** (radio button): Yes / No.
   - **Ringi Number**: Text field (required if Ringi Approval = Yes).
   - **Upload Supporting Documents**: Drag & drop or browse, with hint text "(Ringi copy, Ringi attachments, Gift photo etc.)". Allowed: PDF, DOC, DOCX, XLS, XLSX, JPG, JPEG, PNG. Max 10 MB per file.
3. **Clear Form** button resets all text, attachments, and radio buttons.
4. On **Submit Declaration**:
   - Validates mandatory fields (Title, Description) are filled.
   - If attachment upload fails or unsupported format/size → error shown, submission blocked.
   - If valid → opens **confirmation dialogue**: "Do you want to submit &lt;Gift title&gt;?"
   - On confirm → backend creates request with `request_type` = GIFT_DECLARATION, stores fields in `gift_details` JSONB.
   - Generates `display_id` = `<Staff ID>-<Sr. No>`.
   - Success → popup: **"&lt;Gift ID&gt; submitted successfully"**
   - Failure → popup with error message.
5. Email notification sent via Azure Communication Service to all admins and assigning admins with direct link to compliance helpdesk.
6. Request enters standard assign → discuss → resolve flow.

---

### 4.7 Annual Declaration Cycle

1. Admin navigates to the **Annual Declarations** page and initiates a new cycle for a given year and sub-type (COBCE_COI or R5_18).
2. Backend validates no open cycle exists for that year + sub_type combination.
3. Backend locks the associated schema (marks it immutable).
4. Backend bulk-creates one request per active employee:
   - `display_id` = `<Staff ID>-<Sr. No>` (serial within that employee's requests, e.g., `259039-0005`)
   - `request_type` = ANNUAL_DECLARATION
   - `sub_type` = COBCE_COI or R5_18
   - `overall_status` = NOT_STARTED
   - `response_status` = DUE
   - `response_due_date` calculated from SLA config for annual declarations
5. Employees see their annual declaration request in the **Due to Respond** tab.

---

### 4.8 Employee Responds to Annual Declaration

**Path A – Nothing to Declare:**
1. Employee opens their annual declaration and clicks "Nothing to Declare".
2. Backend sets `nothing_to_declare` = true, `overall_status` = COMPLETED, `response_status` = NOT_REQUIRED.
3. Request moves to the **All** tab.

**Path B – Has Something to Declare:**
1. Employee fills in the declaration form (rendered using the locked schema for that cycle).
   - **COBCE/COI**: Simple Yes/No with optional details text.
   - **R5.18**: Structured form fields as defined by the admin schema for that year.
2. Submits the declaration; data stored in `annual_payload` JSONB.
3. Admin reviews and may respond via the discussion thread.
4. Once resolved, admin marks as COMPLETED.

---

### 4.9 R5.18 Schema Preservation & Historical Access

1. Each year, admin defines the R5.18 form schema (field names, types, validations).
2. When a cycle opens, the schema is snapshot-locked to that cycle.
3. Viewing a past year's declaration always renders using the schema from that year, even if the current year's schema has changed.
4. Export for a specific cycle uses the locked schema as column headers, preserving data integrity across format changes.

---

### 4.10 Email Notifications via Azure Communication Service

| Event | Recipients | Content |
|-------|-----------|---------|
| Request Created (Query/Complaint/Self/Gift) | All admins + assigning admins | "New [type] raised by [employee]. Click here to view." + deep link to helpdesk |
| Request Assigned | Assigned admin | "You have been assigned to [request_id]. Click here to respond." + deep link |
| Response Posted (by admin) | Request creator | "Compliance team responded to your [type]. Click here to view." + deep link |
| Response Posted (by user) | Assigned admin | "[Employee] replied to [request_id]. Click here to view." + deep link |
| Request Overdue | Assigned admin + creator | "[request_id] is now overdue. Click here to take action." + deep link |
| Annual Cycle Opened | All affected employees | "Annual Declaration for [year] [sub_type] is now open. Click here to complete." + deep link |

---

### 4.11 Export & Similar Request Lookup

**Export:**
1. User/Admin applies filters on the HelpDesk grid.
2. Clicks **Export** → backend generates XLSX with all matching records.
3. For annual cycle exports, columns match the locked schema for that year.

**Similar Request Lookup:**
1. On request detail page (primarily for complaints), system displays "Look for Similar Request" section.
2. Backend queries requests with same `request_type` and performs keyword/fuzzy matching on `title`.
3. Results shown as a collapsible list with request ID, title, status, and creation date.

---

### 4.12 Overdue Detection

- A scheduled background job (or on-read evaluation) checks all requests where `response_status` = DUE and `response_due_date` < current date.
- Transitions `response_status` to OVERDUE.
- Triggers overdue email notification.
- KPI tile counts update accordingly.

---

## 5. DB SCHEMA – COMPLIANCE HELPDESK

All tables prefixed with `compliance_`. Using PostgreSQL with JSONB support.

### 5.1 compliance_requests

| Column | Type / Notes |
|--------|--------------|
| id | UUID, PK, default gen_random_uuid() |
| display_id | String(50), unique, not null. Format: `<Staff ID>-<Sr. No>` for all request types. Example: `259039-0001`. Auto-incremented per employee |
| request_type | Enum: QUERY, COMPLAINT, SELF_DECLARATION, GIFT_DECLARATION, ANNUAL_DECLARATION |
| sub_type | Enum: NONE, COBCE, COI, COMPLYSHIELD, GIFT, R5_18, OTHERS, COBCE_COI. Nullable for types that don't require it |
| title | String(500), nullable (not required for annual declarations) |
| description | Text, nullable |
| created_by_employee_id | UUID, FK employees(id), not null |
| subject_employee_id | UUID, FK employees(id), not null. Equals creator unless filed on behalf of another |
| assignee_admin_id | UUID, FK employees(id), nullable. Currently assigned admin |
| overall_status | Enum: NOT_STARTED, IN_PROGRESS, COMPLETED, CLOSED. Default NOT_STARTED |
| response_status | Enum: DUE, OVERDUE, NOT_REQUIRED. Default DUE |
| response_due_date | Timestamp with time zone, nullable. Calculated from SLA config at creation |
| annual_cycle_id | UUID, FK compliance_annual_cycles(id), nullable. Set only for ANNUAL_DECLARATION |
| annual_schema_id | UUID, FK compliance_annual_schemas(id), nullable. Locked schema used for this declaration |
| annual_payload | JSONB, nullable. Employee's declaration data conforming to the locked schema |
| nothing_to_declare | Boolean, default false. Only applicable to ANNUAL_DECLARATION |
| gift_details | JSONB, nullable. Structure: `{ "status": "TO_BE_GIVEN"|"ALREADY_GIVEN"|"TO_BE_RECEIVED"|"ALREADY_RECEIVED", "from_to_person": string, "from_to_org": string, "approx_value_inr": decimal, "ringi_approval_taken": boolean, "ringi_number": string|null }` |
| declaration_type | Enum: COBCE, COI, OTHERS, nullable. For Self Declarations radio button selection |
| yes_no_answers | JSONB, nullable. Key-value pairs of mandatory Yes/No compliance questions. Only for SELF_DECLARATION |
| created_at | Timestamp with time zone, default now() |
| updated_at | Timestamp with time zone, default now() |
| completed_at | Timestamp with time zone, nullable |

---

### 5.2 compliance_self_declaration_items

| Column | Type / Notes |
|--------|--------------|
| id | UUID, PK, default gen_random_uuid() |
| request_id | UUID, FK compliance_requests(id), ON DELETE CASCADE |
| sort_order | Integer, not null. Sequential row number (1, 2, 3…) |
| nature_of_violation | Text, not null. Brief description of the violation |
| person_responsible | String(255), not null. Name of the person responsible |
| created_at | Timestamp with time zone, default now() |

---

### 5.3 compliance_request_files

| Column | Type / Notes |
|--------|--------------|
| id | UUID, PK, default gen_random_uuid() |
| request_id | UUID, FK compliance_requests(id), ON DELETE CASCADE |
| file_url | String(1000), not null. Azure Blob SAS URL |
| original_filename | String(255), not null |
| file_size_bytes | BigInteger, not null |
| file_type | Enum: IMAGE, DOCUMENT |
| sort_order | Integer, default 0 |
| uploaded_by | UUID, FK employees(id), not null |
| created_at | Timestamp with time zone, default now() |

---

### 5.4 compliance_request_responses

| Column | Type / Notes |
|--------|--------------|
| id | UUID, PK, default gen_random_uuid() |
| request_id | UUID, FK compliance_requests(id), ON DELETE CASCADE |
| author_employee_id | UUID, FK employees(id), not null |
| author_role | Enum: USER, ADMIN |
| body | Text, not null. Response message content |
| created_at | Timestamp with time zone, default now() |

---

### 5.5 compliance_response_files

| Column | Type / Notes |
|--------|--------------|
| id | UUID, PK, default gen_random_uuid() |
| response_id | UUID, FK compliance_request_responses(id), ON DELETE CASCADE |
| file_url | String(1000), not null. Azure Blob SAS URL |
| original_filename | String(255), not null |
| file_size_bytes | BigInteger, not null |
| file_type | Enum: IMAGE, DOCUMENT |
| sort_order | Integer, default 0 |
| created_at | Timestamp with time zone, default now() |

---

### 5.6 compliance_request_assignments

| Column | Type / Notes |
|--------|--------------|
| id | UUID, PK, default gen_random_uuid() |
| request_id | UUID, FK compliance_requests(id), ON DELETE CASCADE |
| assigned_to_admin_id | UUID, FK employees(id), not null |
| assigned_by_admin_id | UUID, FK employees(id), not null |
| assigned_at | Timestamp with time zone, default now() |
| unassigned_at | Timestamp with time zone, nullable. Set when a new assignee replaces this one |

---

### 5.7 compliance_annual_cycles

| Column | Type / Notes |
|--------|--------------|
| id | UUID, PK, default gen_random_uuid() |
| year | Integer, not null (e.g., 2026) |
| sub_type | Enum: COBCE_COI, R5_18 |
| schema_id | UUID, FK compliance_annual_schemas(id), not null. Snapshotted/locked schema |
| opened_by_admin_id | UUID, FK employees(id), not null |
| opened_at | Timestamp with time zone, default now() |
| closed_at | Timestamp with time zone, nullable |
| status | Enum: OPEN, CLOSED. Default OPEN |
| total_employees | Integer, not null. Count of employees when cycle opened |
| completed_count | Integer, default 0. Denormalized for quick progress display |
| UNIQUE | (year, sub_type) |

---

### 5.8 compliance_annual_schemas

| Column | Type / Notes |
|--------|--------------|
| id | UUID, PK, default gen_random_uuid() |
| year | Integer, not null |
| sub_type | Enum: COBCE_COI, R5_18 |
| schema_json | JSONB, not null. Array of field definitions: `[{ "name": string, "label": string, "type": "text"|"number"|"date"|"boolean"|"select"|"file", "required": boolean, "options": [] }]` |
| created_by_admin_id | UUID, FK employees(id), not null |
| created_at | Timestamp with time zone, default now() |
| updated_at | Timestamp with time zone, default now() |
| locked | Boolean, default false. Becomes true once a cycle uses this schema; no further edits allowed |
| UNIQUE | (year, sub_type) |

---

### 5.9 compliance_sla_config

| Column | Type / Notes |
|--------|--------------|
| id | UUID, PK, default gen_random_uuid() |
| request_type | Enum: QUERY, COMPLAINT, SELF_DECLARATION, GIFT_DECLARATION, ANNUAL_DECLARATION. Unique |
| response_due_days | Integer, not null. Number of days from creation to calculate response_due_date |
| updated_by | UUID, FK employees(id), not null |
| updated_at | Timestamp with time zone, default now() |

---

### 5.10 compliance_notifications

| Column | Type / Notes |
|--------|--------------|
| id | UUID, PK, default gen_random_uuid() |
| request_id | UUID, FK compliance_requests(id), ON DELETE CASCADE |
| event_type | Enum: CREATED, ASSIGNED, RESPONSE_POSTED, OVERDUE, CYCLE_OPENED |
| recipient_employee_id | UUID, FK employees(id), not null |
| email_sent | Boolean, default false |
| email_sent_at | Timestamp with time zone, nullable |
| deep_link_url | String(1000), not null |
| created_at | Timestamp with time zone, default now() |

---

### 5.11 compliance_request_counters

| Column | Type / Notes |
|--------|--------------|
| id | UUID, PK, default gen_random_uuid() |
| employee_id | UUID, FK employees(id), not null |
| last_value | Integer, not null, default 0 |
| UNIQUE | (employee_id) |

Used for atomic `display_id` generation:
- All request types use the format `<Staff ID>-<Sr. No>` (e.g., `259039-0001`).
- Counter increments per employee across all request types.
- On each new request, atomically increment `last_value` and format as zero-padded 4-digit number.

---

### 5.12 Indexes & Constraints

**Indexes:**
- Composite index on `compliance_requests(request_type, sub_type, overall_status, response_status)` — powers KPI queries and filtered listing.
- Index on `compliance_requests(assignee_admin_id, response_status)` — powers the "Due to Respond" tab for admins.
- Index on `compliance_requests(created_by_employee_id, overall_status)` — powers employee's own request listing.
- Index on `compliance_requests(annual_cycle_id)` — powers cycle-level queries and exports.
- Index on `compliance_requests(response_due_date)` — powers overdue detection job.
- GIN index on `compliance_requests.annual_payload` — enables ad-hoc search within R5.18 declaration data.
- GIN index on `compliance_requests.gift_details` — enables filtering on gift-specific attributes.
- Index on `compliance_request_responses(request_id, created_at)` — powers chronological thread loading.

**Check Constraints:**
- `nothing_to_declare = true` ⇒ `annual_payload IS NULL AND overall_status = 'COMPLETED'`
- `request_type = 'ANNUAL_DECLARATION'` ⇒ `annual_cycle_id IS NOT NULL`
- `request_type = 'GIFT_DECLARATION'` ⇒ `gift_details IS NOT NULL`
- `request_type = 'SELF_DECLARATION'` ⇒ at least one row in `compliance_self_declaration_items` (enforced at application level)
- `locked = true` on schema ⇒ no UPDATE allowed (enforced via trigger or application logic)

---

## 6. ENUMS REFERENCE

```
RequestType: QUERY | COMPLAINT | SELF_DECLARATION | GIFT_DECLARATION | ANNUAL_DECLARATION

SubType: NONE | COBCE | COI | COMPLYSHIELD | GIFT | R5_18 | OTHERS | COBCE_COI

OverallStatus: NOT_STARTED | IN_PROGRESS | COMPLETED | CLOSED

ResponseStatus: DUE | OVERDUE | NOT_REQUIRED

GiftStatus: TO_BE_GIVEN | ALREADY_GIVEN | TO_BE_RECEIVED | ALREADY_RECEIVED

AuthorRole: USER | ADMIN

FileType: IMAGE | DOCUMENT

CycleStatus: OPEN | CLOSED

DisplayIdFormat: <Staff ID>-<Sr. No> (e.g., 259039-0001)

NotificationEvent: CREATED | ASSIGNED | RESPONSE_POSTED | OVERDUE | CYCLE_OPENED

DeclarationType: COBCE | COI | OTHERS
```

---

## 7. VALIDATION RULES & FILE RESTRICTIONS

### 7.1 Text Field Limits

| Field | Max Length |
|-------|-----------|
| Query – Description | 500 words |
| Complaint – Details | 500 words |
| Gift Declaration – Description | 500 words |
| Self Declaration – Nature of Violation | 500 words |
| Response Thread – Body | 500 words |
| Title (Query, Gift) | 255 characters |

### 7.2 File Upload Restrictions

Same as Orchestration → Add Document, plus .xls/.xlsx support:

| Rule | Value |
|------|-------|
| Allowed formats | PDF, DOC, DOCX, XLS, XLSX, JPG, JPEG, PNG |
| Max file size | 10 MB per file |
| Max files per request | 6 |
| Max files per response | 6 |

### 7.3 Required Fields by Request Type

| Request Type | Required Fields |
|--------------|----------------|
| Query | Sub-type (radio), Title, Description |
| Complaint | Complaint Type (radio: COBCE/COI), Complaint Details |
| Self Declaration | Declaration Type (radio), All Yes/No questions answered |
| Gift Declaration | Title, Description, Status (radio) |
| Annual Declaration | Nothing-to-declare OR annual_payload filled per schema |

### 7.4 Sub-Type Radio Options by Request Type

| Request Type | Radio Options |
|--------------|--------------|
| Query | COBCE, COI, ComplyShield, Gift, R5.18, Other |
| Complaint | COBCE, COI |
| Self Declaration | COBCE, COI, Others |
| Gift Declaration | N/A (no sub-type radio; has its own Status radio) |
| Annual Declaration | COBCE_COI, R5_18 (set by cycle, not user-selected) |

---

## 8. STATUS TRANSITION RULES

### 8.1 Overall Status Transitions

```
NOT_STARTED → IN_PROGRESS    (on first response or form submission)
IN_PROGRESS → COMPLETED      (admin marks complete OR nothing-to-declare)
IN_PROGRESS → CLOSED         (admin closes without resolution)
COMPLETED   → IN_PROGRESS    (admin reopens if needed)
CLOSED      → IN_PROGRESS    (admin reopens if needed)
```

### 8.2 Response Status Transitions

```
DUE          → OVERDUE        (response_due_date exceeded, automated)
DUE          → NOT_REQUIRED   (nothing-to-declare for annual, or request closed)
OVERDUE      → NOT_REQUIRED   (request completed/closed)
```

### 8.3 Tab Logic

- **Due to Respond tab**: `overall_status IN (NOT_STARTED, IN_PROGRESS) AND response_status IN (DUE, OVERDUE)`
- **All tab**: `overall_status IN (COMPLETED, CLOSED) OR response_status = NOT_REQUIRED`

---

## 9. REQUEST / RESPONSE PAYLOAD EXAMPLES

### 9.1 Create Query Request

```json
{
  "request_type": "QUERY",
  "sub_type": "COBCE",
  "title": "Clarification on gift policy threshold",
  "description": "What is the maximum gift value allowed without ringi approval?",
  "attachments": []
}
```

**Response:**
```json
{
  "message": "Query Submitted Successfully!",
  "status_code": 201,
  "status": "success",
  "data": {
    "id": "uuid",
    "display_id": "259039-0001",
    "request_type": "QUERY",
    "sub_type": "COBCE",
    "overall_status": "IN_PROGRESS",
    "response_status": "DUE",
    "response_due_date": "2026-05-11T00:00:00Z"
  }
}
```

### 9.2 Create Complaint Request

```json
{
  "request_type": "COMPLAINT",
  "sub_type": "COBCE",
  "description": "Details of the observed violation in procurement department...",
  "attachments": ["evidence.pdf"]
}
```

**Response:**
```json
{
  "message": "Complaint Submitted Successfully!",
  "status_code": 201,
  "status": "success",
  "data": {
    "id": "uuid",
    "display_id": "259039-0002",
    "request_type": "COMPLAINT",
    "sub_type": "COBCE",
    "overall_status": "IN_PROGRESS",
    "response_status": "DUE"
  }
}
```

### 9.3 Create Self Declaration

```json
{
  "request_type": "SELF_DECLARATION",
  "declaration_type": "COBCE",
  "on_behalf_of_employee_id": null,
  "yes_no_answers": {
    "question_1": true,
    "question_2": false,
    "question_3": true
  },
  "items": [
    {
      "sort_order": 1,
      "nature_of_violation": "Accepted vendor lunch exceeding policy limit",
      "person_responsible": "John Smith"
    },
    {
      "sort_order": 2,
      "nature_of_violation": "Failed to report conflict of interest in Q3 project",
      "person_responsible": "Jane Doe"
    }
  ],
  "attachments": []
}
```

### 9.4 Create Gift Declaration

```json
{
  "request_type": "GIFT_DECLARATION",
  "title": "Corporate gift from vendor ABC",
  "description": "Received a branded laptop bag during annual conference",
  "gift_details": {
    "status": "ALREADY_RECEIVED",
    "from_to_person": "Mr. Tanaka",
    "from_to_org": "ABC Corporation",
    "approx_value_inr": 5000,
    "ringi_approval_taken": true,
    "ringi_number": "RNG-2026-0042"
  },
  "attachments": ["gift_photo.jpg", "ringi_copy.pdf"]
}
```

**Response:**
```json
{
  "message": "259039-0003 submitted successfully",
  "status_code": 201,
  "status": "success",
  "data": {
    "id": "uuid",
    "display_id": "259039-0003",
    "request_type": "GIFT_DECLARATION",
    "overall_status": "IN_PROGRESS",
    "response_status": "DUE"
  }
}
```

### 9.5 Annual Declaration – Nothing to Declare

```json
POST /api/compliance/requests/{id}/nothing-to-declare
{}
```

### 9.6 Annual Declaration – Submit (COBCE/COI)

```json
PATCH /api/compliance/requests/{id}
{
  "annual_payload": {
    "has_conflict": false,
    "details": ""
  }
}
```

### 9.7 Annual Declaration – Submit (R5.18)

```json
PATCH /api/compliance/requests/{id}
{
  "annual_payload": {
    "field_1_name": "value per schema",
    "field_2_name": "value per schema",
    "uploaded_file": "r518_data.xlsx"
  }
}
```

### 9.8 KPI Summary Response

```json
{
  "message": "Success",
  "status_code": 200,
  "status": "success",
  "data": {
    "total_due_to_respond": 3,
    "total_overdue_to_respond": 4,
    "annual_declarations": 2,
    "self_declarations": 3,
    "gift_declarations": 0,
    "queries": 1,
    "complaints": 1
  }
}
```
