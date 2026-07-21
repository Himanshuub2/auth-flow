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

from utils.dates import IST

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


def _last_week_bounds(reference_utc: datetime | None = None) -> tuple[datetime, datetime]:
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


THUMBNAIL_MAX_SIZE = (300, 225)  # 4:3 aspect, fits email grid nicely
THUMBNAIL_JPEG_QUALITY = 60


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


def _fetch_blob_bytes_from_azure(path_or_url: str) -> bytes | None:
    """Download blob bytes from Azure using connection string (sync)."""
    from config import settings

    if not path_or_url or not str(path_or_url).strip():
        return None

    if getattr(settings, "BYPASS_AZURE_UPLOAD", False):
        try:
            import hashlib

            blob_path = _resolve_blob_path(path_or_url, settings.AZURE_CONTAINER_NAME)
            seed = hashlib.md5(blob_path.encode()).hexdigest()[:8]
            fake_url = f"https://picsum.photos/seed/{seed}/400/300"
            with urlopen(fake_url, timeout=15) as resp:
                return resp.read()
        except Exception:
            logger.warning(
                "Failed to fetch bypass placeholder for blob: %s",
                path_or_url,
                exc_info=True,
            )
            return None

    conn_str = settings.AZURE_STORAGE_CONNECTION_STRING
    container_name = settings.AZURE_CONTAINER_NAME
    if not conn_str:
        logger.warning("AZURE_STORAGE_CONNECTION_STRING is not configured")
        return None

    blob_path = _resolve_blob_path(path_or_url, container_name)
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


def _compress_image_to_base64(image_bytes: bytes) -> str:
    """Compress image bytes to a JPEG thumbnail and return base64 data URI."""
    from PIL import Image

    img = Image.open(io.BytesIO(image_bytes))
    img = img.convert("RGB")
    img.thumbnail(THUMBNAIL_MAX_SIZE, Image.LANCZOS)
    buffer = io.BytesIO()
    img.save(buffer, format="JPEG", quality=THUMBNAIL_JPEG_QUALITY, optimize=True)
    b64 = base64.b64encode(buffer.getvalue()).decode("ascii")
    return f"data:image/jpeg;base64,{b64}"


def _fetch_and_compress_blob(path_or_url: str) -> str | None:
    """Fetch blob from Azure and compress to base64 thumbnail."""
    image_bytes = _fetch_blob_bytes_from_azure(path_or_url)
    if not image_bytes:
        return None
    try:
        return _compress_image_to_base64(image_bytes)
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
    sql = f"""
        SELECT id, file_type, file_url, thumbnail_url
        FROM {schema}.files
        WHERE id IN ({placeholders})
        ORDER BY sort_order ASC;
    """
    cursor.execute(sql, file_ids)
    return [dict(row) for row in cursor.fetchall()]


def _pick_thumbnail_source_for_event(files: list[dict[str, Any]]) -> str | None:
    """Pick blob path/URL for an event card: prefer IMAGE, fallback to video thumbnail."""
    for f in files:
        if f["file_type"] == "IMAGE" and f.get("file_url"):
            return f["file_url"]
    for f in files:
        if f["file_type"] == "VIDEO" and f.get("thumbnail_url"):
            return f["thumbnail_url"]
    return None


