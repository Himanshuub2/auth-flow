from __future__ import annotations

import asyncio
import base64
import importlib
import io
import json
import logging
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, time, timedelta, timezone
from html import escape
from typing import Any
from urllib.parse import unquote
from urllib.request import urlopen

from .azure_secrets import get_secret_sync
from core.constants import DB_NAME, DB_PORT, GENERIC_EMAIL,BASE_URL

IST = timezone(timedelta(hours=5, minutes=30))

logger = logging.getLogger(__name__)

DOCUMENT_TYPE_LABELS: dict[str, str] = {
    "POLICY": "Policy",
    "GUIDANCE_NOTE": "Guidance Notes",
    "LAW_REGULATION": "Law & Regulation",
    "TRAINING_MATERIAL": "Training Resources",
    "EWS": "Early Warnings",
    "FAQ": "FAQ",
    "LATEST_NEWS_AND_ANNOUNCEMENTS": "Latest News and Announcements",
    "FLYER": "Flyers",
}

ALLOWED_WEEKLY_DOCUMENT_TYPES = {"FLYER", "POLICY", "TRAINING_MATERIAL"}

DOC_HEADING_BY_TYPE: dict[str, str] = {
    "FLYER": "New flyer available",
    "POLICY": "New Policy, Law regulation available",
    "LAW_REGULATION": "New Policy, Law regulation available",
    "TRAINING_MATERIAL": "New training material available",
}

DIGEST_MAX_WORKERS = 10
DIGEST_EXECUTOR = ThreadPoolExecutor(max_workers=DIGEST_MAX_WORKERS)
# Azure Functions timer cron is UTC by default.
# 07:00 AM IST every Monday = 01:30 AM UTC every Monday.
AZURE_TIMER_CRON_MONDAY_7AM_IST = "0 30 1 * * 1"


ACS_CONNECTION_STRING = None
SENDER_EMAIL = None
DB_CONFIG = {}

try:
    ACS_CONNECTION_STRING = get_secret_sync("ACS-CONNECTION-STRING")
    AZURE_STORAGE_CONNECTION_STRING = get_secret_sync("BLOB-CONNECTION-STRING")
    AZURE_CONTAINER_NAME = "ecp"

    SENDER_EMAIL = GENERIC_EMAIL

    POSTGRES_USER = get_secret_sync("POSTGRES-USER")

    POSTGRES_PASSWORD = get_secret_sync("POSTGRES-PASSWORD")

    POSTGRES_HOST = get_secret_sync("POSTGRES-HOST")

    DB_CONFIG = {
        "host": POSTGRES_HOST,
        "port": DB_PORT,
        "dbname": DB_NAME,
        "user": POSTGRES_USER,
        "password": POSTGRES_PASSWORD,
    }

    logging.info("Credentials loaded successfully")

except Exception as ex:
    logging.error(f"FAILED to load credentials: {str(ex)}")


def _last_week_bounds(
    reference_utc: datetime | None = None,
) -> tuple[datetime, datetime]:
    """Return [start, end) UTC bounds for previous week in IST."""
    now_utc = reference_utc or datetime.now(timezone.utc)
    now_ist = now_utc.astimezone(IST)

    this_week_start_ist = datetime.combine(
        now_ist.date() - timedelta(days=now_ist.weekday()),
        time.min,
        tzinfo=IST,
    )
    last_week_start_ist = this_week_start_ist - timedelta(days=7)

    return (
        last_week_start_ist.astimezone(timezone.utc),
        this_week_start_ist.astimezone(timezone.utc),
    )


def _safe_tags(raw_tags: Any) -> list[str]:
    if raw_tags is None:
        return []
    if isinstance(raw_tags, str):
        try:
            decoded = json.loads(raw_tags)
            if isinstance(decoded, list):
                return [str(t) for t in decoded if str(t).strip()]
            return []
        except json.JSONDecodeError:
            return []
    if isinstance(raw_tags, list):
        return [str(t) for t in raw_tags if str(t).strip()]
    return []


def _doc_link(base_url: str, document_type: str, document_id: int) -> str:
    normalized = document_type.strip().lower()
    return f"{base_url.rstrip('/')}/{normalized}/{document_id}"


def _event_link(base_url: str, event_id: int) -> str:
    return f"{base_url.rstrip('/')}/events/{event_id}"


THUMBNAIL_MAX_SIZE = (400, 400)
THUMBNAIL_JPEG_QUALITY = 75
EMAIL_MAX_WIDTH = 600
# Shared 3-col tile size (events + knowledge hub)
TILE_IMAGE_WIDTH = 150
TILE_IMAGE_HEIGHT = 150
KH_DESC_MAX_CHARS = 72
BANNER_HEIGHT = 210
TITLE_MAX_CHARS = 32
KH_TITLE_MAX_CHARS = 28
KH_TAGS_MAX_CHARS = 32
GRID_COLUMNS = 3

# Popular, readable stacks (Google Fonts where clients allow them)
_FONT_DISPLAY = "'DM Serif Display',Georgia,'Times New Roman',serif"
_FONT_BODY = "'DM Sans','Segoe UI',Roboto,Helvetica,Arial,sans-serif"
_GOOGLE_FONTS_HREF = (
    "https://fonts.googleapis.com/css2?"
    "family=DM+Sans:ital,opsz,wght@0,9..40,400;0,9..40,500;0,9..40,700;1,9..40,400"
    "&family=DM+Serif+Display&display=swap"
)

