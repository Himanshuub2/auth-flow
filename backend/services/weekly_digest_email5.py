from __future__ import annotations

import asyncio
import base64
import importlib
import io
import json
import logging
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, time, timedelta, timezone
from typing import Any
from pathlib import Path
from urllib.parse import unquote

from jinja2 import Template

from .azure_secrets import get_secret_sync
from core.constants import DB_NAME, DB_PORT, GENERIC_EMAIL, BASE_URL

IST = timezone(timedelta(hours=5, minutes=30))

logger = logging.getLogger(__name__)

DOCUMENT_TYPE_LABELS: dict[str, str] = {
    "POLICY": "Policy",
    "GUIDANCE_NOTE": "Guidance Notes",
    "LAW_REGULATION": "Law &amp; Regulation",
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


EMAIL_MAX_WIDTH = "100%"
THUMBNAIL_MAX_W = 560
THUMBNAIL_MAX_H = 420  # taller 4:3 crop — more height than 16:9
THUMBNAIL_JPEG_QUALITY = 84
CARD_INNER_PAD_V = 12
EMAIL_CONTAINER_WIDTH = 760  # wider shell so column images read larger

CONTENT_H_PAD = "12px"

# ---------------------------------------------------------------------------
# Full-bleed bg2.jpg behind the whole shell (inline CID + VML for classic
# Outlook so the image covers the reading pane on window resize). Events /
# Flyers sit directly on the bg (no card chrome); Policy cards stay frosted.
# ---------------------------------------------------------------------------
BODY_BG_COLOR = "#024579"           # matches bg2.jpg bottom tone (seamless overflow blend)
DIGEST_BG_CID = "digest-wave-bg"
DIGEST_BG_ASSET = "bg2.jpg"
# Max edge for the attached bg JPEG (keeps message size reasonable).
DIGEST_BG_MAX_EDGE = 1400
DIGEST_BANNER_CID = "digest-wave-banner"
DIGEST_BANNER_ASSET = "digest_wave_banner.png"
DIGEST_BANNER_WIDTH = EMAIL_CONTAINER_WIDTH  # full shell width in Outlook
# Frosted glass cards — soft periwinkle / indigo mist to match the shining-blue bg
# (classic Outlook ignores backdrop-filter; solid fallbacks below).
CARD_BG = "rgba(232,228,255,0.78)"
CARD_BG_MSO = "#e8e4ff"
CARD_BLUR = (
    "backdrop-filter:blur(14px); -webkit-backdrop-filter:blur(14px);"
)
CARD_BORDER = "rgba(165,180,252,0.95)"
CARD_SHADOW = "0 8px 24px rgba(49,46,129,0.28)"
CARD_ACCENT = "#4f46e5"
CARD_LABEL = "#1e1b4b"
CARD_TEXT = "#312e81"
CARD_RADIUS = "18px"
IMAGE_RADIUS = "18px"
# Soft tint behind image + frosted text pad (modern only).
CARD_IMAGE_TINT = "rgba(199,210,254,0.60)"
CARD_IMAGE_TINT_MSO = "#c7d2fe"
CARD_TEXT_BG = "rgba(245,243,255,0.70)"
CARD_TEXT_BG_MSO = "#f5f3ff"
SECTION_TITLE_COLOR = "#4338ca"
COL_HEADER_COLOR = "#ffffff"
COL_GAP = "8px"
CARD_GAP = "30px"
IMAGE_GAP_V = "0"  # no padding around images — flush to card edges
LINK_COLOR = "#4f46e5"
ACCENT_CYAN = "#0891b2"
ACCENT_VIOLET = "#7c3aed"

HERO_TEXT = "#ffffff"
HERO_SUBTEXT = "#ffffff"
# Event/flyer titles sit directly on the dark bg — white + shadow for contrast
# in both light and dark client modes.
SIMPLE_TITLE_COLOR = "#ffffff"
SIMPLE_TITLE_SHADOW = (
    "text-shadow:0 1px 3px rgba(0,0,0,0.9), 0 0 1px rgba(0,0,0,1);"
)

FOOTER_BG = "rgba(8,20,64,0.55)"
FOOTER_TEXT = "#ffffff"
FOOTER_SUBTEXT = "#c3d4fb"

TITLE_MAX_CHARS = 46
DESCRIPTION_MAX_CHARS = 90
MAX_COLUMN_ITEMS = 5

# Outlook-safe system font stacks (no web fonts — Outlook desktop cannot load
# custom/Google fonts and would just fall back anyway).
_FONT_DISPLAY = "Calibri, 'Segoe UI Semibold', Segoe UI, Optima, Candara, Arial, sans-serif"
_FONT_BODY = "Calibri, Segoe UI, Candara, Tahoma, Arial, sans-serif"

_TEXT_WRAP_STYLE = (
    "word-wrap:break-word; overflow-wrap:anywhere; word-break:break-word; "
    "white-space:normal; max-width:100%;"
)

_ASSETS_DIR = Path(__file__).resolve().parent / "assets"


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


def _inline_png_attachment(content_id: str, png_bytes: bytes, filename: str) -> dict[str, str]:
    return {
        "name": filename,
        "contentType": "image/png",
        "contentInBase64": base64.b64encode(png_bytes).decode("ascii"),
        "contentId": content_id,
    }


def _browser_html_from_email(
    html_content: str,
    inline_attachments: list[dict[str, str]] | None = None,
) -> str:
    """Replace cid: image refs with data URIs so the .html opens correctly in a browser."""
    out = html_content
    for att in inline_attachments or []:
        cid = (att.get("contentId") or "").strip()
        b64 = att.get("contentInBase64") or ""
        ctype = att.get("contentType") or "image/jpeg"
        if not cid or not b64:
            continue
        out = out.replace(f"cid:{cid}", f"data:{ctype};base64,{b64}")
    return out


def _html_file_attachment(
    html_content: str,
    *,
    filename: str = "MSIL-Weekly-Digest.html",
) -> dict[str, str]:
    """Regular downloadable .html attachment (no contentId → ACS treats as file, not inline)."""
    return {
        "name": filename,
        "contentType": "text/html",
        "contentInBase64": base64.b64encode(
            html_content.encode("utf-8")
        ).decode("ascii"),
    }


def _email_bg_bytes() -> bytes:
    """Load bg2.jpg as the full-bleed email background (Outlook-safe JPEG).

    Downscales the asset so the inline attachment stays small enough for ACS
    while remaining sharp on a typical reading pane. Fallback color is
    BODY_BG_COLOR (bottom tone of the image).
    """
    from PIL import Image

    path = _ASSETS_DIR / DIGEST_BG_ASSET
    img = Image.open(path).convert("RGB")
    img.thumbnail((DIGEST_BG_MAX_EDGE, DIGEST_BG_MAX_EDGE * 2), Image.LANCZOS)
    buffer = io.BytesIO()
    img.save(buffer, format="JPEG", quality=82, optimize=True)
    return buffer.getvalue()


def _digest_bg_inline_attachment() -> dict[str, str]:
    return _inline_attachment(DIGEST_BG_CID, _email_bg_bytes())


def _email_banner_bytes() -> bytes:
    """Load digest_wave_banner.png for the top-of-email banner."""
    path = _ASSETS_DIR / DIGEST_BANNER_ASSET
    return path.read_bytes()


def _digest_banner_inline_attachment() -> dict[str, str]:
    return _inline_png_attachment(
        DIGEST_BANNER_CID,
        _email_banner_bytes(),
        DIGEST_BANNER_ASSET,
    )


def _ensure_digest_static_attachments(
    inline_attachments: list[dict[str, str]],
) -> list[dict[str, str]]:
    """Append bundled bg2.jpg background + wave banner image."""
    attachments = list(inline_attachments)
    existing = {att.get("contentId") for att in attachments}
    if DIGEST_BG_CID not in existing:
        attachments.append(_digest_bg_inline_attachment())
    if DIGEST_BANNER_CID not in existing:
        attachments.append(_digest_banner_inline_attachment())
    return attachments


def _ensure_digest_banner_attachment(
    inline_attachments: list[dict[str, str]],
) -> list[dict[str, str]]:
    """Backward-compatible alias for static digest assets."""
    return _ensure_digest_static_attachments(inline_attachments)


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
    """Resize/crop to a clean 4:3 landscape JPEG that fits its card.

    Corners are rounded purely via CSS (border-radius) on the <img> tag rather
    than baked into the JPEG.
    """
    from PIL import Image

    img = Image.open(io.BytesIO(image_bytes))
    img = img.convert("RGB")

    w, h = img.size
    target_ratio = THUMBNAIL_MAX_W / THUMBNAIL_MAX_H  # 4:3 — wider + taller cards
    current_ratio = w / h

    if current_ratio > target_ratio:
        new_w = int(h * target_ratio)
        left = (w - new_w) // 2
        img = img.crop((left, 0, left + new_w, h))
    else:
        new_h = int(w / target_ratio)
        top = (h - new_h) // 2
        img = img.crop((0, top, w, top + new_h))

    img = img.resize((THUMBNAIL_MAX_W, THUMBNAIL_MAX_H), Image.LANCZOS)

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

    flyers: list[dict[str, Any]] = []
    policy_others: list[dict[str, Any]] = []
    for row in doc_rows:
        doc_type = str(row["document_type"])
        if doc_type not in ALLOWED_WEEKLY_DOCUMENT_TYPES:
            continue
        tags = _safe_tags(row["tags"])[:3]
        doc_id = int(row["document_id"])
        thumbnail_cid = doc_file_map.get(doc_id) if doc_type == "FLYER" else None
        item = {
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
        if doc_type == "FLYER":
            flyers.append(item)
        else:
            policy_others.append(item)

    flyers.sort(key=lambda d: (0 if d.get("thumbnail_cid") else 1, str(d.get("name") or "").lower()))
    flyers = flyers[:MAX_COLUMN_ITEMS]
    policy_others.sort(key=lambda d: str(d.get("name") or "").lower())
    policy_others = policy_others[:MAX_COLUMN_ITEMS]

    events: list[dict[str, Any]] = []
    for row in event_rows:
        event_id = int(row["event_id"])
        thumbnail_cid = event_file_map.get(event_id)
        if not thumbnail_cid:
            continue
        events.append(
            {
                "id": event_id,
                "name": row["event_name"],
                "description": row["description"] or "",
                "heading": "New Event(s) added",
                "link": _event_link(base_url, event_id),
                "created_at_utc": row["created_at"].isoformat() if row["created_at"] else None,
                "thumbnail_cid": thumbnail_cid,
            }
        )
        if len(events) >= MAX_COLUMN_ITEMS:
            break

    all_docs = flyers + policy_others

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
        "knowledge_hub": all_docs,
        "flyers": flyers,
        "policy_others": policy_others,
        "events": events,
        "base_url": base_url,
        "inline_attachments": _ensure_digest_static_attachments(inline_attachments),
        "counts": {
            "knowledge_hub": len(all_docs),
            "flyers": len(flyers),
            "policy_others": len(policy_others),
            "events": len(events),
            "total": len(all_docs) + len(events),
        },
        "has_content": bool(all_docs or events),
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
    inline = list(payload.get("inline_attachments") or [])
    # Downloadable .html only (plus existing inline images for the email body).
    # CID refs are inlined as data URIs so the file opens correctly in a browser.
    browser_html = _browser_html_from_email(html, inline)
    attachments = inline + [_html_file_attachment(browser_html)]
    send_result = send_html_email_via_acs(
        connection_string=connection_string,
        sender_address=sender_address,
        to_addresses=to_addresses,
        cc_addresses=cc_addresses,
        bcc_addresses=bcc_addresses,
        subject=subject,
        html_content=html,
        inline_attachments=attachments,
        plain_text=(
            "Weekly Knowledge Hub and Events digest is available. "
            "Please review the latest highlights. "
            "An HTML copy is attached for viewing in a browser."
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


def _prepare_simple_card_item(item: dict[str, Any]) -> dict[str, Any]:
    """Plain-text (unescaped) fields for a 16:9-image + name card; template autoescapes."""
    return {
        "name": _truncate_text(str(item.get("name") or ""), TITLE_MAX_CHARS),
        "link": str(item.get("link") or "#"),
        "thumbnail_cid": item.get("thumbnail_cid"),
    }


def _prepare_detail_card_item(item: dict[str, Any]) -> dict[str, Any]:
    """Plain-text (unescaped) fields for a detail card (no image); template autoescapes."""
    tags = item.get("tags") or []
    tags_str = (
        ", ".join(_truncate_text(str(t), 24) for t in tags[:3]) if tags else "\u2014"
    )
    description = _truncate_text(str(item.get("description") or ""), DESCRIPTION_MAX_CHARS)
    return {
        "name": _truncate_text(str(item.get("name") or ""), TITLE_MAX_CHARS),
        "link": str(item.get("link") or "#"),
        "type_label": str(
            item.get("document_type_label") or item.get("document_type") or "Document"
        ),
        "tags_str": tags_str,
        "description": description or "\u2014",
    }


def _build_columns_context(
    events: list[dict[str, Any]],
    flyers: list[dict[str, Any]],
    policy_others: list[dict[str, Any]],
    base_url: str,
) -> list[dict[str, Any]]:
    """Build the `columns` context passed to the Jinja2 template.

    Every column now always shows a trailing "View all" link (in addition to
    its cards when it has any) so the user has a durable place to configure
    each of the three destination URLs.

    NOTE: column dicts use the key "cards" (not "items") for the card list, since
    Jinja2 attribute-lookup on a plain dict named "items" would collide with the
    built-in dict.items() method and silently break `{% for card in col.items %}`.
    """
    columns = [
        {
            "key": "events",
            "header": "Events",
            "cards": [_prepare_simple_card_item(i) for i in events],
            "card_type": "simple",
            "accent": CARD_ACCENT,
            "view_all_label": "View All Events \u2192",
            "view_all_url": f"{base_url}/events",
        },
        {
            "key": "flyers",
            "header": "Flyers",
            "cards": [_prepare_simple_card_item(i) for i in flyers],
            "card_type": "simple",
            "accent": ACCENT_CYAN,
            "view_all_label": "View All Flyers \u2192",
            "view_all_url": f"{base_url}/flyer",
        },
        {
            "key": "policy",
            "header": "Policy & Others",
            "cards": [_prepare_detail_card_item(i) for i in policy_others],
            "card_type": "detail",
            "accent": ACCENT_VIOLET,
            "view_all_label": "View All Documents \u2192",
            "view_all_url": f"{base_url}/policy",
        },
    ]

    n = len(columns)
    pct = 100 // n if n else 33
    mso_w = (EMAIL_CONTAINER_WIDTH - 2 * 22 - (n - 1) * 14) // n if n else 200
    for col in columns:
        col["pct"] = pct
        col["mso_w"] = mso_w

    return columns


# Single Jinja2 template (jinja2.Template) for the whole digest email. Python only
# computes/prepares context data above; all markup composition lives in this template.
#
# Design: bg2.jpg full-bleed behind the whole shell (CSS cover + VML
# aspect=atleast so classic Outlook covers the reading pane on resize), a
# transparent hero (white text on the image), Events/Flyers as bare image +
# white title (no card chrome), frosted Policy cards, and every column ending
# in a "View all" link. The shell is wider (760px) so there's less dead space on
# large windows, while still shrinking fluidly on small ones.
_DIGEST_EMAIL_TEMPLATE_SRC = """
{#-
  IMPORTANT: real HTML comments (the `<!--[if mso]>...<![endif]-->` trick) cannot
  nest — the first `-->` found closes the *outermost* open comment, no matter how
  deeply "nested" it visually looks in the source. The whole document only uses
  ONE level of these real conditional comments (around the columns table).
  Card/image macros below take an `is_mso` flag and use plain Jinja `{% if %}`
  to choose markup instead of embedding more HTML conditional comments, so
  nothing here can ever prematurely close an outer comment and leak duplicate
  markup into non-Outlook clients.
-#}
{%- macro card_spacer(is_mso) -%}
{%- if is_mso %}
<table width="100%" cellpadding="0" cellspacing="0" border="0" role="presentation"><tr><td height="30" style="height:{{ card_gap }}; line-height:{{ card_gap }}; font-size:0;">&nbsp;</td></tr></table>
{%- endif %}
{%- endmacro -%}

{%- macro card_image(thumbnail_cid, alt_text, link, is_mso) -%}
{%- if is_mso %}
<td align="center" style="padding:0; line-height:0; font-size:0;">
<a href="{{ link }}" target="_blank" style="text-decoration:none; border:0;">
<img class="card-img" src="cid:{{ thumbnail_cid }}" width="{{ mso_thumb_w }}" alt="{{ alt_text }}" border="0" style="display:block; width:100%; max-width:100%; height:auto; border:0; outline:none; text-decoration:none; -ms-interpolation-mode:bicubic;">
</a>
</td>
{%- else %}
<td align="center" style="line-height:0; font-size:0; padding:0;">
<a href="{{ link }}" target="_blank" style="display:block; text-decoration:none; border:0; line-height:0;">
<img class="card-img" src="cid:{{ thumbnail_cid }}" alt="{{ alt_text }}" width="560" border="0" style="display:block; width:100%; max-width:100%; height:auto; min-height:210px; aspect-ratio:4/3; border:0; border-radius:{{ image_radius }}; object-fit:cover;">
</a>
</td>
{%- endif %}
{%- endmacro -%}

{%- macro simple_card(card, is_mso) -%}
{#- No card chrome — thumbnail + white title sit directly on the page bg. -#}
<table width="100%" cellpadding="0" cellspacing="0" border="0" role="presentation" style="border-collapse:collapse; background-color:transparent;{% if not is_mso %} margin-bottom:{{ card_gap }};{% endif %}">
{%- if card.thumbnail_cid %}<tr>{{ card_image(card.thumbnail_cid, card.name, card.link, is_mso) }}</tr>{% endif -%}
<tr>
<td class="force-light-text" style="padding:10px 4px 12px 4px; background-color:transparent; font-family:{{ font_body }}; font-size:14px; line-height:19px; font-weight:700; color:{{ simple_title }}; {{ simple_title_shadow }} {{ text_wrap }}">
<a class="force-light-text" href="{{ card.link }}" target="_blank" style="text-decoration:none; color:{{ simple_title }}; font-weight:700; {{ simple_title_shadow }}">{{ card.name }}</a>
</td></tr>
</table>
{{ card_spacer(is_mso) }}
{%- endmacro -%}

{%- macro field(label, value) -%}
<table width="100%" cellpadding="0" cellspacing="0" border="0" role="presentation" style="margin:0; padding:0;">
<tr><td style="padding:8px 0 0 0; font-family:{{ font_body }}; font-size:12px; line-height:16px; font-weight:700; color:{{ card_accent }}; {{ text_wrap }}">{{ label }}:</td></tr>
<tr><td style="padding:2px 0 0 0; font-family:{{ font_body }}; font-size:12px; line-height:17px; color:{{ card_text }}; {{ text_wrap }}">{{ value }}</td></tr>
</table>
{%- endmacro -%}

{%- macro detail_card(card, is_mso) -%}
{%- if is_mso %}
<table width="100%" cellpadding="0" cellspacing="0" border="0" role="presentation" bgcolor="{{ card_bg_mso }}" style="border-collapse:collapse; border:1px solid {{ card_border_mso }}; background-color:{{ card_bg_mso }};">
{%- else %}
<table width="100%" cellpadding="0" cellspacing="0" border="0" role="presentation" style="background-color:{{ card_bg }}; {{ card_blur }} border:1px solid {{ card_border }}; border-radius:{{ card_radius }}; overflow:hidden; box-shadow:{{ card_shadow }}; border-collapse:separate; margin-bottom:{{ card_gap }};">
{%- endif %}
<tr><td style="padding:3px 0 0 0; background-color:{{ card_accent }}; font-size:0; line-height:0;">&nbsp;</td></tr>
<tr>
{%- if is_mso %}
<td bgcolor="{{ card_text_bg_mso }}" style="padding:14px 16px 16px 16px; background-color:{{ card_text_bg_mso }};">
{%- else %}
<td style="padding:14px 16px 16px 16px; background-color:{{ card_text_bg }}; {{ card_blur }}">
{%- endif %}
<a href="{{ card.link }}" target="_blank" style="display:block; text-decoration:none; color:{{ card_label }};">
<span style="display:block; font-family:{{ font_display }}; font-size:15px; line-height:19px; font-weight:700; color:{{ card_label }}; padding-bottom:4px; {{ text_wrap }}">{{ card.name }}</span>
</a>
{{ field("Type", card.type_label) }}
{{ field("Tags", card.tags_str) }}
{{ field("Description", card.description) }}
</td></tr>
</table>
{{ card_spacer(is_mso) }}
{%- endmacro -%}

{%- macro view_all_button(label, url) -%}
<table width="100%" cellpadding="0" cellspacing="0" border="0" role="presentation" style="margin-top:2px;">
<tr><td align="center" style="padding:6px 0 4px 0;">
<a href="{{ url }}" target="_blank" style="display:inline-block; width:100%; box-sizing:border-box; text-align:center; font-family:{{ font_body }}; font-size:13px; font-weight:700; color:#ffffff; background-color:{{ link_color }}; padding:11px 14px; border-radius:22px; text-decoration:none;">{{ label }}</a>
</td></tr></table>
{%- endmacro -%}

{%- macro column_header(title, accent) -%}
<td style="padding:0 0 14px 0;">
<table width="100%" cellpadding="0" cellspacing="0" border="0" role="presentation">
<tr>
<td width="5" bgcolor="{{ accent }}" style="width:5px; background-color:{{ accent }}; border-radius:5px; font-size:0; line-height:0;">&nbsp;</td>
<td style="padding:0 0 0 10px; font-family:{{ font_display }}; font-size:17px; line-height:22px; font-weight:700; color:{{ col_header_color }}; text-align:left; {{ text_wrap }}">{{ title }}</td>
</tr></table>
</td>
{%- endmacro -%}

{%- macro build_column(col, is_mso) -%}
<table width="100%" cellpadding="0" cellspacing="0" border="0" role="presentation">
<tr>{{ column_header(col.header, col.accent) }}</tr>
<tr><td style="padding:0;">
{%- for card in col.cards %}
{%- if col.card_type == 'simple' %}{{ simple_card(card, is_mso) }}{% else %}{{ detail_card(card, is_mso) }}{% endif -%}
{%- endfor %}
{{ view_all_button(col.view_all_label, col.view_all_url) }}
</td></tr>
</table>
{%- endmacro -%}

{%- macro wave_banner() -%}
<tr>
<td align="center" style="padding:0; margin:0; width:100%; line-height:0; font-size:0; background-color:transparent;">
<img class="wave-banner" src="cid:{{ banner_cid }}" width="{{ banner_w }}" alt="MSIL Compliance Weekly Digest" border="0" style="display:block; width:100%; max-width:100%; height:auto; border:0; outline:none; text-decoration:none; -ms-interpolation-mode:bicubic;">
</td>
</tr>
{%- endmacro -%}

{%- macro hero_banner() -%}
{{ wave_banner() }}
<tr>
<td align="center" style="padding:0; margin:0; width:100%; background-color:transparent;">
<!--[if mso]>
<table width="100%" cellpadding="0" cellspacing="0" border="0" role="presentation" style="background-color:transparent;"><tr><td style="padding:36px 30px 40px 30px;">
<table width="100%" cellpadding="0" cellspacing="0" border="0" role="presentation">
<tr><td align="center" class="force-light-text" style="padding:0 0 12px 0; font-family:{{ font_display }}; font-size:30px; line-height:36px; font-weight:700; color:{{ hero_text }}; {{ simple_title_shadow }}">MSIL Compliance Weekly Digest</td></tr>
<tr><td align="center" class="force-light-text" style="padding:0 0 8px 0; font-family:{{ font_body }}; font-size:14px; line-height:20px; color:{{ hero_subtext }}; {{ simple_title_shadow }}">Events &amp; Knowledge Hub updates</td></tr>
<tr><td align="center" class="force-light-text" style="padding:0; font-family:{{ font_body }}; font-size:14px; line-height:20px; color:{{ hero_subtext }}; {{ simple_title_shadow }}">{{ period_display }}</td></tr>
</table>
</td></tr></table>
<![endif]-->
<!--[if !mso]><!-->
<table width="100%" cellpadding="0" cellspacing="0" border="0" role="presentation"><tr><td style="padding:36px 30px 40px 30px; background-color:transparent;">
<table width="100%" cellpadding="0" cellspacing="0" border="0" role="presentation">
<tr><td align="center" class="force-light-text hero-title" style="padding:0 0 12px 0; font-family:{{ font_display }}; font-size:30px; line-height:36px; font-weight:700; color:{{ hero_text }}; letter-spacing:0.2px; mso-line-height-rule:exactly; {{ simple_title_shadow }} {{ text_wrap }}">MSIL Compliance Weekly Digest</td></tr>
<tr><td align="center" class="force-light-text" style="padding:0 0 8px 0; font-family:{{ font_body }}; font-size:14px; line-height:20px; color:{{ hero_subtext }}; mso-line-height-rule:exactly; {{ simple_title_shadow }} {{ text_wrap }}">Events &amp; Knowledge Hub updates</td></tr>
<tr><td align="center" class="force-light-text" style="padding:0; font-family:{{ font_body }}; font-size:14px; line-height:20px; color:{{ hero_subtext }}; mso-line-height-rule:exactly; {{ simple_title_shadow }} {{ text_wrap }}">{{ period_display }}</td></tr>
</table>
</td></tr></table>
<!--<![endif]-->
</td>
</tr>
{%- endmacro -%}

<!DOCTYPE html>
<html lang="en" xmlns:v="urn:schemas-microsoft-com:vml" xmlns:o="urn:schemas-microsoft-com:office:office" style="width:100%; max-width:100%; overflow-x:hidden;">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<meta http-equiv="X-UA-Compatible" content="IE=edge">
<meta name="x-apple-disable-message-reformatting">
<meta name="color-scheme" content="light only">
<meta name="supported-color-schemes" content="light only">
<title>MSIL Compliance Weekly Digest</title>
<!--[if mso]>
<noscript><xml><o:OfficeDocumentSettings><o:PixelsPerInch>96</o:PixelsPerInch></o:OfficeDocumentSettings></xml></noscript>
<style>
table {border-collapse: collapse;}
td, th, div, p, a, h1, h2, h3 {font-family: Calibri, Segoe UI, Arial, Helvetica, sans-serif;}
</style>
<![endif]-->
<style>
:root { color-scheme: light only; }
html, body { width: 100% !important; max-width: 100% !important; overflow-x: hidden !important; margin: 0 !important; padding: 0 !important; }
body, table, td, a { -webkit-text-size-adjust: 100%; -ms-text-size-adjust: 100%; }
table, td { mso-table-lspace: 0pt; mso-table-rspace: 0pt; }
img { -ms-interpolation-mode: bicubic; border: 0; outline: none; text-decoration: none; max-width: 100% !important; height: auto !important; }
body { margin: 0; padding: 0; width: 100% !important; }
a { text-decoration: none; }
.email-outer { width: 100% !important; max-width: 100% !important; table-layout: fixed !important; }
.email-wrapper, .content-shell { width: 100% !important; max-width: {{ cw }}px !important; table-layout: fixed !important; }
.card-img { width: 100% !important; max-width: 100% !important; height: auto !important; display: block !important; }
.wave-banner { width: 100% !important; max-width: 100% !important; height: auto !important; display: block !important; }
.stack-col { overflow: hidden !important; word-wrap: break-word !important; vertical-align: top !important; width: 33.33% !important; }
.force-light-text, .force-light-text a {
  color: {{ simple_title }} !important;
  -webkit-text-fill-color: {{ simple_title }} !important;
}
/* Keep titles readable if a client still applies dark-mode inversion */
@media (prefers-color-scheme: dark) {
  .force-light-text, .force-light-text a {
    color: {{ simple_title }} !important;
    -webkit-text-fill-color: {{ simple_title }} !important;
  }
}
/* Fluid hybrid: shrink with reading pane without relying on @media alone */
@media only screen and (max-width: 720px) {
  .outer-pad { padding-left: 8px !important; padding-right: 8px !important; }
  .stack-col { display: block !important; width: 100% !important; max-width: 100% !important; padding: 0 0 20px 0 !important; }
  .mobile-pad { padding-left: 14px !important; padding-right: 14px !important; }
  .hero-title { font-size: 24px !important; line-height: 30px !important; }
}
</style>
</head>
<body bgcolor="{{ body_bg }}" style="margin:0; padding:0; width:100%; max-width:100%; overflow-x:hidden; -webkit-font-smoothing:antialiased; background-color:{{ body_bg }}; background-image:url(cid:{{ bg_cid }}); background-repeat:no-repeat; background-position:center top; background-size:cover;">
{#- Classic Outlook: VML v:background with aspect=atleast ≈ CSS background-size:cover
   so the image fills the reading pane when the user resizes the window. -#}
<!--[if gte mso 9]>
<v:background xmlns:v="urn:schemas-microsoft-com:vml" fill="t">
<v:fill type="frame" aspect="atleast" src="cid:{{ bg_cid }}" color="{{ body_bg }}" />
</v:background>
<![endif]-->
<div style="display:none; max-height:0; overflow:hidden; mso-hide:all; font-size:1px; line-height:1px; color:{{ body_bg }};">Your Weekly Digest: Events &amp; Knowledge Hub updates from MSIL Compliance.&nbsp;&zwnj;&nbsp;&zwnj;&nbsp;&zwnj;&nbsp;&zwnj;&nbsp;&zwnj;&nbsp;&zwnj;&nbsp;&zwnj;&nbsp;&zwnj;&nbsp;&zwnj;&nbsp;&zwnj;</div>
<table role="presentation" class="email-outer" width="100%" cellpadding="0" cellspacing="0" border="0" style="width:100%; max-width:100%; table-layout:fixed; margin:0; padding:0; background-color:transparent;">
<tr><td class="outer-pad" align="center" valign="top" width="100%" style="padding:26px 12px; margin:0; width:100%;">
<!--[if mso]>
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" align="center" style="width:100%; margin:0 auto;">
<tr><td align="center" valign="top" style="width:100%;">
<![endif]-->
<table role="presentation" class="email-wrapper content-shell" width="100%" cellpadding="0" cellspacing="0" border="0" style="width:100%; max-width:{{ cw }}px; table-layout:fixed; margin:0 auto; background-color:transparent;">
{{ hero_banner() }}
<tr><td class="mobile-pad" style="padding:30px {{ hp }} 14px {{ hp }};">
<!--[if mso]>
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" style="width:100%;">
<tr>
{%- for col in columns %}
<td width="{{ col.pct }}%" valign="top" style="width:{{ col.pct }}%; padding:0 7px;">{{ build_column(col, true) }}</td>
{%- endfor %}
</tr>
</table>
<![endif]-->
<!--[if !mso]><!-->
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" style="width:100%; max-width:100%; table-layout:fixed;">
<tr>
{%- for col in columns %}
<td class="stack-col" width="{{ col.pct }}%" valign="top" style="width:{{ col.pct }}%; max-width:{{ col.pct }}%; vertical-align:top; padding:0 {{ col_gap }};">{{ build_column(col, false) }}</td>
{%- endfor %}
</tr>
</table>
<!--<![endif]-->
</td></tr>
<tr><td style="padding:10px {{ hp }} 0 {{ hp }};">
<!--[if mso]>
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0">
<![endif]-->
<!--[if !mso]><!-->
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" style="width:100%; background-color:{{ footer_bg }}; border-radius:12px; overflow:hidden;">
<!--<![endif]-->
<tr><td style="padding:18px 18px; font-family:{{ font_body }};">
<span style="display:block; font-size:13px; color:{{ footer_text }}; padding-bottom:6px;">Regards,<br><strong>Compliance Team</strong></span>
<span style="display:block; font-size:11px; line-height:16px; color:{{ footer_subtext }}; {{ text_wrap }}">This is a weekly digest sent to all employees. You are receiving this because you are part of the organization&rsquo;s distribution list.<br>MSIL Corporate Office, Compliance Division</span>
</td></tr>
</table>
</td></tr>
<tr><td style="padding:0; height:26px; line-height:26px; font-size:26px;">&nbsp;</td></tr>
</table>
<!--[if mso]>
</td></tr></table>
<![endif]-->
</td></tr>
</table>
</body>
</html>
"""

# Compiled once at import time; autoescape=True means all `{{ }}` substitutions are
# HTML-escaped automatically (Python no longer needs to call html.escape() itself).
_DIGEST_EMAIL_TEMPLATE = Template(_DIGEST_EMAIL_TEMPLATE_SRC, autoescape=True, trim_blocks=True, lstrip_blocks=True)


def build_weekly_digest_html(
    payload: dict[str, Any],
    *,
    banner_image_url: str | None = None,
) -> str:
    """Build Outlook-safe HTML digest with 3-column layout: Events | Flyers | Policy+Others.

    Rendering is done via a single compiled jinja2.Template (_DIGEST_EMAIL_TEMPLATE);
    this function only prepares/aggregates the context data passed to it. The
    email background is bg2.jpg and the top wave banner is digest_wave_banner.png,
    both attached as `inline_attachments` (see `_ensure_digest_static_attachments`);
    `banner_image_url` is accepted for backward compatibility but is currently unused.
    """
    events = list(payload.get("events") or [])[:MAX_COLUMN_ITEMS]
    flyers = list(payload.get("flyers") or [])[:MAX_COLUMN_ITEMS]
    policy_others = list(payload.get("policy_others") or [])[:MAX_COLUMN_ITEMS]
    base_url = str(payload.get("base_url") or "https://ecp.com").rstrip("/")

    period_label = _truncate_text(
        payload["period"].get("label", "") if payload and payload.get("period") else "",
        48,
    )
    period_display = period_label if period_label else "this week"

    columns = _build_columns_context(events, flyers, policy_others, base_url)
    # Pixel fallback width for classic Outlook images (Word ignores % on <img>).
    # Matches ~one fluid column so thumbs track the reading-pane column size.
    mso_col_w = int(columns[0]["mso_w"]) if columns else 210
    mso_thumb_w = max(140, mso_col_w - 14)

    return _DIGEST_EMAIL_TEMPLATE.render(
        period_display=period_display,
        columns=columns,
        cw=EMAIL_CONTAINER_WIDTH,
        hp=CONTENT_H_PAD,
        col_gap=COL_GAP,
        body_bg=BODY_BG_COLOR,
        bg_cid=DIGEST_BG_CID,
        banner_cid=DIGEST_BANNER_CID,
        banner_w=DIGEST_BANNER_WIDTH,
        hero_text=HERO_TEXT,
        hero_subtext=HERO_SUBTEXT,
        simple_title=SIMPLE_TITLE_COLOR,
        simple_title_shadow=SIMPLE_TITLE_SHADOW,
        footer_bg=FOOTER_BG,
        footer_text=FOOTER_TEXT,
        footer_subtext=FOOTER_SUBTEXT,
        card_bg=CARD_BG,
        card_bg_mso=CARD_BG_MSO,
        card_border_mso="#c7d2fe",
        card_blur=CARD_BLUR,
        card_border=CARD_BORDER,
        card_radius=CARD_RADIUS,
        image_radius=IMAGE_RADIUS,
        card_shadow=CARD_SHADOW,
        card_label=CARD_LABEL,
        card_text=CARD_TEXT,
        card_accent=CARD_ACCENT,
        card_image_tint=CARD_IMAGE_TINT,
        card_image_tint_mso=CARD_IMAGE_TINT_MSO,
        card_text_bg=CARD_TEXT_BG,
        card_text_bg_mso=CARD_TEXT_BG_MSO,
        image_gap_v=IMAGE_GAP_V,
        col_header_color=COL_HEADER_COLOR,
        link_color=LINK_COLOR,
        font_body=_FONT_BODY,
        font_display=_FONT_DISPLAY,
        card_gap=CARD_GAP,
        text_wrap=_TEXT_WRAP_STYLE,
        mso_thumb_w=mso_thumb_w,
        mso_thumb_h=int(round(mso_thumb_w * 3 / 4)),
    )


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