def _pick_thumbnail_source_for_document(files: list[dict[str, Any]]) -> str | None:
    """Pick blob path/URL for a flyer document card."""
    for f in files:
        if f["file_type"] == "IMAGE" and f.get("file_url"):
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
) -> dict[str, Any]:
    doc_file_map = doc_file_map or {}
    event_file_map = event_file_map or {}

    documents: list[dict[str, Any]] = []
    for row in doc_rows:
        doc_type = str(row["document_type"])
        if doc_type not in ALLOWED_WEEKLY_DOCUMENT_TYPES:
            continue
        tags = _safe_tags(row["tags"])[:3]
        doc_id = int(row["document_id"])
        thumbnail_b64 = doc_file_map.get(doc_id) if doc_type == "FLYER" else None
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
                "thumbnail_base64": thumbnail_b64,
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
                "thumbnail_base64": event_file_map.get(event_id),
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
            for row in doc_rows:
                doc_type = str(row["document_type"])
                if doc_type != "FLYER":
                    continue
                file_ids = _parse_file_ids(row.get("file_ids"))
                if not file_ids:
                    continue
                files = _fetch_files_for_ids(cur, file_ids, "documents")
                blob_source = _pick_thumbnail_source_for_document(files)
                if blob_source:
                    doc_file_map[int(row["document_id"])] = _fetch_and_compress_blob(blob_source)

            # Fetch file thumbnails for events
            event_file_map: dict[int, str | None] = {}
            for row in event_rows:
                file_ids = _parse_file_ids(row.get("file_ids"))
                if not file_ids:
                    continue
                files = _fetch_files_for_ids(cur, file_ids, "events")
                blob_source = _pick_thumbnail_source_for_event(files)
                if blob_source:
                    event_file_map[int(row["event_id"])] = _fetch_and_compress_blob(blob_source)

    return _build_payload_from_rows(
        doc_rows,
        event_rows,
        start_utc=start_utc,
        end_utc=end_utc,
        base_url=base_url,
        doc_file_map=doc_file_map,
        event_file_map=event_file_map,
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
) -> Any:
    """
    Send HTML email through Azure Communication Services Email.

    Returns the ACS send result from poller.result().
    """
    client = create_acs_email_client(connection_string)
    message = {
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
    use_sample_data: bool = True,
) -> dict[str, Any]:
    """
    Build weekly digest payload + HTML, then send via ACS (sync flow).

    Set use_sample_data=False to render real DB payload instead of demo cards.
    """
    payload = build_weekly_digest_payload_sync(
        db_config,
        reference_utc=reference_utc,
        base_url=base_url,
    )
    html = build_weekly_digest_html(
        payload,
        banner_image_url=banner_image_url,
        use_sample_data=use_sample_data,
    )
    send_result = send_html_email_via_acs(
        connection_string=connection_string,
        sender_address=sender_address,
        to_addresses=to_addresses,
        cc_addresses=cc_addresses,
        bcc_addresses=bcc_addresses,
        subject=subject,
        html_content=html,
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
    use_sample_data: bool = True,
) -> dict[str, Any]:
    """
    Async wrapper for sync build+send flow using ThreadPoolExecutor(max_workers=10).

    Set use_sample_data=False to render real DB payload instead of demo cards.
    """
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(
        DIGEST_EXECUTOR,
        lambda: build_and_send_weekly_digest_sync(
            db_config=db_config,
            connection_string=connection_string,
            sender_address=sender_address,
            to_addresses=to_addresses,
            cc_addresses=cc_addresses,
            bcc_addresses=bcc_addresses,
            subject=subject,
            base_url=base_url,
            banner_image_url=banner_image_url,
            reference_utc=reference_utc,
            use_sample_data=use_sample_data,
        ),
    )


