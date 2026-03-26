"""Small helpers to build consistent cache keys."""

from __future__ import annotations

from utils.security import CurrentUser


def role_scope(user: CurrentUser) -> str:
    return (
        f"m{int(bool(user.is_master_admin))}"
        f"_p{int(bool(user.is_policy_hub_admin))}"
        f"_k{int(bool(user.is_knowledge_hub_admin))}"
    )


def event_item(event_id: int) -> str:
    return f"item:event:{event_id}"


def document_item(document_id: int) -> str:
    return f"item:document:{document_id}"


def event_list(page: int, page_size: int, status_value: str | None) -> str:
    return f"events:list:{page}:{page_size}:{status_value or 'ALL'}"


def doc_hub(
    user: CurrentUser,
    doc_types: list[str] | None,
    page: int,
    page_size: int,
    load_more_type: str | None,
    load_more_page: int | None,
    applicability: str | None,
    search: str | None,
) -> str:
    types_part = ",".join(sorted(doc_types or []))
    return (
        f"doc_hub:{role_scope(user)}:{types_part}:{page}:{page_size}:"
        f"{load_more_type}:{load_more_page}:{applicability}:{(search or '').strip().lower()}"
    )


def item_detail(item_type: str, item_id: int) -> str:
    return f"item:{item_type}:{item_id}"


def items_list(
    page: int,
    page_size: int,
    item_type: str | None,
    document_types: list[str] | None,
    document_names: list[str] | None,
    statuses: list[str] | None,
    last_updated_start,
    last_updated_end,
    next_review_start,
    next_review_end,
    search: str | None,
) -> str:
    return (
        "items:list:"
        f"{page}:{page_size}:{item_type or 'all'}:"
        f"{','.join(sorted(document_types or []))}:"
        f"{','.join(sorted(document_names or []))}:"
        f"{','.join(sorted(statuses or []))}:"
        f"{last_updated_start}:{last_updated_end}:{next_review_start}:{next_review_end}:"
        f"{(search or '').strip().lower()}"
    )
