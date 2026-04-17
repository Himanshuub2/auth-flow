"""
Bulk Applicability Service
--------------------------
Handles template generation, file upload + storage, Excel parsing,
and bulk applicability updates for documents and events.
"""

import io
import logging
from datetime import datetime, timezone

from openpyxl import Workbook, load_workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter
from sqlalchemy import func, select, text, update
from sqlalchemy.ext.asyncio import AsyncSession

from models.documents.bulk_applicability import (
    BulkApplicabilityRequest,
    BulkApplicabilityStatus,
)
from models.documents.document import (
    Document,
    DocumentType,
    DOCUMENT_TYPE_LABELS,
    ApplicabilityType as DocApplicabilityType,
)
from models.events.event import (
    Event,
    ApplicabilityType as EventApplicabilityType,
)
from models.events.user import User
from storage import get_storage

logger = logging.getLogger(__name__)

ALLOWED_UPLOAD_EXTENSIONS = frozenset({"xlsx", "csv", "xls"})

FIXED_COLUMNS = ["id", "type", "name", "updated_at"]


# ---------------------------------------------------------------------------
# Template generation
# ---------------------------------------------------------------------------

async def generate_template(
    db: AsyncSession,
    selected_types: list[str],
) -> tuple[io.BytesIO, str]:
    """
    Build an Excel template in memory and return (bytes_buffer, filename).
    No Azure storage -- streamed directly to the client.
    """
    division_columns = await _get_division_columns(db)
    rows: list[dict] = []

    doc_types = [t for t in selected_types if t != "EVENTS"]
    if doc_types:
        doc_rows = await _fetch_document_rows(db, doc_types)
        rows.extend(doc_rows)

    if "EVENTS" in selected_types:
        event_rows = await _fetch_event_rows(db)
        rows.extend(event_rows)

    wb = Workbook()
    ws = wb.active
    ws.title = "Applicability"

    _write_reference_row(ws, division_columns)
    _write_header_row(ws, division_columns)
    _write_data_rows(ws, rows)
    _apply_styles(ws, division_columns, len(rows))

    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)

    type_label = "_".join(t.lower() for t in selected_types[:3])
    if len(selected_types) > 3:
        type_label += f"_and_{len(selected_types) - 3}_more"
    filename = f"bulk_applicability_template_{type_label}.xlsx"

    return buf, filename


async def _get_division_columns(db: AsyncSession) -> list[tuple[str, str]]:
    """
    Returns ordered (organization_vertical, division_cluster) pairs.
    Row 1 uses organization_vertical (reference only), row 2 uses division_cluster headers.
    """
    result = await db.execute(
        select(User.organization_vertical, User.division_cluster)
        .where(User.division_cluster.isnot(None))
        .where(User.division_cluster != "")
        .distinct()
        .order_by(User.organization_vertical, User.division_cluster)
    )
    return [(row[0], row[1]) for row in result.all()]


async def _fetch_document_rows(
    db: AsyncSession, doc_types: list[str]
) -> list[dict]:
    type_enums = [DocumentType(t) for t in doc_types]
    result = await db.execute(
        select(
            Document.id,
            Document.name,
            Document.document_type,
            Document.updated_at,
        )
        .where(Document.document_type.in_(type_enums))
        .order_by(Document.document_type, Document.id)
    )
    rows = []
    for r in result.all():
        rows.append({
            "id": r.id,
            "type": DOCUMENT_TYPE_LABELS.get(r.document_type, r.document_type.value),
            "name": r.name,
            "updated_at": r.updated_at,
        })
    return rows


async def _fetch_event_rows(db: AsyncSession) -> list[dict]:
    result = await db.execute(
        select(
            Event.id,
            Event.event_name,
            Event.updated_at,
        ).order_by(Event.id)
    )
    rows = []
    for r in result.all():
        rows.append({
            "id": r.id,
            "type": "Events",
            "name": r.event_name,
            "updated_at": r.updated_at,
        })
    return rows


def _write_reference_row(
    ws,
    division_columns: list[tuple[str, str]],
) -> None:
    """
    Row 1: organization_vertical reference (user guidance only).
    Fixed columns are left blank on this row.
    """
    for col_idx, (organization_vertical, _division_cluster) in enumerate(
        division_columns, start=len(FIXED_COLUMNS) + 1
    ):
        ws.cell(row=1, column=col_idx, value=organization_vertical)


