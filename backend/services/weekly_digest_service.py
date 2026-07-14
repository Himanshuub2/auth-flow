from __future__ import annotations

import asyncio
import importlib
import json
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, time, timedelta, timezone
from html import escape
from typing import Any

from utils.dates import IST

DOCUMENT_TYPE_LABELS: dict[str, str] = {
    "POLICY": "Policy",
    "GUIDANCE_NOTE": "Guidance Note",
    "LAW_REGULATION": "Law Regulation",
    "TRAINING_MATERIAL": "Training Material",
    "EWS": "EWS",
    "FAQ": "FAQ",
    "LATEST_NEWS_AND_ANNOUNCEMENTS": "Latest News and Announcements",
    "FLYER": "Flyer",
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
) -> dict[str, Any]:
    documents: list[dict[str, Any]] = []
    for row in doc_rows:
        doc_type = str(row["document_type"])
        if doc_type not in ALLOWED_WEEKLY_DOCUMENT_TYPES:
            continue
        tags = _safe_tags(row["tags"])[:3]
        documents.append(
            {
                "id": int(row["document_id"]),
                "name": row["name"],
                "document_type": doc_type,
                "document_type_label": DOCUMENT_TYPE_LABELS.get(doc_type, doc_type),
                "heading": DOC_HEADING_BY_TYPE.get(doc_type, "New document available"),
                "description": row["summary"] or "",
                "tags": tags,
                "link": _doc_link(base_url, doc_type, int(row["document_id"])),
                "created_at_utc": row["created_at"].isoformat() if row["created_at"] else None,
            }
        )

    events: list[dict[str, Any]] = []
    for row in event_rows:
        events.append(
            {
                "id": int(row["event_id"]),
                "name": row["event_name"],
                "description": row["description"] or "",
                "heading": "New Event(s) added",
                "link": _event_link(base_url, int(row["event_id"])),
                "created_at_utc": row["created_at"].isoformat() if row["created_at"] else None,
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
            latest.created_at
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
            latest.created_at
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

    return _build_payload_from_rows(
        doc_rows,
        event_rows,
        start_utc=start_utc,
        end_utc=end_utc,
        base_url=base_url,
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
) -> dict[str, Any]:
    """
    Build weekly digest payload + HTML, then send via ACS (sync flow).
    """
    payload = build_weekly_digest_payload_sync(
        db_config,
        reference_utc=reference_utc,
        base_url=base_url,
    )
    html = build_weekly_digest_html(payload, banner_image_url=banner_image_url)
    send_result = send_html_email_via_acs(
        connection_string=connection_string,
        sender_address=sender_address,
        to_addresses=to_addresses,
        cc_addresses=cc_addresses,
        bcc_addresses=bcc_addresses,
        subject=subject,
        html_content=html,
        plain_text=(
            f"Weekly digest for {payload['period']['label']}. "
            f"Knowledge Hub updates: {payload['counts']['knowledge_hub']}, "
            f"Events updates: {payload['counts']['events']}."
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
) -> dict[str, Any]:
    """
    Async wrapper for sync build+send flow using ThreadPoolExecutor(max_workers=10).
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
        ),
    )


def _render_doc_card(item: dict[str, Any]) -> str:
    tags = item.get("tags") or []
    tag_html = "".join(
        f"<span style=\"display:inline-block;background:#e6f0ff;color:#0f3f7a;"
        f"font-size:12px;line-height:16px;padding:4px 8px;border-radius:999px;"
        f"margin:0 6px 6px 0;\">{escape(str(tag))}</span>"
        for tag in tags
    )
    return (
        "<table role=\"presentation\" width=\"100%\" cellpadding=\"0\" cellspacing=\"0\" "
        "style=\"border-collapse:separate;border-spacing:0;background:#ffffff;border:1px solid #d9e7ff;"
        "border-radius:10px;\">"
        "<tr><td style=\"padding:16px;font-family:'Segoe UI',Arial,sans-serif;color:#1a1a1a;\">"
        f"<div style=\"font-size:12px;font-weight:700;color:#0f4d9a;text-transform:uppercase;letter-spacing:.4px;\">{escape(item['heading'])}</div>"
        f"<div style=\"font-size:16px;line-height:22px;font-weight:700;margin-top:6px;\">{escape(item['name'])}</div>"
        f"<div style=\"font-size:13px;line-height:18px;color:#335f9e;margin-top:6px;\">Type: {escape(item['document_type_label'])}</div>"
        f"<div style=\"font-size:14px;line-height:21px;color:#2f3a4a;margin-top:8px;\">{escape(item['description'])}</div>"
        f"<div style=\"margin-top:10px;\">{tag_html}</div>"
        f"<a href=\"{escape(item['link'])}\" style=\"display:inline-block;margin-top:8px;color:#0b5cab;"
        "font-size:14px;font-weight:600;text-decoration:none;\">Open document</a>"
        "</td></tr></table>"
    )


def _render_event_card(item: dict[str, Any]) -> str:
    return (
        "<table role=\"presentation\" width=\"100%\" cellpadding=\"0\" cellspacing=\"0\" "
        "style=\"border-collapse:separate;border-spacing:0;background:#ffffff;border:1px solid #d9e7ff;"
        "border-radius:10px;\">"
        "<tr><td style=\"padding:16px;font-family:'Segoe UI',Arial,sans-serif;color:#1a1a1a;\">"
        "<div style=\"font-size:12px;font-weight:700;color:#0f4d9a;text-transform:uppercase;letter-spacing:.4px;\">New Event(s) added</div>"
        f"<div style=\"font-size:16px;line-height:22px;font-weight:700;margin-top:6px;\">{escape(item['name'])}</div>"
        f"<div style=\"font-size:14px;line-height:21px;color:#2f3a4a;margin-top:8px;\">{escape(item['description'])}</div>"
        f"<a href=\"{escape(item['link'])}\" style=\"display:inline-block;margin-top:10px;color:#0b5cab;"
        "font-size:14px;font-weight:600;text-decoration:none;\">Open event</a>"
        "</td></tr></table>"
    )


def _render_grid(cards: list[str], empty_message: str) -> str:
    if not cards:
        return (
            "<table role=\"presentation\" width=\"100%\" cellpadding=\"0\" cellspacing=\"0\" "
            "style=\"border-collapse:collapse;background:#f7fbff;border:1px dashed #bfd6ff;border-radius:10px;\">"
            f"<tr><td style=\"padding:20px;font-family:'Segoe UI',Arial,sans-serif;color:#36557c;font-size:14px;\">{escape(empty_message)}</td></tr>"
            "</table>"
        )

    rows: list[str] = []
    for i in range(0, len(cards), 2):
        left = cards[i]
        right = cards[i + 1] if i + 1 < len(cards) else ""
        right_cell = (
            f"<td valign=\"top\" width=\"50%\" style=\"padding:8px;\">{right}</td>"
            if right
            else "<td valign=\"top\" width=\"50%\" style=\"padding:8px;\"></td>"
        )
        rows.append(
            "<tr>"
            f"<td valign=\"top\" width=\"50%\" style=\"padding:8px;\">{left}</td>"
            f"{right_cell}"
            "</tr>"
        )
    return (
        "<table role=\"presentation\" width=\"100%\" cellpadding=\"0\" cellspacing=\"0\" "
        "style=\"border-collapse:collapse;\">"
        + "".join(rows)
        + "</table>"
    )


def build_weekly_digest_html(
    payload: dict[str, Any],
    *,
    banner_image_url: str | None = None,
) -> str:
    knowledge_cards = [_render_doc_card(item) for item in payload.get("knowledge_hub", [])]
    event_cards = [_render_event_card(item) for item in payload.get("events", [])]
    counts = payload.get("counts", {})
    period = payload.get("period", {})

    if banner_image_url:
        banner_html = (
            f"<img src=\"{escape(banner_image_url)}\" alt=\"Weekly digest banner\" width=\"640\" "
            "style=\"display:block;width:100%;max-width:640px;height:auto;border:0;\">"
        )
    else:
        banner_html = (
            "<table role=\"presentation\" width=\"100%\" cellpadding=\"0\" cellspacing=\"0\" "
            "style=\"border-collapse:collapse;background:linear-gradient(90deg,#084a9a 0%,#0b5cab 35%,#2a80d8 70%,#71b2ff 100%);\">"
            "<tr><td style=\"padding:28px 24px;font-family:'Segoe UI',Arial,sans-serif;color:#ffffff;\">"
            "<div style=\"font-size:24px;line-height:30px;font-weight:700;\">Weekly Knowledge & Events Digest</div>"
            f"<div style=\"font-size:14px;line-height:20px;margin-top:8px;opacity:.95;\">{escape(period.get('label', 'Last week update'))}</div>"
            "</td></tr></table>"
        )

    return f"""<!doctype html>
<html lang="en">
  <head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width,initial-scale=1.0">
    <meta name="color-scheme" content="light dark">
    <meta name="supported-color-schemes" content="light dark">
    <title>Weekly Digest</title>
    <style>
      body {{
        margin: 0 !important;
        padding: 0 !important;
        background: #eef4ff;
      }}
      @media (prefers-color-scheme: dark) {{
        body {{
          background: #0e1523 !important;
        }}
      }}
      @media screen and (max-width: 640px) {{
        .container {{
          width: 100% !important;
        }}
      }}
    </style>
  </head>
  <body>
    <center style="width:100%;background:#eef4ff;padding:18px 10px;">
      <table role="presentation" class="container" width="640" cellpadding="0" cellspacing="0"
             style="width:640px;max-width:640px;border-collapse:collapse;background:#f4f8ff;border-radius:12px;overflow:hidden;">
        <tr>
          <td>{banner_html}</td>
        </tr>
        <tr>
          <td style="padding:18px 20px 8px 20px;font-family:'Segoe UI',Arial,sans-serif;color:#16365f;">
            <div style="font-size:14px;line-height:20px;">
              Period: <strong>{escape(period.get("label", "Last week"))}</strong>
            </div>
            <div style="font-size:13px;line-height:18px;margin-top:4px;color:#245184;">
              Total updates: <strong>{counts.get("total", 0)}</strong> |
              Knowledge Hub: <strong>{counts.get("knowledge_hub", 0)}</strong> |
              Events: <strong>{counts.get("events", 0)}</strong>
            </div>
          </td>
        </tr>
        <tr>
          <td style="padding:8px 20px 4px 20px;font-family:'Segoe UI',Arial,sans-serif;">
            <div style="font-size:20px;line-height:26px;font-weight:700;color:#0d3f7d;">Knowledge Hub</div>
          </td>
        </tr>
        <tr>
          <td style="padding:8px 12px 18px 12px;">
            {_render_grid(knowledge_cards, "No new Knowledge Hub documents were added in the last week.")}
          </td>
        </tr>
        <tr>
          <td style="padding:2px 20px 4px 20px;font-family:'Segoe UI',Arial,sans-serif;">
            <div style="font-size:20px;line-height:26px;font-weight:700;color:#0d3f7d;">Events</div>
          </td>
        </tr>
        <tr>
          <td style="padding:8px 12px 22px 12px;">
            {_render_grid(event_cards, "No new events were added in the last week.")}
          </td>
        </tr>
      </table>
    </center>
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
    html = build_weekly_digest_html(payload, banner_image_url=banner_image_url)
    return payload, html