# Hero banner (teal) — also used as the full-email background motif
_BANNER_SVG_DATA_URI = (
    "data:image/svg+xml,%3Csvg xmlns=%22http://www.w3.org/2000/svg%22 width=%22600%22 height=%22210%22 "
    "viewBox=%220 0 600 210%22 preserveAspectRatio=%22xMidYMid slice%22%3E%3Cdefs%3E"
    "%3ClinearGradient id=%22bg%22 x1=%220%22 y1=%220%22 x2=%221%22 y2=%221%22%3E"
    "%3Cstop offset=%220%25%22 stop-color=%22%230B3A5C%22/%3E"
    "%3Cstop offset=%2255%25%22 stop-color=%22%23155F8A%22/%3E"
    "%3Cstop offset=%22100%25%22 stop-color=%22%230D8F9A%22/%3E"
    "%3C/linearGradient%3E"
    "%3ClinearGradient id=%22shine%22 x1=%220%22 y1=%220%22 x2=%220%22 y2=%221%22%3E"
    "%3Cstop offset=%220%25%22 stop-color=%22%23FFFFFF%22 stop-opacity=%220.18%22/%3E"
    "%3Cstop offset=%22100%25%22 stop-color=%22%23FFFFFF%22 stop-opacity=%220%22/%3E"
    "%3C/linearGradient%3E"
    "%3C/defs%3E"
    "%3Crect width=%22600%22 height=%22210%22 fill=%22url(%23bg)%22/%3E"
    "%3Ccircle cx=%22520%22 cy=%2230%22 r=%2290%22 fill=%22%23FFFFFF%22 fill-opacity=%220.08%22/%3E"
    "%3Ccircle cx=%22560%22 cy=%22170%22 r=%2270%22 fill=%22%2300C2CB%22 fill-opacity=%220.22%22/%3E"
    "%3Ccircle cx=%2240%22 cy=%22170%22 r=%2260%22 fill=%22%23FFFFFF%22 fill-opacity=%220.06%22/%3E"
    "%3Cpath d=%22M0 148 C120 128 220 168 320 148 C420 128 500 138 600 122 L600 210 L0 210 Z%22 "
    "fill=%22%23FFFFFF%22 fill-opacity=%220.1%22/%3E"
    "%3Crect width=%22600%22 height=%22210%22 fill=%22url(%23shine)%22/%3E"
    "%3C/svg%3E"
)

# Soft full-page background derived from the same banner palette (readable under dark text)
_EMAIL_BG_SVG_DATA_URI = (
    "data:image/svg+xml,%3Csvg xmlns=%22http://www.w3.org/2000/svg%22 width=%221440%22 height=%222200%22 "
    "viewBox=%220 0 1440 2200%22 preserveAspectRatio=%22xMidYMid slice%22%3E%3Cdefs%3E"
    "%3ClinearGradient id=%22g%22 x1=%220%22 y1=%220%22 x2=%221%22 y2=%221%22%3E"
    "%3Cstop offset=%220%25%22 stop-color=%22%23EAF6FB%22/%3E"
    "%3Cstop offset=%2240%25%22 stop-color=%22%23D5EEF7%22/%3E"
    "%3Cstop offset=%2275%25%22 stop-color=%22%23C5E6F2%22/%3E"
    "%3Cstop offset=%22100%25%22 stop-color=%22%23B3DCEC%22/%3E"
    "%3C/linearGradient%3E"
    "%3CradialGradient id=%22r1%22 cx=%2215%25%22 cy=%228%25%22 r=%2245%25%22%3E"
    "%3Cstop offset=%220%25%22 stop-color=%22%230D8F9A%22 stop-opacity=%220.18%22/%3E"
    "%3Cstop offset=%22100%25%22 stop-color=%22%230D8F9A%22 stop-opacity=%220%22/%3E"
    "%3C/radialGradient%3E"
    "%3CradialGradient id=%22r2%22 cx=%2288%25%22 cy=%2222%25%22 r=%2240%25%22%3E"
    "%3Cstop offset=%220%25%22 stop-color=%22%230B3A5C%22 stop-opacity=%220.16%22/%3E"
    "%3Cstop offset=%22100%25%22 stop-color=%22%230B3A5C%22 stop-opacity=%220%22/%3E"
    "%3C/radialGradient%3E"
    "%3CradialGradient id=%22r3%22 cx=%2270%25%22 cy=%2275%25%22 r=%2250%25%22%3E"
    "%3Cstop offset=%220%25%22 stop-color=%22%2300C2CB%22 stop-opacity=%220.14%22/%3E"
    "%3Cstop offset=%22100%25%22 stop-color=%22%2300C2CB%22 stop-opacity=%220%22/%3E"
    "%3C/radialGradient%3E"
    "%3C/defs%3E"
    "%3Crect width=%221440%22 height=%222200%22 fill=%22url(%23g)%22/%3E"
    "%3Crect width=%221440%22 height=%222200%22 fill=%22url(%23r1)%22/%3E"
    "%3Crect width=%221440%22 height=%222200%22 fill=%22url(%23r2)%22/%3E"
    "%3Crect width=%221440%22 height=%222200%22 fill=%22url(%23r3)%22/%3E"
    "%3C/svg%3E"
)


def _truncate_text(text: str, max_len: int) -> str:
    cleaned = str(text or "").strip()
    if len(cleaned) <= max_len:
        return cleaned
    return cleaned[: max_len - 1].rstrip() + "…"


def _thumbnail_content_id(prefix: str, item_id: int) -> str:
    return f"digest-{prefix}-{item_id}"


def _inline_attachment(content_id: str, jpeg_bytes: bytes) -> dict[str, str]:
    return {
        "name": f"{content_id}.jpg",
        "contentType": "image/jpeg",
        "contentInBase64": base64.b64encode(jpeg_bytes).decode("ascii"),
        "contentId": content_id,
    }


def _normalize_file_type(raw: Any) -> str:
    return str(raw or "").strip().upper()


def _parse_file_ids(raw: Any) -> list[int]:
    """Parse file_ids from JSON array column."""
    if raw is None:
        return []
    if isinstance(raw, list):
        return [int(x) for x in raw if x is not None]
    if isinstance(raw, str):
        try:
            decoded = json.loads(raw)
            if isinstance(decoded, list):
                return [int(x) for x in decoded if x is not None]
        except (json.JSONDecodeError, ValueError):
            pass
    return []


def _resolve_blob_path(path_or_url: str, container_name: str) -> str:
    """Return blob path from a stored blob path or full Azure blob URL."""
    if "://" not in path_or_url:
        return path_or_url.lstrip("/")
    try:
        base = path_or_url.split("?", 1)[0]
        prefix = f"/{container_name}/"
        if prefix not in base:
            return path_or_url
        idx = base.index(prefix) + len(prefix)
        raw = base[idx:].strip("/")
        return unquote(raw) if raw else path_or_url
    except Exception:
        return path_or_url


