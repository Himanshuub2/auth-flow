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
    # Solid soft blues (Outlook often ignores CSS gradients and shows white).
    doc_bg = [
        "#eaf5ff",
        "#edf2ff",
        "#e8f8ff",
        "#f0f4ff",
        "#e6f4ff",
    ]
    tags = item.get("tags") or []
    card_index = int(item.get("_index", 0)) % len(doc_bg)
    bg = doc_bg[card_index]
    tag_html = "".join(
        f"<span style=\"display:inline-block;background:#ffffff;color:#0f3f7a;"
        f"font-size:12px;line-height:16px;padding:4px 8px;border-radius:999px;"
        f"margin:0 6px 6px 0;\">{escape(str(tag))}</span>"
        for tag in tags
    )
    return (
        "<table role=\"presentation\" width=\"100%\" cellpadding=\"0\" cellspacing=\"0\" "
        f"bgcolor=\"{bg}\" style=\"border-collapse:separate;border-spacing:0;background-color:{bg};"
        "border:1px solid #c5dcff;border-radius:10px;\">"
        "<tr><td style=\"padding:16px;font-family:'Segoe UI',Arial,sans-serif;color:#1a1a1a;\">"
        f"<div style=\"font-size:12px;font-weight:700;color:#154f9f;text-transform:uppercase;letter-spacing:.4px;\">{escape(item['heading'])}</div>"
        f"<div style=\"font-size:16px;line-height:22px;font-weight:700;margin-top:6px;color:#0b2f66;\">{escape(item['name'])}</div>"
        f"<div style=\"font-size:13px;line-height:18px;color:#235b9f;margin-top:6px;\">Type: {escape(item['document_type_label'])}</div>"
        f"<div style=\"font-size:14px;line-height:21px;color:#27384f;margin-top:8px;\">{escape(item['description'])}</div>"
        f"<div style=\"margin-top:10px;\">{tag_html}</div>"
        f"<a href=\"{escape(item['link'])}\" style=\"display:inline-block;margin-top:8px;color:#0c4a92;"
        "font-size:14px;font-weight:700;text-decoration:none;\">Open document</a>"
        "</td></tr></table>"
    )


