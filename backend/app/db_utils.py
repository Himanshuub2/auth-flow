"""Dialect helpers for SQLite vs PostgreSQL. Used only when settings.is_sqlite is True."""

from sqlalchemy import JSON, Integer
from sqlalchemy.dialects.postgresql import ARRAY, JSONB

from app.config import settings


def json_type():
    """Use JSON for SQLite (no JSONB); JSONB for PostgreSQL."""
    return JSON() if settings.is_sqlite else JSONB()


def media_versions_type():
    """Store list of ints: JSON on SQLite, ARRAY(Integer) on PostgreSQL."""
    return JSON() if settings.is_sqlite else ARRAY(Integer)


def schema_events():
    """Schema name for events tables; None for SQLite (no schemas)."""
    return None if settings.is_sqlite else "events"


def schema_documents():
    """Schema name for documents tables; None for SQLite (no schemas)."""
    return None if settings.is_sqlite else "documents"


def events_table(name: str) -> str:
    """Table name for events: prefixed when SQLite to match SQLite migration."""
    if settings.is_sqlite:
        if name == "users":
            return "events_users"
        if name == "events":
            return "events_events"
        if name == "event_revisions":
            return "event_revisions"
        if name == "files":
            return "event_files"
        return f"events_{name}"
    return name


def documents_table(name: str) -> str:
    """Table name for documents: prefixed when SQLite to match SQLite migration."""
    if settings.is_sqlite:
        if name == "document_revisions":
            return "document_revisions"
        return f"documents_{name}"
    return name


def fk_events(table: str, column: str = "id") -> str:
    """ForeignKey target for events schema (e.g. events.users.id or events_users.id)."""
    if settings.is_sqlite:
        t = events_table(table)
        return f"{t}.{column}"
    return f"events.{table}.{column}"


def fk_documents(table: str, column: str = "id") -> str:
    """ForeignKey target for documents schema."""
    if settings.is_sqlite:
        t = documents_table(table)
        return f"{t}.{column}"
    return f"documents.{table}.{column}"


def fk_users(column: str = "id") -> str:
    """ForeignKey target for users (in events schema)."""
    return fk_events("users", column)