def _fetch_blob_bytes_from_azure(blob_path: str) -> bytes | None:
    """Download blob bytes from Azure using connection string (sync)."""


    if not blob_path or not str(blob_path).strip():
        return None

    conn_str = AZURE_STORAGE_CONNECTION_STRING
    container_name = AZURE_CONTAINER_NAME
    if not conn_str:
        logger.warning("AZURE_STORAGE_CONNECTION_STRING is not configured")
        return None


    try:
        blob_module = importlib.import_module("azure.storage.blob")
        blob_service_client_cls = getattr(blob_module, "BlobServiceClient")
        client = blob_service_client_cls.from_connection_string(conn_str)
        blob_client = client.get_blob_client(container=container_name, blob=blob_path)
        return blob_client.download_blob().readall()
    except Exception:
        logger.warning(
            "Failed to fetch blob from Azure: container=%s blob=%s",
            container_name,
            blob_path,
            exc_info=True,
        )
        return None


def _compress_image_to_jpeg_bytes(image_bytes: bytes) -> bytes:
    """Resize and compress image bytes to JPEG for email inline attachments."""
    from PIL import Image

    img = Image.open(io.BytesIO(image_bytes))
    img = img.convert("RGB")
    img.thumbnail(THUMBNAIL_MAX_SIZE, Image.LANCZOS)
    buffer = io.BytesIO()
    img.save(buffer, format="JPEG", quality=THUMBNAIL_JPEG_QUALITY, optimize=True)
    return buffer.getvalue()


def _fetch_and_compress_blob(path_or_url: str) -> bytes | None:
    """Fetch blob from Azure and return compressed JPEG bytes."""
    image_bytes = _fetch_blob_bytes_from_azure(path_or_url)
    if not image_bytes:
        return None
    try:
        return _compress_image_to_jpeg_bytes(image_bytes)
    except Exception:
        logger.warning(
            "Failed to compress blob image: %s",
            path_or_url,
            exc_info=True,
        )
        return None


def _fetch_files_for_ids(
    cursor,
    file_ids: list[int],
    schema: str,
) -> list[dict[str, Any]]:
    """Fetch file records from documents.files or events.files by IDs."""
    if not file_ids:
        return []

    placeholders = ",".join(["%s"] * len(file_ids))
    columns = ["id", "file_type", "file_url"]
    if schema == "events":
        columns.append("thumbnail_url")

    sql = f"""
        SELECT {', '.join(columns)}
        FROM {schema}.files
        WHERE id IN ({placeholders})
        ORDER BY sort_order ASC;
    """
    cursor.execute(sql, file_ids)
    return [dict(row) for row in cursor.fetchall()]


def _pick_thumbnail_source_for_event(files: list[dict[str, Any]]) -> str | None:
    """Pick blob path/URL for an event card: prefer IMAGE, fallback to video thumbnail."""
    for f in files:
        if _normalize_file_type(f.get("file_type")) == "IMAGE" and f.get("file_url"):
            return f["file_url"]
    for f in files:
        if _normalize_file_type(f.get("file_type")) == "VIDEO" and f.get("thumbnail_url"):
            return f["thumbnail_url"]
    return None


def _pick_thumbnail_source_for_document(files: list[dict[str, Any]]) -> str | None:
    """Pick blob path/URL for a flyer document card."""
    for f in files:
        if _normalize_file_type(f.get("file_type")) == "IMAGE" and f.get("file_url"):
            return f["file_url"]
    return None


def create_acs_email_client(connection_string: str) -> Any:
    """Create Azure Communication Services EmailClient from connection string."""
    email_module = importlib.import_module("azure.communication.email")
    email_client_cls = getattr(email_module, "EmailClient")
    return email_client_cls.from_connection_string(connection_string)


def create_psycopg2_connection(db_config: dict[str, Any]) -> Any:
    """
    Create psycopg2 connection from DB_CONFIG.

    Required keys: host, port, dbname, user, password.
    """
    psycopg2_module = importlib.import_module("psycopg2")
    return psycopg2_module.connect(
        host=db_config["host"],
        port=db_config["port"],
        dbname=db_config["dbname"],
        user=db_config["user"],
        password=db_config["password"],
    )


def get_digest_executor() -> ThreadPoolExecutor:
    """Return shared thread pool executor for blocking operations."""
    return DIGEST_EXECUTOR


def get_monday_7am_ist_timer_schedule() -> str:
    """Return Azure Timer cron expression for Monday 7:00 AM IST."""
    return AZURE_TIMER_CRON_MONDAY_7AM_IST


def _normalize_recipients(recipients: list[str]) -> list[dict[str, str]]:
    return [{"address": r.strip()} for r in recipients if r and r.strip()]


def _build_payload_from_rows(
    doc_rows: list[dict[str, Any]],
    event_rows: list[dict[str, Any]],
    *,
    start_utc: datetime,
    end_utc: datetime,
    base_url: str,
    doc_file_map: dict[int, str | None] | None = None,
    event_file_map: dict[int, str | None] | None = None,
    inline_attachments: list[dict[str, str]] | None = None,
) -> dict[str, Any]:
    doc_file_map = doc_file_map or {}
    event_file_map = event_file_map or {}
    inline_attachments = inline_attachments or []

    documents: list[dict[str, Any]] = []
    for row in doc_rows:
        doc_type = str(row["document_type"])
        if doc_type not in ALLOWED_WEEKLY_DOCUMENT_TYPES:
            continue
        tags = _safe_tags(row["tags"])[:3]
        doc_id = int(row["document_id"])
        thumbnail_cid = doc_file_map.get(doc_id) if doc_type == "FLYER" else None
        documents.append(
            {
                "id": doc_id,
                "name": row["name"],
                "document_type": doc_type,
                "document_type_label": DOCUMENT_TYPE_LABELS.get(doc_type, doc_type),
                "heading": DOC_HEADING_BY_TYPE.get(doc_type, "New document available"),
                "description": row["summary"] or "",
                "tags": tags,
                "link": _doc_link(base_url, doc_type, doc_id),
                "created_at_utc": row["created_at"].isoformat() if row["created_at"] else None,
                "thumbnail_cid": thumbnail_cid,
            }
        )

    events: list[dict[str, Any]] = []
    for row in event_rows:
        event_id = int(row["event_id"])
        events.append(
            {
                "id": event_id,
                "name": row["event_name"],
                "description": row["description"] or "",
                "heading": "New Event(s) added",
                "link": _event_link(base_url, event_id),
                "created_at_utc": row["created_at"].isoformat() if row["created_at"] else None,
                "thumbnail_cid": event_file_map.get(event_id),
            }
        )

    start_ist = start_utc.astimezone(IST)
    end_ist_exclusive = end_utc.astimezone(IST)
    period_label = (
        f"{start_ist.strftime('%d %b %Y')} - "
        f"{(end_ist_exclusive - timedelta(days=1)).strftime('%d %b %Y')}"
    )

    return {
        "period": {
            "start_ist": start_ist.isoformat(),
            "end_ist_exclusive": end_ist_exclusive.isoformat(),
            "label": period_label,
        },
        "knowledge_hub": documents,
        "events": events,
        "inline_attachments": inline_attachments,
        "counts": {
            "knowledge_hub": len(documents),
            "events": len(events),
            "total": len(documents) + len(events),
        },
        "has_content": bool(documents or events),
    }