def _render_doc_card(item: dict[str, Any]) -> str:
    thumbnail = item.get("thumbnail_base64")
    doc_type = item.get("document_type", "")
    is_flyer = doc_type == "FLYER"
    tags = item.get("tags") or []

    if is_flyer and thumbnail:
        # Flyer card: image + name + arrow link (same layout as event cards)
        return (
            '<table role="presentation" class="kh-card" width="100%" cellpadding="0" cellspacing="0" '
            'border="0" style="background-color:#ffffff; border:1px solid #E0E8F0; border-radius:6px;">'
            '<tr><td style="line-height:0;">'
            f'<img src="{thumbnail}" width="100%" alt="{escape(item["name"])}" '
            'style="display:block; width:100%; height:auto; aspect-ratio:4/3; '
            'object-fit:cover; border-radius:6px 6px 0 0;">'
            '</td></tr>'
            '<tr><td style="padding:8px 10px 10px 10px; font-family:Arial,Helvetica,sans-serif;">'
            '<table role="presentation" cellpadding="0" cellspacing="0" border="0"><tr>'
            '<td bgcolor="#2B6CB0" style="padding:2px 8px; border-radius:3px;">'
            f'<span style="font-size:10px; font-weight:bold; color:#ffffff; text-transform:uppercase; '
            f'letter-spacing:0.4px;">{escape(item["document_type_label"])}</span>'
            '</td></tr></table>'
            f'<span style="display:block; font-size:13px; font-weight:bold; color:#111111; margin-top:6px; '
            f'mso-line-height-rule:exactly; line-height:18px; overflow:hidden;">{escape(item["name"])}</span>'
            '<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" style="margin-top:6px;">'
            '<tr><td align="right">'
            f'<a href="{escape(item["link"])}" class="arrow-link" style="display:inline-block; '
            'font-family:Arial,Helvetica,sans-serif; font-size:16px; color:#2B6CB0; font-weight:bold; '
            'text-decoration:none;">&rarr;</a>'
            '</td></tr></table>'
            '</td></tr></table>'
        )

    # Non-flyer card: text-only with type badge, name, tags, description, link
    tag_html = ""
    if tags:
        tag_parts = " &middot; ".join(escape(str(t)) for t in tags)
        tag_html = (
            f'<span style="display:block; font-size:11px; color:#2B6CB0; margin-top:6px; '
            f'overflow:hidden;">{tag_parts}</span>'
        )

    description = item.get("description", "")
    desc_html = ""
    if description:
        desc_html = (
            f'<span style="display:block; font-size:12px; line-height:17px; color:#555555; '
            f'margin-top:5px; overflow:hidden; max-height:34px;">{escape(description)}</span>'
        )

    return (
        '<table role="presentation" class="kh-card" width="100%" cellpadding="0" cellspacing="0" '
        'border="0" style="background-color:#ffffff; border:1px solid #E0E8F0; border-radius:6px;">'
        '<tr><td style="padding:8px 10px 10px 10px; font-family:Arial,Helvetica,sans-serif;">'
        '<table role="presentation" cellpadding="0" cellspacing="0" border="0"><tr>'
        '<td bgcolor="#2B6CB0" style="padding:2px 8px; border-radius:3px;">'
        f'<span style="font-size:10px; font-weight:bold; color:#ffffff; text-transform:uppercase; '
        f'letter-spacing:0.4px;">{escape(item["document_type_label"])}</span>'
        '</td></tr></table>'
        f'<span style="display:block; font-size:13px; font-weight:bold; color:#111111; margin-top:6px; '
        f'mso-line-height-rule:exactly; line-height:18px; overflow:hidden;">{escape(item["name"])}</span>'
        f'{tag_html}'
        f'{desc_html}'
        '<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" style="margin-top:6px;">'
        '<tr><td align="right">'
        f'<a href="{escape(item["link"])}" class="arrow-link" style="display:inline-block; '
        'font-family:Arial,Helvetica,sans-serif; font-size:16px; color:#2B6CB0; font-weight:bold; '
        'text-decoration:none;">&rarr;</a>'
        '</td></tr></table>'
        '</td></tr></table>'
    )