def _write_header_row(
    ws,
    division_columns: list[tuple[str, str]],
) -> None:
    """Row 2: visible header row."""
    headers = FIXED_COLUMNS + [division_cluster for _vertical, division_cluster in division_columns]
    for col_idx, header in enumerate(headers, start=1):
        ws.cell(row=2, column=col_idx, value=header)


def _write_data_rows(ws, rows: list[dict]) -> None:
    """Row 3+: data rows with fixed columns pre-filled, division columns empty."""
    for row_idx, row_data in enumerate(rows, start=3):
        ws.cell(row=row_idx, column=1, value=row_data["id"])
        ws.cell(row=row_idx, column=2, value=row_data["type"])
        ws.cell(row=row_idx, column=3, value=row_data["name"])
        updated = row_data.get("updated_at")
        if isinstance(updated, datetime):
            ws.cell(row=row_idx, column=4, value=updated.strftime("%d/%m/%Y"))
        else:
            ws.cell(row=row_idx, column=4, value=str(updated) if updated else "")


def _apply_styles(
    ws,
    division_columns: list[tuple[str, str]],
    data_row_count: int,
) -> None:
    header_font = Font(bold=True, size=11)
    header_fill = PatternFill(start_color="D9E1F2", end_color="D9E1F2", fill_type="solid")
    header_alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
    total_cols = len(FIXED_COLUMNS) + len(division_columns)

    # Row 1 is reference-only; highlight differently.
    reference_fill = PatternFill(start_color="F2F2F2", end_color="F2F2F2", fill_type="solid")
    for col_idx in range(len(FIXED_COLUMNS) + 1, total_cols + 1):
        ref_cell = ws.cell(row=1, column=col_idx)
        ref_cell.font = Font(bold=True, size=10)
        ref_cell.fill = reference_fill
        ref_cell.alignment = header_alignment

    for col_idx in range(1, total_cols + 1):
        cell = ws.cell(row=2, column=col_idx)
        cell.font = header_font
        cell.fill = header_fill
        cell.alignment = header_alignment

    for col_idx in range(1, total_cols + 1):
        col_letter = get_column_letter(col_idx)
        if col_idx <= len(FIXED_COLUMNS):
            ws.column_dimensions[col_letter].width = 20
        else:
            ws.column_dimensions[col_letter].width = 14

    ws.freeze_panes = "A3"
    ws.sheet_properties.tabColor = "1F4E79"
    # Keep the template fully editable so admins can update cells
    # and delete rows as needed.
    ws.protection.sheet = False


# ---------------------------------------------------------------------------
# Upload handling
# ---------------------------------------------------------------------------

async def create_upload_request(
    db: AsyncSession,
    *,
    file_name: str,
    blob_path: str,
    selected_types: list[str],
    change_remarks: str | None,
    user_id: str,
) -> BulkApplicabilityRequest:
    req = BulkApplicabilityRequest(
        file_name=file_name,
        uploaded_file_url=blob_path,
        selected_types=selected_types,
        status=BulkApplicabilityStatus.PENDING,
        change_remarks=change_remarks,
        created_by=user_id,
        updated_by=user_id,
    )
    db.add(req)
    await db.flush()
    return req


# ---------------------------------------------------------------------------
# History
# ---------------------------------------------------------------------------

async def list_history(
    db: AsyncSession,
    page: int = 1,
    page_size: int = 10,
) -> tuple[list[BulkApplicabilityRequest], int]:
    count_q = select(func.count()).select_from(BulkApplicabilityRequest)
    total = (await db.execute(count_q)).scalar_one()

    offset = (page - 1) * page_size
    items_q = (
        select(BulkApplicabilityRequest)
        .order_by(BulkApplicabilityRequest.created_at.desc())
        .offset(offset)
        .limit(page_size)
    )
    result = await db.execute(items_q)
    items = list(result.scalars().all())
    return items, total


# ---------------------------------------------------------------------------
# Processing engine (called by cron or force-start)
# ---------------------------------------------------------------------------

async def process_pending_requests(db: AsyncSession, user_id: str | None = None) -> dict:
    """
    Pick all PENDING requests ordered by created_at and process each.
    Returns summary of processed/failed counts.
    """
    pending_q = (
        select(BulkApplicabilityRequest)
        .where(BulkApplicabilityRequest.status == BulkApplicabilityStatus.PENDING)
        .order_by(BulkApplicabilityRequest.created_at.asc())
    )
    result = await db.execute(pending_q)
    requests = list(result.scalars().all())

    processed = 0
    failed = 0

    for req in requests:
        try:
            await _process_single_request(db, req, user_id)
            processed += 1
        except Exception:
            failed += 1
            logger.exception("Failed to process bulk applicability request %s", req.id)

    return {"processed": processed, "failed": failed, "total": len(requests)}


