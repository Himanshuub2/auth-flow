"""
Bulk Applicability Service
--------------------------
Handles template generation, file upload + storage, Excel parsing,
and bulk applicability updates for documents and events.
"""

import asyncio
import io
import logging
from pathlib import Path
from datetime import datetime, timezone

from openpyxl import Workbook, load_workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter
from sqlalchemy import bindparam, func, select, text, update
from sqlalchemy.ext.asyncio import AsyncSession

from utils.dates import format_date_dmy_month_abbr
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

logger = logging.getLogger(__name__)

ALLOWED_UPLOAD_EXTENSIONS = frozenset({"xlsx", "csv", "xls"})

FIXED_COLUMNS = ["id", "type", "name", "updated_at"]

# Safety cap so one upload cannot grow unbounded memory in parsed row list.
MAX_BULK_APPLICABILITY_DATA_ROWS = 100_000

# Hard cap on physical data rows scanned (including blank rows) to limit CPU/DoS.
MAX_BULK_APPLICABILITY_SCAN_ROWS = 500_000

# Fewer round-trips than one UPDATE per row; keeps bind parameter batches bounded.
_BULK_UPDATE_CHUNK = 500


def _format_error_for_storage(exc: BaseException) -> str:
    """User-readable text stored on BulkApplicabilityRequest.error_message."""
    if isinstance(exc, ValueError) and "Validation errors" in str(exc):
        return (
            "The uploaded file has invalid or missing data. Ensure header row "
            "includes 'id' and 'type', and each data row has values for 'id' and "
            "'type' (division columns must be Y or N).\n\n"
            f"{exc}"
        )
    if isinstance(exc, ValueError):
        return f"File format or content error:\n{exc}"
    return str(exc)


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




async def get_history_by_id(
    db: AsyncSession,
    request_id: int,
) -> BulkApplicabilityRequest | None:
    result = await db.execute(
        select(BulkApplicabilityRequest).where(BulkApplicabilityRequest.id == request_id)
    )
    return result.scalar_one_or_none()


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
        req_id = req.id
        try:
            await _process_single_request(db, req, user_id)
            processed += 1
        except Exception:
            failed += 1
            await db.rollback()
            logger.exception("Failed to process bulk applicability request %s", req_id)

    return {"processed": processed, "failed": failed, "total": len(requests)}


async def _persist_request_failed(
    db: AsyncSession,
    req_id: int,
    actor: str,
    exc: BaseException,
) -> None:
    """Set FAILED + error_message and commit (caller must not have rolled back the request row)."""
    err_text = _format_error_for_storage(exc)
    await db.execute(
        update(BulkApplicabilityRequest)
        .where(BulkApplicabilityRequest.id == req_id)
        .values(
            status=BulkApplicabilityStatus.FAILED,
            error_message=err_text,
            updated_by=actor,
        )
    )
    await db.flush()
    await db.commit()
    if isinstance(exc, ValueError):
        logger.warning(
            "Bulk applicability request %s failed validation: %s",
            req_id,
            err_text[:500],
        )
    else:
        logger.exception("Bulk applicability request %s failed: %s", req_id, exc)


async def _process_single_request(
    db: AsyncSession,
    req: BulkApplicabilityRequest,
    user_id: str | None = None,
) -> None:
    req_id = req.id
    actor = user_id or req.updated_by or req.created_by
    updater = user_id or req.created_by

    await db.execute(
        update(BulkApplicabilityRequest)
        .where(BulkApplicabilityRequest.id == req_id)
        .values(
            status=BulkApplicabilityStatus.IN_PROGRESS,
            updated_by=actor,
        )
    )
    await db.flush()

    # Parse first. Do NOT session.rollback() here: if upload+process share one HTTP
    # transaction, rollback would undo the new bulk_applicability row so UPDATE … FAILED
    # would match 0 rows.
    try:
        path = _resolve_stored_path(req.uploaded_file_url)
        parsed_rows = await asyncio.to_thread(
            _parse_uploaded_file_from_path, path, req.file_name
        )
    except Exception as exc:
        await _persist_request_failed(db, req_id, actor, exc)
        return

    try:
        await _apply_bulk_updates(db, parsed_rows, updater)
    except Exception as exc:
        # Revert partial document/event updates only.
        await db.rollback()
        await _persist_request_failed(db, req_id, actor, exc)
        return

    await db.execute(
        update(BulkApplicabilityRequest)
        .where(BulkApplicabilityRequest.id == req_id)
        .values(
            status=BulkApplicabilityStatus.COMPLETED,
            error_message=None,
            updated_by=actor,
        )
    )
    await db.flush()
    await db.commit()


def _resolve_stored_path(stored_path: str) -> Path:
    path = Path(stored_path)
    if not path.is_absolute():
        path = Path.cwd() / path
    if not path.exists():
        raise FileNotFoundError(f"Uploaded file not found at path: {path}")
    return path