def _render_event_card(item: dict[str, Any]) -> str:
    thumbnail = item.get("thumbnail_base64")
    image_html = ""
    if thumbnail:
        image_html = (
            '<tr><td style="line-height:0;">'
            f'<img src="{thumbnail}" width="100%" alt="{escape(item["name"])}" '
            'style="display:block; width:100%; height:auto; aspect-ratio:4/3; '
            'object-fit:cover; border-radius:6px 6px 0 0;">'
            '</td></tr>'
        )

    return (
        '<table role="presentation" class="ev-card" width="100%" cellpadding="0" cellspacing="0" '
        'border="0" style="background-color:#ffffff; border:1px solid #E0E8F0; border-radius:6px;">'
        f'{image_html}'
        '<tr><td style="padding:8px 10px 10px 10px; font-family:Arial,Helvetica,sans-serif;">'
        f'<span style="display:block; font-size:13px; font-weight:bold; color:#111111; '
        f'mso-line-height-rule:exactly; line-height:18px; overflow:hidden;">{escape(item["name"])}</span>'
        '<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" style="margin-top:6px;">'
        '<tr><td align="right">'
        f'<a href="{escape(item["link"])}" class="arrow-link" style="display:inline-block; '
        'font-family:Arial,Helvetica,sans-serif; font-size:16px; color:#2B6CB0; font-weight:bold; '
        'text-decoration:none;">&rarr;</a>'
        '</td></tr></table>'
        '</td></tr></table>'
    )




def _sample_digest_items() -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Demo Knowledge Hub + Events cards for HTML preview / local testing."""
    sample_knowledge_hub = [
        {
            "heading": "New flyer available",
            "name": "Critical Third-Party Cyber Risk Awareness Flyer for Multi-Entity Compliance and Continuous Monitoring Excellence",
            "document_type": "FLYER",
            "document_type_label": "Flyer",
            "description": "A detailed communication flyer explaining cross-functional due diligence, escalation protocols, and continuous observation requirements for high-risk third-party onboarding and lifecycle governance.",
            "tags": ["Cyber Risk", "Third Party", "Awareness"],
            "link": "https://ecp.com/flyer/1001",
            "thumbnail_base64": None,
            "_index": 0,
        },
        {
            "heading": "New Policy, Law regulation available",
            "name": "Enterprise Policy on Data Protection, Consent Governance, and Cross-Border Information Processing Controls",
            "document_type": "POLICY",
            "document_type_label": "Policy",
            "description": "This policy defines long-form obligations for teams handling personally identifiable data, mandatory retention boundaries, internal approval controls, and legal review checkpoints.",
            "tags": ["Data Privacy", "Policy", "Governance"],
            "link": "https://ecp.com/policy/1002",
            "thumbnail_base64": None,
            "_index": 1,
        },
        {
            "heading": "New training material available",
            "name": "Advanced Training Material for Regulatory Reporting Accuracy, Audit Readiness, and Exception Handling Procedures",
            "document_type": "TRAINING_MATERIAL",
            "document_type_label": "Training Material",
            "description": "Comprehensive training content covering scenario-based reporting practices, validation workflows, and long-text guidance for correcting filing exceptions without timeline slippage.",
            "tags": ["Training", "Reporting", "Audit"],
            "link": "https://ecp.com/training_material/1003",
            "thumbnail_base64": None,
            "_index": 2,
        },
        {
            "heading": "New Policy, Law regulation available",
            "name": "Updated Anti-Bribery and Conflict-of-Interest Policy for Vendor Engagement, Entertainment, and Hospitality Disclosures",
            "document_type": "POLICY",
            "document_type_label": "Policy",
            "description": "A practical policy update that clarifies declaration thresholds, investigative responsibilities, and periodic attestation requirements across procurement and business support functions.",
            "tags": ["Ethics", "Policy", "Vendors"],
            "link": "https://ecp.com/policy/1004",
            "thumbnail_base64": None,
            "_index": 3,
        },
        {
            "heading": "New flyer available",
            "name": "Information Security Incident Reporting Flyer for Rapid Internal Notification and Coordinated Compliance Response",
            "document_type": "FLYER",
            "document_type_label": "Flyer",
            "description": "An operational flyer that lists immediate reporting channels, evidence preservation reminders, and communication checkpoints to support timely legal and compliance intervention.",
            "tags": ["Incident", "Security", "Response"],
            "link": "https://ecp.com/flyer/1005",
            "thumbnail_base64": None,
            "_index": 4,
        },
    ]
    sample_events = [
        {
            "name": "Compliance Townhall on Emerging Regulatory Trends, Supervisory Expectations, and Cross-Border Governance Preparedness",
            "description": "A broad leadership session to discuss major regulatory developments, practical controls alignment, and sustained evidence practices for internal and external stakeholder confidence.",
            "link": "https://ecp.com/events/2001",
            "thumbnail_base64": None,
            "_index": 0,
        },
        {
            "name": "Hands-On Workshop for Case Management Documentation Quality and Risk-Based Escalation Decisioning",
            "description": "Interactive workshop focused on drafting robust case narratives, documenting rationale clearly, and improving escalation quality for complex multi-factor incidents.",
            "link": "https://ecp.com/events/2002",
            "thumbnail_base64": None,
            "_index": 1,
        },
        {
            "name": "Training Session on Investigative Interview Standards, Evidence Integrity, and Defensible Closure Reporting",
            "description": "A scenario-rich program that provides practical methods for interview preparation, evidence chain handling, and producing closure reports that withstand review.",
            "link": "https://ecp.com/events/2003",
            "thumbnail_base64": None,
            "_index": 2,
        },
        {
            "name": "Panel Discussion on Internal Controls Optimization, Policy Usability, and Department-Wide Adoption Strategy",
            "description": "Cross-team discussion around balancing control strength with operational usability, including examples of successful rollout playbooks and accountability models.",
            "link": "https://ecp.com/events/2004",
            "thumbnail_base64": None,
            "_index": 3,
        },
        {
            "name": "Knowledge Sharing Forum for Lessons Learned from Recent Audit Observations and Corrective Action Execution",
            "description": "An extended knowledge forum to review recurring audit findings, strong remediation approaches, and methods to prevent repeat observations through durable ownership.",
            "link": "https://ecp.com/events/2005",
            "thumbnail_base64": None,
            "_index": 4,
        },
    ]
    return sample_knowledge_hub, sample_events


def _with_card_index(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Attach gradient index for card styling without mutating original rows."""
    out: list[dict[str, Any]] = []
    for idx, item in enumerate(items):
        row = dict(item)
        row["_index"] = idx
        out.append(row)
    return out