async def build_weekly_digest_payload(
    db_config: dict[str, Any],
    *,
    reference_utc: datetime | None = None,
    base_url: str = "https://ecp.com",
) -> dict[str, Any]:
    """
    Async payload builder using psycopg2 + ThreadPoolExecutor.

    Fetches latest document/event revisions created in last week IST window.
    """
    return await build_weekly_digest_payload_with_executor(
        db_config,
        reference_utc=reference_utc,
        base_url=base_url,
    )


def build_weekly_digest_payload_sync(
    db_config: dict[str, Any],
    *,
    reference_utc: datetime | None = None,
    base_url: str = "https://ecp.com",
) -> dict[str, Any]:
    """
    Sync variant for Azure Function usage with psycopg2 DB config.

    Accepts DB_CONFIG:
    {
        "host": "...",
        "port": 5432,
        "dbname": "...",
        "user": "...",
        "password": "..."
    }
    """
    start_utc, end_utc = _last_week_bounds(reference_utc=reference_utc)

    documents_sql = """
        SELECT
            latest.document_id,
            latest.name,
            latest.document_type,
            latest.summary,
            latest.tags,
            latest.created_at,
            latest.file_ids
        FROM (
            SELECT DISTINCT ON (document_id)
                *
            FROM documents.document_revisions
            ORDER BY document_id, revision_number DESC
        ) latest
        WHERE latest.created_at >= %(start_utc)s
          AND latest.created_at < %(end_utc)s
        ORDER BY latest.name ASC;
    """
    events_sql = """
        SELECT
            latest.event_id,
            latest.event_name,
            latest.description,
            latest.created_at,
            latest.file_ids
        FROM (
            SELECT DISTINCT ON (event_id)
                *
            FROM events.event_revisions
            ORDER BY event_id, revision_number DESC
        ) latest
        WHERE latest.created_at >= %(start_utc)s
          AND latest.created_at < %(end_utc)s
        ORDER BY latest.event_name ASC;
    """

    bind = {"start_utc": start_utc, "end_utc": end_utc}
    psycopg2_extras = importlib.import_module("psycopg2.extras")
    real_dict_cursor = getattr(psycopg2_extras, "RealDictCursor")

    with create_psycopg2_connection(db_config) as conn:
        with conn.cursor(cursor_factory=real_dict_cursor) as cur:
            cur.execute(documents_sql, bind)
            doc_rows = list(cur.fetchall())
            cur.execute(events_sql, bind)
            event_rows = list(cur.fetchall())

            # Fetch file thumbnails for flyer documents
            doc_file_map: dict[int, str | None] = {}
            inline_attachments: list[dict[str, str]] = []
            for row in doc_rows:
                doc_type = str(row["document_type"])
                if doc_type != "FLYER":
                    continue
                file_ids = _parse_file_ids(row.get("file_ids"))
                if not file_ids:
                    continue
                files = _fetch_files_for_ids(cur, file_ids, "documents")
                blob_source = _pick_thumbnail_source_for_document(files)
                if not blob_source:
                    continue
                jpeg_bytes = _fetch_and_compress_blob(blob_source)
                if not jpeg_bytes:
                    continue
                doc_id = int(row["document_id"])
                content_id = _thumbnail_content_id("doc", doc_id)
                doc_file_map[doc_id] = content_id
                inline_attachments.append(_inline_attachment(content_id, jpeg_bytes))

            # Fetch file thumbnails for events
            event_file_map: dict[int, str | None] = {}
            for row in event_rows:
                file_ids = _parse_file_ids(row.get("file_ids"))
                if not file_ids:
                    continue
                files = _fetch_files_for_ids(cur, file_ids, "events")
                blob_source = _pick_thumbnail_source_for_event(files)
                if not blob_source:
                    continue
                jpeg_bytes = _fetch_and_compress_blob(blob_source)
                if not jpeg_bytes:
                    continue
                event_id = int(row["event_id"])
                content_id = _thumbnail_content_id("event", event_id)
                event_file_map[event_id] = content_id
                inline_attachments.append(_inline_attachment(content_id, jpeg_bytes))

    return _build_payload_from_rows(
        doc_rows,
        event_rows,
        start_utc=start_utc,
        end_utc=end_utc,
        base_url=base_url,
        doc_file_map=doc_file_map,
        event_file_map=event_file_map,
        inline_attachments=inline_attachments,
    )


async def build_weekly_digest_payload_with_executor(
    db_config: dict[str, Any],
    *,
    reference_utc: datetime | None = None,
    base_url: str = "https://ecp.com",
) -> dict[str, Any]:
    """Async wrapper that executes sync psycopg2 flow in ThreadPoolExecutor."""
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(
        DIGEST_EXECUTOR,
        lambda: build_weekly_digest_payload_sync(
            db_config,
            reference_utc=reference_utc,
            base_url=base_url,
        ),
    )