def _render_event_card(item: dict[str, Any]) -> str:
    event_bg = [
        "#eef4ff",
        "#f0efff",
        "#e9f7ff",
        "#eef1ff",
        "#e8f4ff",
    ]
    card_index = int(item.get("_index", 0)) % len(event_bg)
    bg = event_bg[card_index]
    return (
        "<table role=\"presentation\" width=\"100%\" cellpadding=\"0\" cellspacing=\"0\" "
        f"bgcolor=\"{bg}\" style=\"border-collapse:separate;border-spacing:0;background-color:{bg};"
        "border:1px solid #c9dfff;border-radius:10px;\">"
        "<tr><td style=\"padding:16px;font-family:'Segoe UI',Arial,sans-serif;color:#1a1a1a;\">"
        "<div style=\"font-size:12px;font-weight:700;color:#164d9c;text-transform:uppercase;letter-spacing:.4px;\">New Event(s) added</div>"
        f"<div style=\"font-size:16px;line-height:22px;font-weight:700;margin-top:6px;color:#102e61;\">{escape(item['name'])}</div>"
        f"<div style=\"font-size:14px;line-height:21px;color:#2b3f5e;margin-top:8px;\">{escape(item['description'])}</div>"
        f"<a href=\"{escape(item['link'])}\" style=\"display:inline-block;margin-top:10px;color:#0c4a92;"
        "font-size:14px;font-weight:700;text-decoration:none;\">Open event</a>"
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


def _sample_digest_items() -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Demo Knowledge Hub + Events cards for HTML preview / local testing."""
    sample_knowledge_hub = [
        {
            "heading": "New flyer available",
            "name": "Critical Third-Party Cyber Risk Awareness Flyer for Multi-Entity Compliance and Continuous Monitoring Excellence",
            "document_type_label": "Flyer",
            "description": "A detailed communication flyer explaining cross-functional due diligence, escalation protocols, and continuous observation requirements for high-risk third-party onboarding and lifecycle governance.",
            "tags": ["Cyber Risk", "Third Party", "Awareness"],
            "link": "https://ecp.com/flyer/1001",
            "_index": 0,
        },
        {
            "heading": "New Policy, Law regulation available",
            "name": "Enterprise Policy on Data Protection, Consent Governance, and Cross-Border Information Processing Controls",
            "document_type_label": "Policy",
            "description": "This policy defines long-form obligations for teams handling personally identifiable data, mandatory retention boundaries, internal approval controls, and legal review checkpoints.",
            "tags": ["Data Privacy", "Policy", "Governance"],
            "link": "https://ecp.com/policy/1002",
            "_index": 1,
        },
        {
            "heading": "New training material available",
            "name": "Advanced Training Material for Regulatory Reporting Accuracy, Audit Readiness, and Exception Handling Procedures",
            "document_type_label": "Training Material",
            "description": "Comprehensive training content covering scenario-based reporting practices, validation workflows, and long-text guidance for correcting filing exceptions without timeline slippage.",
            "tags": ["Training", "Reporting", "Audit"],
            "link": "https://ecp.com/training_material/1003",
            "_index": 2,
        },
        {
            "heading": "New Policy, Law regulation available",
            "name": "Updated Anti-Bribery and Conflict-of-Interest Policy for Vendor Engagement, Entertainment, and Hospitality Disclosures",
            "document_type_label": "Policy",
            "description": "A practical policy update that clarifies declaration thresholds, investigative responsibilities, and periodic attestation requirements across procurement and business support functions.",
            "tags": ["Ethics", "Policy", "Vendors"],
            "link": "https://ecp.com/policy/1004",
            "_index": 3,
        },
        {
            "heading": "New flyer available",
            "name": "Information Security Incident Reporting Flyer for Rapid Internal Notification and Coordinated Compliance Response",
            "document_type_label": "Flyer",
            "description": "An operational flyer that lists immediate reporting channels, evidence preservation reminders, and communication checkpoints to support timely legal and compliance intervention.",
            "tags": ["Incident", "Security", "Response"],
            "link": "https://ecp.com/flyer/1005",
            "_index": 4,
        },
    ]
    sample_events = [
        {
            "name": "Compliance Townhall on Emerging Regulatory Trends, Supervisory Expectations, and Cross-Border Governance Preparedness",
            "description": "A broad leadership session to discuss major regulatory developments, practical controls alignment, and sustained evidence practices for internal and external stakeholder confidence.",
            "link": "https://ecp.com/events/2001",
            "_index": 0,
        },
        {
            "name": "Hands-On Workshop for Case Management Documentation Quality and Risk-Based Escalation Decisioning",
            "description": "Interactive workshop focused on drafting robust case narratives, documenting rationale clearly, and improving escalation quality for complex multi-factor incidents.",
            "link": "https://ecp.com/events/2002",
            "_index": 1,
        },
        {
            "name": "Training Session on Investigative Interview Standards, Evidence Integrity, and Defensible Closure Reporting",
            "description": "A scenario-rich program that provides practical methods for interview preparation, evidence chain handling, and producing closure reports that withstand review.",
            "link": "https://ecp.com/events/2003",
            "_index": 2,
        },
        {
            "name": "Panel Discussion on Internal Controls Optimization, Policy Usability, and Department-Wide Adoption Strategy",
            "description": "Cross-team discussion around balancing control strength with operational usability, including examples of successful rollout playbooks and accountability models.",
            "link": "https://ecp.com/events/2004",
            "_index": 3,
        },
        {
            "name": "Knowledge Sharing Forum for Lessons Learned from Recent Audit Observations and Corrective Action Execution",
            "description": "An extended knowledge forum to review recurring audit findings, strong remediation approaches, and methods to prevent repeat observations through durable ownership.",
            "link": "https://ecp.com/events/2005",
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


def build_weekly_digest_html(
    payload: dict[str, Any],
    *,
    banner_image_url: str | None = None,
    use_sample_data: bool = True,
) -> str:
    """
    Build Outlook-safe HTML digest.

    use_sample_data=True  -> demo cards (preview / local test)
    use_sample_data=False -> real payload from DB
    """
    if use_sample_data:
        knowledge_hub, events = _sample_digest_items()
    else:
        knowledge_hub = _with_card_index(list(payload.get("knowledge_hub") or []))
        events = _with_card_index(list(payload.get("events") or []))

    knowledge_cards = [_render_doc_card(item) for item in knowledge_hub]
    event_cards = [_render_event_card(item) for item in events]

    if banner_image_url:
        banner_html = (
            f"<img src=\"{escape(banner_image_url)}\" alt=\"Weekly digest banner\" width=\"640\" "
            "style=\"display:block;width:100%;max-width:640px;height:auto;border:0;\">"
        )
    else:
        # Solid color bands so Outlook shows color (CSS gradients often render white).
        banner_html = (
            "<table role=\"presentation\" width=\"100%\" cellpadding=\"0\" cellspacing=\"0\" "
            "style=\"border-collapse:collapse;\">"
            "<tr><td bgcolor=\"#0a4d96\" height=\"8\" style=\"font-size:0;line-height:0;\">&nbsp;</td></tr>"
            "<tr>"
            "<td bgcolor=\"#1565c0\" style=\"padding:26px 24px;font-family:'Segoe UI',Arial,sans-serif;color:#ffffff;\">"
            "<div style=\"font-size:22px;line-height:28px;font-weight:700;\">Weekly Knowledge &amp; Events Digest</div>"
            "<div style=\"font-size:14px;line-height:20px;margin-top:6px;color:#d6e8ff;\">"
            "Highlights from Knowledge Hub and Events"
            "</div>"
            "</td>"
            "</tr>"
            "<tr><td bgcolor=\"#42a5f5\" height=\"6\" style=\"font-size:0;line-height:0;\">&nbsp;</td></tr>"
            "</table>"
        )

    footer_html = (
        "<table role=\"presentation\" width=\"100%\" cellpadding=\"0\" cellspacing=\"0\" "
        "style=\"border-collapse:collapse;\">"
        "<tr><td bgcolor=\"#42a5f5\" height=\"4\" style=\"font-size:0;line-height:0;\">&nbsp;</td></tr>"
        "<tr>"
        "<td bgcolor=\"#0d47a1\" style=\"padding:22px 24px;font-family:'Segoe UI',Arial,sans-serif;color:#ffffff;\">"
        "<div style=\"font-size:14px;line-height:20px;\">Regards,</div>"
        "<div style=\"font-size:15px;line-height:22px;font-weight:700;margin-top:2px;\">Compliance Team</div>"
        "</td>"
        "</tr>"
        "<tr><td bgcolor=\"#0a4d96\" height=\"8\" style=\"font-size:0;line-height:0;\">&nbsp;</td></tr>"
        "</table>"
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
        background-color: #dcecff !important;
      }}
      @media screen and (max-width: 640px) {{
        .container {{
          width: 100% !important;
        }}
      }}
    </style>
  </head>
  <body style="margin:0;padding:0;background-color:#dcecff;">
    <!-- Outer wrap: soft multi-tone background for Outlook + other clients -->
    <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0"
           bgcolor="#dcecff" style="border-collapse:collapse;background-color:#dcecff;">
      <tr>
        <td align="center" bgcolor="#e3f0ff" style="padding:20px 10px;background-color:#e3f0ff;">
          <table role="presentation" class="container" width="640" cellpadding="0" cellspacing="0" border="0"
                 bgcolor="#f4f8ff"
                 style="width:640px;max-width:640px;border-collapse:collapse;background-color:#f4f8ff;">
            <tr>
              <td>{banner_html}</td>
            </tr>
            <tr>
              <td bgcolor="#eaf3ff" style="padding:18px 20px 6px 20px;font-family:'Segoe UI',Arial,sans-serif;background-color:#eaf3ff;">
                <div style="font-size:18px;line-height:24px;font-weight:700;color:#0d3f7d;">Knowledge Hub</div>
              </td>
            </tr>
            <tr>
              <td bgcolor="#f4f8ff" style="padding:8px 12px 16px 12px;background-color:#f4f8ff;">
                {_render_grid(knowledge_cards, "No Knowledge Hub items to show.")}
              </td>
            </tr>
            <tr>
              <td bgcolor="#e8f0ff" style="padding:8px 20px 6px 20px;font-family:'Segoe UI',Arial,sans-serif;background-color:#e8f0ff;">
                <div style="font-size:18px;line-height:24px;font-weight:700;color:#0d3f7d;">Events</div>
              </td>
            </tr>
            <tr>
              <td bgcolor="#f4f8ff" style="padding:8px 12px 20px 12px;background-color:#f4f8ff;">
                {_render_grid(event_cards, "No Events to show.")}
              </td>
            </tr>
            <tr>
              <td>{footer_html}</td>
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