def _cell_str(value: object) -> str:
    if value is None:
        return ""
    return str(value)


def _prepare_indices(
    reference_row: list[str],
    header_row: list[str],
) -> tuple[int, int, list[tuple[int, str, str]]]:
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
    return id_idx, type_idx, division_indices


def _append_parsed_row(
    row: list[str],
    row_num: int,
    id_idx: int,
    type_idx: int,
    division_indices: list[tuple[int, str, str]],
    errors: list[str],
    parsed: list[dict],
) -> None:
    if not any(cell.strip() for cell in row):
        return

    row_id = row[id_idx].strip() if id_idx < len(row) else ""
    row_type = row[type_idx].strip() if type_idx < len(row) else ""

    if not row_id:
        errors.append(f"Row {row_num}: missing 'id'")
        return

    try:
        int(row_id)
    except ValueError:
        errors.append(f"Row {row_num}: 'id' must be an integer, got '{row_id}'")
        return

    if not row_type:
        errors.append(f"Row {row_num}: missing 'type'")
        return

    matched_divisions: set[str] = set()
    has_any_y_or_n: bool = False
    for col_idx, division_name, _organization_vertical in division_indices:
        val = row[col_idx].strip().upper() if col_idx < len(row) else ""
        if val in ("Y", "YES", "N", "NO"):
            has_any_y_or_n = True
        if val in ("Y", "YES"):
            matched_divisions.add(division_name)
        elif val in ("N", "NO", ""):
            pass
        else:
            errors.append(
                f"Row {row_num}, column '{division_name}': "
                f"invalid value '{row[col_idx].strip()}'. Expected Y or N."
            )

    # No division cell was filled with Y/N: leave this document/event unchanged.
    if not has_any_y_or_n:
        return

    parsed.append({
        "id": int(row_id),
        "type": row_type,
        "divisions": sorted(matched_divisions),
        "row_num": row_num,
    })


def _raise_if_errors(errors: list[str]) -> None:
    if errors:
        lines = "\n".join(errors)
        raise ValueError(
            "Validation errors (fix each row/column, then re-upload):\n" + lines
        )


def _parse_uploaded_file_from_path(path: Path, file_name: str) -> list[dict]:
    """
    Parse upload from disk. CSV and XLSX stream row-by-row (no full-sheet list).
    Legacy .xls reads into memory once (openpyxl does not stream .xls reliably).
    """
    ext = file_name.rsplit(".", 1)[-1].lower() if "." in file_name else ""
    if ext == "csv":
        return _parse_csv_path(path)
    if ext == "xlsx":
        return _parse_excel_path(path)
    if ext == "xls":
        return _parse_excel_from_bytes(path.read_bytes())
    raise ValueError(f"Unsupported file extension: {ext}")


def _parse_csv_path(path: Path) -> list[dict]:
    import csv

    errors: list[str] = []
    parsed: list[dict] = []
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.reader(f)
        try:
            ref = next(reader)
            hdr = next(reader)
        except StopIteration as exc:
            raise ValueError(
                "CSV must have reference row, header row, and at least one data row"
            ) from exc
        reference_row = [str(c) if c is not None else "" for c in ref]
        header_row = [str(c) if c is not None else "" for c in hdr]
        id_idx, type_idx, division_indices = _prepare_indices(reference_row, header_row)
        for row_num, raw in enumerate(reader, start=1):
            if row_num > MAX_BULK_APPLICABILITY_SCAN_ROWS:
                raise ValueError(
                    f"Too many rows in file (max {MAX_BULK_APPLICABILITY_SCAN_ROWS} data rows)."
                )
            row = [str(c) if c is not None else "" for c in raw]
            _append_parsed_row(row, row_num, id_idx, type_idx, division_indices, errors, parsed)
            if len(parsed) > MAX_BULK_APPLICABILITY_DATA_ROWS:
                raise ValueError(
                    f"Too many non-empty data rows (max {MAX_BULK_APPLICABILITY_DATA_ROWS})."
                )
    _raise_if_errors(errors)
    return parsed


def _parse_excel_path(path: Path) -> list[dict]:
    wb = load_workbook(filename=str(path), read_only=True, data_only=True)
    try:
        return _consume_excel_rows(wb.active)
    finally:
        wb.close()


def _parse_excel_from_bytes(file_bytes: bytes) -> list[dict]:
    wb = load_workbook(io.BytesIO(file_bytes), read_only=True, data_only=True)
    try:
        return _consume_excel_rows(wb.active)
    finally:
        wb.close()