def send_html_email_via_acs(
    *,
    connection_string: str,
    sender_address: str,
    to_addresses: list[str],
    subject: str,
    html_content: str,
    plain_text: str | None = None,
    cc_addresses: list[str] | None = None,
    bcc_addresses: list[str] | None = None,
    inline_attachments: list[dict[str, str]] | None = None,
) -> Any:
    """
    Send HTML email through Azure Communication Services Email.

    Returns the ACS send result from poller.result().
    """
    client = create_acs_email_client(connection_string)
    message: dict[str, Any] = {
        "senderAddress": sender_address,
        "recipients": {
            "to": _normalize_recipients(to_addresses),
            "cc": _normalize_recipients(cc_addresses or []),
            "bcc": _normalize_recipients(bcc_addresses or []),
        },
        "content": {
            "subject": subject,
            "plainText": plain_text or "Weekly Knowledge Hub and Events Digest",
            "html": html_content,
        },
    }
    if inline_attachments:
        message["attachments"] = inline_attachments
    poller = client.begin_send(message)
    return poller.result()


def build_and_send_weekly_digest_sync(
    *,
    db_config: dict[str, Any],
    connection_string: str,
    sender_address: str,
    to_addresses: list[str],
    subject: str = "Weekly Knowledge Hub and Events Digest",
    base_url: str = "https://ecp.com",
    banner_image_url: str | None = None,
    reference_utc: datetime | None = None,
    cc_addresses: list[str] | None = None,
    bcc_addresses: list[str] | None = None,
) -> dict[str, Any]:
    """Build weekly digest payload + HTML, then send via ACS (sync flow)."""
    payload = build_weekly_digest_payload_sync(
        db_config,
        reference_utc=reference_utc,
        base_url=base_url,
    )
    html = build_weekly_digest_html(
        payload,
        banner_image_url=banner_image_url,
    )
    send_result = send_html_email_via_acs(
        connection_string=connection_string,
        sender_address=sender_address,
        to_addresses=to_addresses,
        cc_addresses=cc_addresses,
        bcc_addresses=bcc_addresses,
        subject=subject,
        html_content=html,
        inline_attachments=list(payload.get("inline_attachments") or []),
        plain_text=(
            "Weekly Knowledge Hub and Events digest is available. "
            "Please review the latest highlights."
        ),
    )
    return {
        "payload": payload,
        "html": html,
        "send_result": send_result,
    }


async def build_and_send_weekly_digest(
    *,

    to_addresses: list[str],
    subject: str = "Weekly Knowledge Hub and Events Digest",
    base_url: str = BASE_URL,
    banner_image_url: str | None = None,
    reference_utc: datetime | None = None,
    cc_addresses: list[str] | None = None,
    bcc_addresses: list[str] | None = None,
) -> dict[str, Any]:
    """Async wrapper for sync build+send flow using ThreadPoolExecutor(max_workers=10)."""
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(
        DIGEST_EXECUTOR,
        lambda: build_and_send_weekly_digest_sync(
            db_config=DB_CONFIG,
            connection_string=ACS_CONNECTION_STRING,
            sender_address=SENDER_EMAIL,
            to_addresses=to_addresses,
            cc_addresses=cc_addresses,
            bcc_addresses=bcc_addresses,
            subject=subject,
            base_url=BASE_URL,
            banner_image_url=banner_image_url,
            reference_utc=reference_utc,
        ),
    )

def _has_thumbnail(item: dict[str, Any]) -> bool:
    return bool(item.get("thumbnail_cid"))


def _sort_section_items(
    items: list[dict[str, Any]],
    *,
    prefer_flyers: bool = False,
) -> list[dict[str, Any]]:
    """Image tiles first; no-image items last. Optional flyer preference among imaged docs."""

    def _key(item: dict[str, Any]) -> tuple[int, int]:
        no_image = 0 if _has_thumbnail(item) else 1
        flyer_rank = 0
        if prefer_flyers:
            flyer_rank = (
                0
                if str(item.get("document_type") or "").upper() == "FLYER"
                else 1
            )
        return (no_image, flyer_rank)

    return sorted(items, key=_key)


def _format_tags_line(tags: list[Any]) -> str:
    cleaned = [str(t).strip() for t in (tags or []) if str(t).strip()]
    if not cleaned:
        return ""
    return _truncate_text(" · ".join(cleaned), KH_TAGS_MAX_CHARS)


def _render_tile_image(thumbnail_cid: str | None, alt_text: str) -> str:
    """Rounded image only (no card). Soft placeholder when missing."""
    if thumbnail_cid:
        alt = escape(_truncate_text(alt_text, 120))
        return (
            f'<img class="tile-img" src="cid:{thumbnail_cid}" width="{TILE_IMAGE_WIDTH}" '
            f'alt="{alt}" '
            f'style="display:block; width:100%; max-width:100%; height:auto; '
            f"border:0; border-radius:18px; object-fit:cover;\">"
        )
    return (
        f'<table role="presentation" class="tile-img-ph" width="100%" '
        f'cellpadding="0" cellspacing="0" border="0" '
        f'style="width:100%; max-width:100%; background-color:#D9E8F2; border-radius:18px;">'
        f'<tr><td height="{TILE_IMAGE_HEIGHT}" style="height:{TILE_IMAGE_HEIGHT}px; '
        f'font-size:0; line-height:0;">&nbsp;</td></tr></table>'
    )