def _render_events_grid(cards: list[str]) -> str:
    """Render event cards in a 2-column grid layout."""
    if not cards:
        return (
            '<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0">'
            '<tr><td style="padding:20px 40px; font-family:Arial,Helvetica,sans-serif; font-size:14px; color:#A8CCE8;">'
            'No events this week.</td></tr></table>'
        )
    rows_html = ""
    for i in range(0, len(cards), 2):
        left = cards[i]
        right = cards[i + 1] if i + 1 < len(cards) else ""
        right_cell = (
            f'<td class="stack-col" valign="top" width="50%" style="width:50%; padding-left:8px;">{right}</td>'
            if right
            else '<td class="stack-col" valign="top" width="50%" style="width:50%; padding-left:8px;"></td>'
        )
        rows_html += (
            '<tr>'
            '<td class="mobile-pad" style="padding:10px 40px 0 40px;">'
            '<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0"><tr>'
            f'<td class="stack-col col-pad-right" valign="top" width="50%" style="width:50%; padding-right:8px;">{left}</td>'
            f'{right_cell}'
            '</tr></table></td></tr>'
        )
    return rows_html


def _render_knowledge_grid(cards: list[str]) -> str:
    """Render knowledge hub cards in a 2-column grid layout."""
    if not cards:
        return (
            '<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0">'
            '<tr><td style="padding:20px 40px; font-family:Arial,Helvetica,sans-serif; font-size:14px; color:#A8CCE8;">'
            'No Knowledge Hub items this week.</td></tr></table>'
        )
    rows_html = ""
    for i in range(0, len(cards), 2):
        left = cards[i]
        right = cards[i + 1] if i + 1 < len(cards) else ""
        right_cell = (
            f'<td class="stack-col" valign="top" width="50%" style="width:50%; padding-left:8px;">{right}</td>'
            if right
            else '<td class="stack-col" valign="top" width="50%" style="width:50%; padding-left:8px;"></td>'
        )
        rows_html += (
            '<tr>'
            '<td class="mobile-pad" style="padding:10px 40px 0 40px;">'
            '<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0"><tr>'
            f'<td class="stack-col col-pad-right" valign="top" width="50%" style="width:50%; padding-right:8px;">{left}</td>'
            f'{right_cell}'
            '</tr></table></td></tr>'
        )
    return rows_html