async def _process_single_request(
    db: AsyncSession,
    req: BulkApplicabilityRequest,
    user_id: str | None = None,
) -> None:
    req.status = BulkApplicabilityStatus.IN_PROGRESS
    if user_id:
        req.updated_by = user_id
    await db.flush()

    try:
        file_bytes = await _download_blob(req.uploaded_file_url)
        parsed_rows = _parse_uploaded_file(file_bytes, req.file_name)
        await _apply_bulk_updates(db, parsed_rows, user_id or req.created_by)

        req.status = BulkApplicabilityStatus.COMPLETED
        req.error_message = None
    except Exception as exc:
        await db.rollback()
        req.status = BulkApplicabilityStatus.FAILED
        req.error_message = str(exc)
        logger.exception(
            "Bulk applicability request %s failed: %s", req.id, exc
        )

    if user_id:
        req.updated_by = user_id
    db.add(req)
    await db.flush()


async def _download_blob(blob_path: str) -> bytes:
    storage = get_storage()
    if getattr(storage, "_bypass", False):
        raise RuntimeError(
            "Azure bypass is enabled; cannot download uploaded file. "
            "Disable BYPASS_AZURE_UPLOAD to process bulk uploads."
        )

    container = await storage._get_container()
    blob_client = container.get_blob_client(blob_path)
    download_stream = await blob_client.download_blob()
    return await download_stream.readall()


def _parse_uploaded_file(file_bytes: bytes, file_name: str) -> list[dict]:
    """
    Parse the uploaded Excel/CSV file and return a list of row dicts.
    Each dict: {id, type, divisions: [list of division names with Y]}
    """
    ext = file_name.rsplit(".", 1)[-1].lower() if "." in file_name else ""

    if ext == "csv":
        return _parse_csv(file_bytes)
    elif ext in ("xlsx", "xls"):
        return _parse_excel(file_bytes)
    else:
        raise ValueError(f"Unsupported file extension: {ext}")


def _parse_csv(file_bytes: bytes) -> list[dict]:
    import csv

    text = file_bytes.decode("utf-8-sig")
    reader = csv.reader(io.StringIO(text))
    all_rows = list(reader)

    if len(all_rows) < 3:
        raise ValueError("CSV must have reference row, header row, and at least one data row")

    reference_row = all_rows[0]
    header_row = all_rows[1]
    data_rows = all_rows[2:]
    return _rows_to_dicts(reference_row, header_row, data_rows)


def _parse_excel(file_bytes: bytes) -> list[dict]:
    wb = load_workbook(io.BytesIO(file_bytes), read_only=True, data_only=True)
    ws = wb.active

    all_rows = []
    for row in ws.iter_rows(values_only=True):
        all_rows.append([str(c) if c is not None else "" for c in row])

    if len(all_rows) < 3:
        raise ValueError("Excel must have reference row, header row, and at least one data row")

    reference_row = all_rows[0]
    header_row = all_rows[1]
    data_rows = all_rows[2:]
    return _rows_to_dicts(reference_row, header_row, data_rows)


def _rows_to_dicts(
    reference_row: list[str],
    header_row: list[str],
    data_rows: list[list[str]],
) -> list[dict]:
    header = [h.strip() for h in header_row]

    id_idx = _find_column(header, "id")
    type_idx = _find_column(header, "type")

    division_indices: list[tuple[int, str, str]] = []
    for i, h in enumerate(header):
        if i > type_idx and h.lower() not in ("name", "updated_at", "id", "type"):
            organization_vertical = reference_row[i].strip() if i < len(reference_row) else ""
            division_indices.append((i, h, organization_vertical))

    if not division_indices:
        raise ValueError("No division columns found in the uploaded file")

    errors: list[str] = []
    parsed: list[dict] = []

    for row_num, row in enumerate(data_rows, start=1):
        if not any(cell.strip() for cell in row):
            continue

        row_id = row[id_idx].strip() if id_idx < len(row) else ""
        row_type = row[type_idx].strip() if type_idx < len(row) else ""

        if not row_id:
            errors.append(f"Row {row_num}: missing 'id'")
            continue

        try:
            int(row_id)
        except ValueError:
            errors.append(f"Row {row_num}: 'id' must be an integer, got '{row_id}'")
            continue

        if not row_type:
            errors.append(f"Row {row_num}: missing 'type'")
            continue

        matched_divisions: set[str] = set()
        for col_idx, division_name, _organization_vertical in division_indices:
            val = row[col_idx].strip().upper() if col_idx < len(row) else ""
            if val in ("Y", "YES"):
                matched_divisions.add(division_name)
            elif val in ("N", "NO", ""):
                pass
            else:
                errors.append(
                    f"Row {row_num}, column '{division_name}': "
                    f"invalid value '{row[col_idx].strip()}'. Expected Y or N."
                )

        parsed.append({
            "id": int(row_id),
            "type": row_type,
            "divisions": sorted(matched_divisions),
            "row_num": row_num,
        })

    if errors:
        raise ValueError("Validation errors:\n" + "\n".join(errors))

    return parsed