def _render_product_tile(
    *,
    name: str,
    link: str,
    thumbnail_cid: str | None,
    alt_text: str,
    meta_html: str = "",
) -> str:
    """
    Product-grid tile: image only + text under it.
    Text width matches image via shared fixed-layout column (Outlook-safe wrapping).
    """
    safe_link = escape(link)
    image_html = _render_tile_image(thumbnail_cid, alt_text)

    return (
        f'<table class="product-tile" role="presentation" width="100%" '
        f'cellpadding="0" cellspacing="0" border="0" '
        f'style="width:100%; max-width:100%; table-layout:fixed; '
        f'background-color:transparent; border:0;">'
        f'<tr><td align="left" style="line-height:0; font-size:0; padding:0;">'
        f'<a href="{safe_link}" style="text-decoration:none; border:0;">{image_html}</a>'
        f"</td></tr>"
        f'<tr><td align="left" valign="top" '
        f'style="padding:10px 2px 14px 2px; font-family:{_FONT_BODY}; '
        f'word-wrap:break-word; overflow-wrap:anywhere; word-break:break-word;">'
        f'<a href="{safe_link}" style="text-decoration:none; color:#111111;">'
        # <p> wraps in Outlook; span+nowrap does not
        f'<p style="margin:0; padding:0; font-family:{_FONT_BODY}; font-size:14px; '
        f'font-weight:700; color:#111111; line-height:18px; mso-line-height-rule:exactly;">'
        f"{name}</p>"
        f"{meta_html}"
        f"</a>"
        f"</td></tr>"
        f"</table>"
    )


def _render_doc_card(item: dict[str, Any]) -> str:
    """Knowledge Hub: name, type, tags, description (truncated except flyers)."""
    name = escape(_truncate_text(str(item.get("name") or ""), KH_TITLE_MAX_CHARS))
    doc_type = str(item.get("document_type") or "").upper()
    type_label = escape(
        str(
            item.get("document_type_label")
            or DOCUMENT_TYPE_LABELS.get(doc_type, doc_type)
            or "Document"
        )
    )
    tags_raw = item.get("tags") or []
    if not isinstance(tags_raw, list):
        tags_raw = _safe_tags(tags_raw)
    tags_line = escape(_format_tags_line(tags_raw))

    description = str(item.get("description") or "").strip()
    if doc_type != "FLYER":
        description = _truncate_text(description, KH_DESC_MAX_CHARS)
    description = escape(description)

    meta_parts: list[str] = []
    if type_label:
        meta_parts.append(
            f'<p style="margin:4px 0 0 0; padding:0; font-family:{_FONT_BODY}; font-size:11px; '
            f'font-weight:600; color:#0F6E8C; line-height:15px; mso-line-height-rule:exactly;">'
            f"{type_label}</p>"
        )
    if tags_line:
        meta_parts.append(
            f'<p style="margin:3px 0 0 0; padding:0; font-family:{_FONT_BODY}; font-size:11px; '
            f'color:#6A8499; line-height:15px; mso-line-height-rule:exactly;">'
            f"{tags_line}</p>"
        )
    if description:
        meta_parts.append(
            f'<p style="margin:6px 0 0 0; padding:0; font-family:{_FONT_BODY}; font-size:12px; '
            f'color:#4A5F70; line-height:17px; mso-line-height-rule:exactly; '
            f'word-wrap:break-word; overflow-wrap:anywhere; word-break:break-word;">'
            f"{description}</p>"
        )

    return _render_product_tile(
        name=name,
        link=str(item.get("link") or "#"),
        thumbnail_cid=item.get("thumbnail_cid"),
        alt_text=str(item.get("name") or ""),
        meta_html="".join(meta_parts),
    )


def _render_event_card(item: dict[str, Any]) -> str:
    """Events: same 3-col product tile as Knowledge Hub (image + name)."""
    name = escape(_truncate_text(str(item.get("name") or ""), TITLE_MAX_CHARS))
    description = escape(
        _truncate_text(str(item.get("description") or "").strip(), KH_DESC_MAX_CHARS)
    )
    meta = ""
    if description:
        meta = (
            f'<p style="margin:6px 0 0 0; padding:0; font-family:{_FONT_BODY}; font-size:12px; '
            f'color:#4A5F70; line-height:17px; mso-line-height-rule:exactly; '
            f'word-wrap:break-word; overflow-wrap:anywhere; word-break:break-word;">'
            f"{description}</p>"
        )
    return _render_product_tile(
        name=name,
        link=str(item.get("link") or "#"),
        thumbnail_cid=item.get("thumbnail_cid"),
        alt_text=str(item.get("name") or ""),
        meta_html=meta,
    )