def _consume_excel_rows(ws) -> list[dict]:
    it = ws.iter_rows(values_only=True)
    try:
        r0 = next(it)
        r1 = next(it)
    except StopIteration as exc:
        raise ValueError(
            "Excel must have reference row, header row, and at least one data row"
        ) from exc
    reference_row = [_cell_str(c) for c in r0]
    header_row = [_cell_str(c) for c in r1]
    id_idx, type_idx, division_indices = _prepare_indices(reference_row, header_row)
    errors: list[str] = []
    parsed: list[dict] = []
    for row_num, raw in enumerate(it, start=1):
        if row_num > MAX_BULK_APPLICABILITY_SCAN_ROWS:
            raise ValueError(
                f"Too many rows in file (max {MAX_BULK_APPLICABILITY_SCAN_ROWS} data rows)."
            )
        row = [_cell_str(c) for c in raw] if raw else []
        _append_parsed_row(row, row_num, id_idx, type_idx, division_indices, errors, parsed)
        if len(parsed) > MAX_BULK_APPLICABILITY_DATA_ROWS:
            raise ValueError(
                f"Too many non-empty data rows (max {MAX_BULK_APPLICABILITY_DATA_ROWS})."
            )
    _raise_if_errors(errors)
    return parsed


def _find_column(header: list[str], name: str) -> int:
    for i, h in enumerate(header):
        if h.lower() == name.lower():
            return i
    raise ValueError(
        f"Required column '{name}' is missing from row 2 (header row). "
        f"Use the downloaded template; found columns: {header}"
    )



async def _get_division_columns(db: AsyncSession) -> list[tuple[str, str]]:
    """
    Returns ordered (organization_vertical, division_cluster) pairs.
    Row 1 uses organization_vertical (reference only), row 2 uses division_cluster headers.
    """
    if await _has_users_org_vertical_column(db):
        result = await db.execute(
            select(User.organization_vertical, User.division_cluster)
            .where(User.division_cluster.isnot(None))
            .where(User.division_cluster != "")
            .distinct()
            .order_by(User.organization_vertical, User.division_cluster)
        )
        return [(row[0] or "", row[1]) for row in result.all()]

    result = await db.execute(
        select(User.division_cluster)
        .where(User.division_cluster.isnot(None))
        .where(User.division_cluster != "")
        .distinct()
        .order_by(User.division_cluster)
    )
    return [("", row[0]) for row in result.all()]


async def _has_users_org_vertical_column(db: AsyncSession) -> bool:
    q = await db.execute(
        text(
            """
            SELECT 1
            FROM information_schema.columns
            WHERE table_schema = 'users'
              AND table_name = 'users'
              AND column_name = 'organization_vertical'
            LIMIT 1
            """
        )
    )
    return q.first() is not None


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
            ws.cell(row=row_idx, column=4, value=format_date_dmy_month_abbr(updated))
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
    ws.protection.sheet = False


# ---------------------------------------------------------------------------
# Upload handling
# ---------------------------------------------------------------------------


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
    """
    Validate IDs exist, then batch UPDATE.
    Rows only include records where at least one division cell was Y/N; others were skipped at parse time.
    """
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
    # Core Table update (not ORM entity) so executemany + bindparam works without
    # SQLAlchemy's "bulk UPDATE by primary key" parameter naming rules.
    tbl = Document.__table__
    now = datetime.now(timezone.utc)
    stmt = (
        update(tbl)
        .where(tbl.c.id == bindparam("doc_id"))
        .values(
            applicability_type=bindparam("app_type"),
            applicability_refs=bindparam("app_refs"),
            updated_by=bindparam("upd_by"),
            updated_at=bindparam("upd_at"),
        )
    )
    for i in range(0, len(updates), _BULK_UPDATE_CHUNK):
        chunk = updates[i : i + _BULK_UPDATE_CHUNK]
        await db.execute(
            stmt,
            [
                {
                    "doc_id": entry["id"],
                    "app_type": DocApplicabilityType(entry["applicability_type"]),
                    "app_refs": entry["applicability_refs"],
                    "upd_by": user_id,
                    "upd_at": now,
                }
                for entry in chunk
            ],
        )


async def _batch_update_events(
    db: AsyncSession,
    updates: list[dict],
    user_id: str,
) -> None:
    tbl = Event.__table__
    now = datetime.now(timezone.utc)
    stmt = (
        update(tbl)
        .where(tbl.c.id == bindparam("evt_id"))
        .values(
            applicability_type=bindparam("app_type"),
            applicability_refs=bindparam("app_refs"),
            updated_by=bindparam("upd_by"),
            updated_at=bindparam("upd_at"),
        )
    )
    for i in range(0, len(updates), _BULK_UPDATE_CHUNK):
        chunk = updates[i : i + _BULK_UPDATE_CHUNK]
        await db.execute(
            stmt,
            [
                {
                    "evt_id": entry["id"],
                    "app_type": EventApplicabilityType(entry["applicability_type"]),
                    "app_refs": entry["applicability_refs"],
                    "upd_by": user_id,
                    "upd_at": now,
                }
                for entry in chunk
            ],
        )