def _find_column(header: list[str], name: str) -> int:
    for i, h in enumerate(header):
        if h.lower() == name.lower():
            return i
    raise ValueError(f"Required column '{name}' not found in header: {header}")


# ---------------------------------------------------------------------------
# DB bulk update
# ---------------------------------------------------------------------------

_TYPE_LABEL_TO_DOC_TYPE: dict[str, str] = {}
for dt in DocumentType:
    label = DOCUMENT_TYPE_LABELS.get(dt, dt.value)
    _TYPE_LABEL_TO_DOC_TYPE[label.upper()] = dt.value
    _TYPE_LABEL_TO_DOC_TYPE[dt.value.upper()] = dt.value


def _resolve_type(raw_type: str) -> tuple[str, str]:
    """
    Return (table, enum_value).
    table is 'document' or 'event'.
    """
    upper = raw_type.strip().upper()
    if upper in ("EVENT", "EVENTS"):
        return ("event", "EVENTS")
    resolved = _TYPE_LABEL_TO_DOC_TYPE.get(upper)
    if resolved:
        return ("document", resolved)
    raise ValueError(f"Unknown type '{raw_type}'")


async def _apply_bulk_updates(
    db: AsyncSession,
    rows: list[dict],
    user_id: str,
) -> None:
    """All-or-nothing: validate all IDs exist, then batch UPDATE."""
    doc_updates: list[dict] = []
    event_updates: list[dict] = []

    for row in rows:
        table, _ = _resolve_type(row["type"])
        divisions = row["divisions"]

        if divisions:
            app_type = "DIVISION"
            app_refs = {"divisions": divisions, "designations": []}
        else:
            app_type = "ALL"
            app_refs = None

        entry = {
            "id": row["id"],
            "applicability_type": app_type,
            "applicability_refs": app_refs,
            "row_num": row["row_num"],
        }

        if table == "document":
            doc_updates.append(entry)
        else:
            event_updates.append(entry)

    if doc_updates:
        await _validate_ids_exist(db, Document, [u["id"] for u in doc_updates], "document")
        await _batch_update_documents(db, doc_updates, user_id)

    if event_updates:
        await _validate_ids_exist(db, Event, [u["id"] for u in event_updates], "event")
        await _batch_update_events(db, event_updates, user_id)


async def _validate_ids_exist(
    db: AsyncSession,
    model,
    ids: list[int],
    label: str,
) -> None:
    result = await db.execute(select(model.id).where(model.id.in_(ids)))
    found = {r[0] for r in result.all()}
    missing = set(ids) - found
    if missing:
        raise ValueError(
            f"The following {label} IDs do not exist: {sorted(missing)}"
        )


async def _batch_update_documents(
    db: AsyncSession,
    updates: list[dict],
    user_id: str,
) -> None:
    now = datetime.now(timezone.utc)
    for entry in updates:
        await db.execute(
            update(Document)
            .where(Document.id == entry["id"])
            .values(
                applicability_type=DocApplicabilityType(entry["applicability_type"]),
                applicability_refs=entry["applicability_refs"],
                updated_by=user_id,
                updated_at=now,
            )
        )


async def _batch_update_events(
    db: AsyncSession,
    updates: list[dict],
    user_id: str,
) -> None:
    now = datetime.now(timezone.utc)
    for entry in updates:
        await db.execute(
            update(Event)
            .where(Event.id == entry["id"])
            .values(
                applicability_type=EventApplicabilityType(entry["applicability_type"]),
                applicability_refs=entry["applicability_refs"],
                updated_by=user_id,
                updated_at=now,
            )
        )