def _render_n_col_grid(
    cards: list[str],
    *,
    columns: int,
    empty_message: str,
) -> str:
    """
    N-column grid without gap <td>s (those cause horizontal scroll when pane shrinks).
    Spacing uses padding only; total column % always equals 100%.
    """
    columns = max(1, columns)
    widths = [100 // columns] * columns
    widths[0] += 100 - sum(widths)
    if not cards:
        return (
            f'<tr><td class="mobile-pad" style="padding:10px 12px; '
            f'font-family:{_FONT_BODY}; font-size:13px; color:#4A6F8C;">'
            f"{empty_message}</td></tr>"
        )

    rows_html = ""
    for i in range(0, len(cards), columns):
        chunk = cards[i : i + columns]
        cells = ""
        for idx in range(columns):
            content = chunk[idx] if idx < len(chunk) else "&nbsp;"
            w = widths[idx]
            if idx == 0:
                pad = "padding:0 6px 12px 0;"
            elif idx == columns - 1:
                pad = "padding:0 0 12px 6px;"
            else:
                pad = "padding:0 6px 12px 6px;"
            cells += (
                f'<td class="stack-col" width="{w}%" valign="top" '
                f'style="width:{w}%; max-width:{w}%; {pad} '
                f'overflow:hidden; word-wrap:break-word;">{content}</td>'
            )
        rows_html += (
            '<tr><td class="mobile-pad" style="padding:4px 12px 0 12px;">'
            '<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" '
            'style="table-layout:fixed; width:100%; max-width:100%; border-collapse:collapse;">'
            f"<tr>{cells}</tr></table>"
            "</td></tr>"
        )
    return rows_html


def _render_events_grid(cards: list[str]) -> str:
    return _render_n_col_grid(
        cards,
        columns=GRID_COLUMNS,
        empty_message="No events this week.",
    )


def _render_knowledge_grid(cards: list[str]) -> str:
    return _render_n_col_grid(
        cards,
        columns=GRID_COLUMNS,
        empty_message="No Knowledge Hub items this week.",
    )


def _render_section_cta(*, cta_label: str, cta_href: str) -> str:
    """End-of-section button-style CTA."""
    return (
        '<tr><td class="mobile-pad" align="center" style="padding:18px 12px 8px 12px;">'
        f'<a href="{escape(cta_href)}" '
        f'style="display:inline-block; font-family:{_FONT_BODY}; font-size:12px; '
        "font-weight:700; letter-spacing:0.6px; color:#FFFFFF; text-decoration:none; "
        "background-color:#0F6E8C; border-radius:8px; padding:11px 22px;\">"
        f"{escape(cta_label)}"
        "</a>"
        "</td></tr>"
    )


def _render_section_heading(label: str) -> str:
    return (
        '<tr><td class="mobile-pad" style="padding:22px 12px 6px 12px;">'
        '<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" '
        'style="table-layout:fixed; width:100%;">'
        "<tr>"
        '<td width="4" style="width:4px; background-color:#0F6E8C; border-radius:2px; '
        'font-size:0; line-height:0;">&nbsp;</td>'
        f'<td style="padding-left:10px; font-family:{_FONT_DISPLAY}; font-size:20px; '
        f'font-weight:400; color:#0F2C44; letter-spacing:0.2px; '
        f'word-wrap:break-word;">{escape(label)}</td>'
        "</tr></table>"
        "</td></tr>"
    )


def _render_banner_block(
    *,
    banner_src: str | None,
    period_display: str,
    root_url: str,
) -> str:
    """Hero banner with each text line in its own table row (Outlook wraps correctly)."""
    bg_src = (banner_src or "").strip() or _BANNER_SVG_DATA_URI
    safe_bg = escape(bg_src, quote=True)

    return f"""<!-- BANNER (text overlaid; one row per line for Outlook) -->
<tr>
<td class="banner-cell" align="center" background="{safe_bg}"
style="background-color:#0B3A5C; background-image:url('{safe_bg}');
background-size:cover; background-position:center center; background-repeat:no-repeat;">
<!--[if mso]>
<v:rect xmlns:v="urn:schemas-microsoft-com:vml" fill="true" stroke="false"
 style="width:{EMAIL_MAX_WIDTH}px; height:{BANNER_HEIGHT}px;">
<v:fill type="frame" src="{safe_bg}" color="#0B3A5C"/>
<v:textbox inset="0,0,0,0" style="mso-fit-shape-to-text:true">
<![endif]-->
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0"
style="width:100%; max-width:100%; table-layout:fixed;">
<tr>
<td align="center" valign="middle" style="padding:36px 16px 38px 16px;">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0"
style="max-width:100%; table-layout:fixed;">
<tr>
<td align="center" class="banner-kicker"
style="font-family:{_FONT_BODY}; font-size:11px; font-weight:700;
letter-spacing:1.4px; text-transform:uppercase; color:#A8E4EA;
mso-line-height-rule:exactly; line-height:16px; padding-bottom:8px;">
Your weekly roundup
</td>
</tr>
<tr>
<td align="center" class="banner-title"
style="font-family:{_FONT_DISPLAY}; font-size:26px; font-weight:400;
color:#FFFFFF; mso-line-height-rule:exactly; line-height:32px; padding-bottom:8px;
word-wrap:break-word;">
Events &amp; Knowledge Hub
</td>
</tr>
<tr>
<td align="center" class="banner-subtitle"
style="font-family:{_FONT_BODY}; font-size:13px; color:#D2EAF2;
mso-line-height-rule:exactly; line-height:19px; padding-bottom:16px;
word-wrap:break-word;">
{period_display}
</td>
</tr>
<tr>
<td align="center">
<a href="{escape(root_url)}"
style="display:inline-block; font-family:{_FONT_BODY}; font-size:12px;
font-weight:700; letter-spacing:0.4px; color:#0B3A5C; text-decoration:none;
background-color:#FFFFFF; border-radius:8px; padding:10px 20px;">Open portal</a>
</td>
</tr>
</table>
</td>
</tr>
</table>
<!--[if mso]>
</v:textbox>
</v:rect>
<![endif]-->
</td>
</tr>"""


def build_weekly_digest_html(
    payload: dict[str, Any],
    *,
    banner_image_url: str | None = None,
) -> str:
    """Build Outlook-safe HTML digest from the weekly payload."""
    knowledge_hub = _sort_section_items(
        list(payload.get("knowledge_hub") or []),
        prefer_flyers=True,
    )
    events = _sort_section_items(list(payload.get("events") or []))

    period_label = _truncate_text(
        payload["period"].get("label", "") if payload and payload.get("period") else "",
        48,
    )

    knowledge_cards = [_render_doc_card(item) for item in knowledge_hub]
    event_cards = [_render_event_card(item) for item in events]

    events_grid = _render_events_grid(event_cards)
    knowledge_grid = _render_knowledge_grid(knowledge_cards)

    period_display = escape(period_label) if period_label else "this week"
    root_url = str(BASE_URL or "https://ecp.com").rstrip("/")
    events_cta = f"{root_url}/events"
    documents_cta = root_url

    banner_src = (banner_image_url or "").strip() or None
    banner_block = _render_banner_block(
        banner_src=banner_src,
        period_display=period_display,
        root_url=root_url,
    )

    events_heading = _render_section_heading("This Week's Events")
    knowledge_heading = _render_section_heading("Knowledge Hub")

    events_end_cta = _render_section_cta(
        cta_label="VIEW ALL EVENTS",
        cta_href=events_cta,
    )
    documents_end_cta = _render_section_cta(
        cta_label="VIEW ALL DOCUMENTS",
        cta_href=documents_cta,
    )

    return f"""<!DOCTYPE html>
<html lang="en" xmlns:v="urn:schemas-microsoft-com:vml" xmlns:o="urn:schemas-microsoft-com:office:office" style="width:100%; max-width:100%; overflow-x:hidden;">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<meta http-equiv="X-UA-Compatible" content="IE=edge">
<meta name="x-apple-disable-message-reformatting">
<meta name="color-scheme" content="light dark">
<meta name="supported-color-schemes" content="light dark">
<title>MSIL Compliance Weekly Digest</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="{_GOOGLE_FONTS_HREF}" rel="stylesheet">
<!--[if mso]>
<noscript>
<xml>
<o:OfficeDocumentSettings>
<o:PixelsPerInch>96</o:PixelsPerInch>
</o:OfficeDocumentSettings>
</xml>
</noscript>
<style>
table {{border-collapse: collapse;}}
td, th, div, p, a, h1, h2, h3 {{font-family: Arial, Helvetica, sans-serif;}}
</style>
<![endif]-->
<style>
  html, body {{ width: 100% !important; max-width: 100% !important; overflow-x: hidden !important; margin: 0 !important; padding: 0 !important; }}
  body, table, td, a {{ -webkit-text-size-adjust: 100%; -ms-text-size-adjust: 100%; }}
  table, td {{ mso-table-lspace: 0pt; mso-table-rspace: 0pt; border-collapse: collapse; }}
  img {{ -ms-interpolation-mode: bicubic; border: 0; height: auto; line-height: 100%; outline: none; text-decoration: none; max-width: 100% !important; }}
  body {{ margin: 0; padding: 0; width: 100% !important; height: 100% !important; }}
  p {{ margin: 0; padding: 0; }}
  a {{ text-decoration: none; }}
  .email-outer {{ width: 100% !important; max-width: 100% !important; overflow-x: hidden !important; }}
  .email-wrapper {{ width: 100% !important; max-width: {EMAIL_MAX_WIDTH}px !important; }}
  .banner-cell {{
    background-size: cover !important;
    background-position: center center !important;
    background-repeat: no-repeat !important;
  }}
  .product-tile {{ width: 100% !important; max-width: 100% !important; table-layout: fixed !important; }}
  .tile-img, .tile-img-ph {{ width: 100% !important; max-width: 100% !important; height: auto !important; display: block !important; }}
  .stack-col {{ overflow: hidden !important; word-wrap: break-word !important; }}
  @media screen and (max-width: 620px) {{
    .email-wrapper {{ width: 100% !important; max-width: 100% !important; }}
    .stack-col {{ display: block !important; width: 100% !important; max-width: 100% !important; padding-left: 0 !important; padding-right: 0 !important; }}
    .mobile-pad {{ padding-left: 12px !important; padding-right: 12px !important; }}
    .banner-title {{ font-size: 22px !important; line-height:28px !important; }}
    .banner-subtitle {{ font-size: 12px !important; line-height:18px !important; }}
    .banner-cell {{ padding: 28px 14px 30px 14px !important; }}
  }}
</style>
</head>
<body style="margin:0; padding:0; width:100%; max-width:100%; overflow-x:hidden; -webkit-font-smoothing:antialiased; background-color:#D5EEF7; background-image:url('{_EMAIL_BG_SVG_DATA_URI}'); background-size:cover; background-position:center top; background-repeat:no-repeat;">

<!-- Preheader -->
<div style="display:none; max-height:0; overflow:hidden; mso-hide:all; font-size:1px; line-height:1px; color:#D5EEF7;">
Your Weekly Digest: Events &amp; Knowledge Hub updates from MSIL Compliance.&nbsp;&zwnj;&nbsp;&zwnj;&nbsp;&zwnj;&nbsp;&zwnj;&nbsp;&zwnj;&nbsp;&zwnj;&nbsp;&zwnj;&nbsp;&zwnj;&nbsp;&zwnj;&nbsp;&zwnj;
</div>

<!--[if mso]>
<v:background xmlns:v="urn:schemas-microsoft-com:vml" fill="t">
<v:fill type="frame" src="{_EMAIL_BG_SVG_DATA_URI}" color="#D5EEF7"/>
</v:background>
<![endif]-->

<table role="presentation" class="email-outer" width="100%" cellpadding="0" cellspacing="0" border="0" style="width:100%; max-width:100%; table-layout:fixed; background-color:transparent;">
<tr>
<td align="center" valign="top" style="padding:12px 0 20px 0;">

<!--[if mso]>
<table role="presentation" width="{EMAIL_MAX_WIDTH}" cellpadding="0" cellspacing="0" border="0" align="center"><tr><td>
<![endif]-->
<table role="presentation" class="email-wrapper" width="100%" cellpadding="0" cellspacing="0" border="0" style="width:100%; max-width:{EMAIL_MAX_WIDTH}px; table-layout:fixed; background-color:#F7FBFD; border:1px solid #D0E4EF; border-radius:14px; overflow:hidden;">

{banner_block}

{events_heading}

<!-- EVENTS GRID -->
{events_grid}

<!-- VIEW EVENTS CTA -->
{events_end_cta}

<!-- SPACER -->
<tr><td style="padding:10px 0 0 0; font-size:1px; line-height:1px;">&nbsp;</td></tr>

{knowledge_heading}

<!-- KNOWLEDGE HUB GRID -->
{knowledge_grid}

<!-- VIEW DOCUMENTS CTA -->
{documents_end_cta}

<!-- FOOTER -->
<tr>
<td style="padding:28px 12px 24px 12px; background-color:#FFFFFF; border-top:1px solid #D7E6F0;">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" style="table-layout:fixed; width:100%;">
<tr>
<td style="font-family:{_FONT_BODY}; word-wrap:break-word;">
<p style="margin:0 0 10px 0; padding:0; font-size:14px; color:#0F2C44; line-height:20px;">Regards,<br><strong>Compliance Team</strong></p>
<p style="margin:0; padding:0; font-size:11px; line-height:18px; color:#4A6F8C;">
This is a weekly digest sent to all employees. You are receiving this because you are part of the organization&rsquo;s distribution list.<br>
MSIL Corporate Office, Compliance Division
</p>
</td>
</tr>
</table>
</td>
</tr>

</table>
<!--[if mso]>
</td></tr></table>
<![endif]-->

</td>
</tr>
</table>

</body>
</html>"""


async def build_weekly_digest_email(
    db_config: dict[str, Any],
    *,
    reference_utc: datetime | None = None,
    base_url: str = "https://ecp.com",
    banner_image_url: str | None = None,
) -> tuple[dict[str, Any], str]:
    payload = await build_weekly_digest_payload(
        db_config,
        reference_utc=reference_utc,
        base_url=base_url,
    )
    html = build_weekly_digest_html(
        payload,
        banner_image_url=banner_image_url,
    )
    return payload, html