def build_weekly_digest_html(
    payload: dict[str, Any],
    *,
    banner_image_url: str | None = None,
    use_sample_data: bool = True,
) -> str:
    """
    Build Outlook-safe HTML digest using the new full-width dark template.

    use_sample_data=True  -> demo cards (preview / local test)
    use_sample_data=False -> real payload from DB
    """
    if use_sample_data:
        knowledge_hub, events = _sample_digest_items()
    else:
        knowledge_hub = _with_card_index(list(payload.get("knowledge_hub") or []))
        events = _with_card_index(list(payload.get("events") or []))

    period_label = ""
    if payload and payload.get("period"):
        period_label = payload["period"].get("label", "")

    knowledge_cards = [_render_doc_card(item) for item in knowledge_hub]
    event_cards = [_render_event_card(item) for item in events]

    events_grid = _render_events_grid(event_cards)
    knowledge_grid = _render_knowledge_grid(knowledge_cards)

    return f"""<!DOCTYPE html>
<html lang="en" xmlns:v="urn:schemas-microsoft-com:vml" xmlns:o="urn:schemas-microsoft-com:office:office">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<meta http-equiv="X-UA-Compatible" content="IE=edge">
<meta name="color-scheme" content="light dark">
<meta name="supported-color-schemes" content="light dark">
<title>MSIL Compliance Weekly Digest</title>
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
  body, table, td, a {{ -webkit-text-size-adjust: 100%; -ms-text-size-adjust: 100%; }}
  table, td {{ mso-table-lspace: 0pt; mso-table-rspace: 0pt; }}
  img {{ -ms-interpolation-mode: bicubic; border: 0; height: auto; line-height: 100%; outline: none; text-decoration: none; }}
  body {{ margin: 0; padding: 0; width: 100% !important; height: 100% !important; }}
  a {{ text-decoration: none; }}
  .arrow-link:hover {{ opacity: 0.7; }}
  .ev-card:hover, .kh-card:hover {{ box-shadow: 0 4px 16px rgba(0,50,120,0.15); }}
  @media screen and (max-width: 680px) {{
    .email-wrapper {{ width: 100% !important; }}
    .stack-col {{ display: block !important; width: 100% !important; max-width: 100% !important; }}
    .col-pad-right {{ padding-right: 0 !important; padding-bottom: 12px !important; }}
    .mobile-pad {{ padding-left: 16px !important; padding-right: 16px !important; }}
    .banner-title {{ font-size: 26px !important; }}
    .banner-cell {{ padding: 60px 20px 70px 20px !important; }}
  }}
</style>
</head>
<body style="margin:0; padding:0; -webkit-font-smoothing:antialiased; background-color:#0B1D3A;">

<div style="display:none; max-height:0; overflow:hidden; mso-hide:all; font-size:1px; line-height:1px; color:#0B1D3A;">
Your Weekly Digest: Events &amp; Knowledge Hub updates from MSIL Compliance.&nbsp;&zwnj;&nbsp;&zwnj;&nbsp;&zwnj;&nbsp;&zwnj;&nbsp;&zwnj;
</div>

<!--[if mso]>
<v:background xmlns:v="urn:schemas-microsoft-com:vml" fill="t">
<v:fill type="tile" color="#0B1D3A"/>
</v:background>
<![endif]-->

<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" style="width:100%; min-width:100%;">
<tr>
<td align="center" valign="top" style="padding:0;">

<table role="presentation" class="email-wrapper" width="100%" cellpadding="0" cellspacing="0" border="0" style="width:100%; max-width:100%;">

<!-- BANNER -->
<tr>
<td style="line-height:0; background-color:#0D2240;">
<!--[if mso]>
<v:rect xmlns:v="urn:schemas-microsoft-com:vml" fill="true" stroke="false" style="width:100%; height:220px;">
<v:fill type="gradient" color="#0D2240" color2="#1A4080"/>
<v:textbox inset="0,0,0,0" style="mso-fit-shape-to-text:true">
<![endif]-->
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" style="background:linear-gradient(135deg, #0D2240 0%, #1A4A8A 50%, #2B6CB0 100%);">
<tr>
<td class="banner-cell" align="center" style="padding:80px 40px 90px 40px;">
<table role="presentation" cellpadding="0" cellspacing="0" border="0">
<tr>
<td align="center" style="font-family:Arial,Helvetica,sans-serif;">
<span class="banner-title" style="display:block; font-size:34px; font-weight:bold; color:#ffffff; letter-spacing:1px; mso-line-height-rule:exactly; line-height:42px;">MSIL Compliance Weekly Digest</span>
<span style="display:block; font-size:14px; color:#A8CCE8; margin-top:6px; letter-spacing:0.5px; mso-line-height-rule:exactly; line-height:20px;">Events &amp; Knowledge Hub updates &mdash; {escape(period_label) if period_label else "this week"}</span>
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
</tr>

<!-- EVENTS SECTION HEADING -->
<tr>
<td class="mobile-pad" style="padding:28px 40px 6px 40px;">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0">
<tr>
<td style="padding-bottom:4px;">
<span style="font-family:Arial,Helvetica,sans-serif; font-size:18px; font-weight:bold; color:#ffffff; letter-spacing:0.5px;">This Week's Events</span>
</td>
</tr>
</table>
</td>
</tr>

<!-- EVENTS GRID -->
{events_grid}

<!-- SPACER -->
<tr><td style="padding:14px 0 0 0; font-size:1px; line-height:1px;">&nbsp;</td></tr>

<!-- KNOWLEDGE HUB SECTION HEADING -->
<tr>
<td class="mobile-pad" style="padding:8px 40px 6px 40px;">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0">
<tr>
<td style="padding-bottom:4px;">
<span style="font-family:Arial,Helvetica,sans-serif; font-size:18px; font-weight:bold; color:#ffffff; letter-spacing:0.5px;">Knowledge Hub</span>
</td>
</tr>
</table>
</td>
</tr>

<!-- KNOWLEDGE HUB GRID -->
{knowledge_grid}

<!-- FOOTER -->
<tr>
<td style="padding:32px 40px 28px 40px;">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0">
<tr>
<td style="border-top:1px solid rgba(255,255,255,0.15); padding-top:20px; font-family:Arial,Helvetica,sans-serif;">
<span style="display:block; font-size:14px; color:#ffffff; padding-bottom:10px;">Regards,<br><strong>Compliance Team</strong></span>
<span style="display:block; font-size:11px; line-height:18px; color:#6A8EAE;">
This is a weekly digest sent to all employees. You are receiving this because you are part of the organization&rsquo;s distribution list.<br>
MSIL Corporate Office, Compliance Division
</span>
</td>
</tr>
</table>
</td>
</tr>

</table>
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
    use_sample_data: bool = True,
) -> tuple[dict[str, Any], str]:
    payload = await build_weekly_digest_payload(
        db_config,
        reference_utc=reference_utc,
        base_url=base_url,
    )
    html = build_weekly_digest_html(
        payload,
        banner_image_url=banner_image_url,
        use_sample_data=use_sample_data,
    )
    return payload, html
