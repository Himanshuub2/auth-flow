"""Separate version (user-facing NUMERIC) and revision (auto-incremented INTEGER).

- Remove current_media_version from events and documents
- Rename current_revision_number -> revision (INTEGER, default 1)
- Add version (NUMERIC 10,2, default 1.0) to events
- Change version column type from INTEGER to NUMERIC(10,2) in documents

Revision ID: 0004_version_revision
Revises: bb46983d6af6
Create Date: 2026-05-06
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0004_version_revision"
down_revision: Union[str, None] = "bb46983d6af6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

EVENTS_SCHEMA = "events"
DOCUMENTS_SCHEMA = "documents"


def upgrade() -> None:
    # ── Events table ─────────────────────────────────────────────────────
    # Add version column (NUMERIC)
    op.add_column(
        "events",
        sa.Column("version", sa.Numeric(10, 2), nullable=False, server_default="1.0"),
        schema=EVENTS_SCHEMA,
    )

    # Rename current_revision_number -> revision
    op.alter_column(
        "events",
        "current_revision_number",
        new_column_name="revision",
        schema=EVENTS_SCHEMA,
    )
    # Set default and migrate data: published items get max(current_media_version, 1)
    op.execute(
        f"UPDATE {EVENTS_SCHEMA}.events "
        f"SET revision = GREATEST(current_media_version, 1)"
    )
    op.alter_column(
        "events",
        "revision",
        server_default="1",
        nullable=False,
        schema=EVENTS_SCHEMA,
    )

    # Drop current_media_version
    op.drop_column("events", "current_media_version", schema=EVENTS_SCHEMA)

    # ── Documents table ──────────────────────────────────────────────────
    # Rename current_revision_number -> revision
    op.alter_column(
        "documents",
        "current_revision_number",
        new_column_name="revision",
        schema=DOCUMENTS_SCHEMA,
    )
    # Migrate data before dropping current_media_version
    op.execute(
        f"UPDATE {DOCUMENTS_SCHEMA}.documents "
        f"SET revision = GREATEST(current_media_version, 1)"
    )
    op.alter_column(
        "documents",
        "revision",
        server_default="1",
        nullable=False,
        schema=DOCUMENTS_SCHEMA,
    )

    # Drop current_media_version
    op.drop_column("documents", "current_media_version", schema=DOCUMENTS_SCHEMA)

    # Change version column from INTEGER to NUMERIC(10,2)
    op.alter_column(
        "documents",
        "version",
        type_=sa.Numeric(10, 2),
        postgresql_using="version::numeric(10,2)",
        server_default="1.0",
        nullable=False,
        schema=DOCUMENTS_SCHEMA,
    )


def downgrade() -> None:
    # ── Documents table ──────────────────────────────────────────────────
    op.alter_column(
        "documents",
        "version",
        type_=sa.Integer(),
        postgresql_using="version::integer",
        server_default="1",
        nullable=False,
        schema=DOCUMENTS_SCHEMA,
    )

    op.add_column(
        "documents",
        sa.Column("current_media_version", sa.Integer(), nullable=False, server_default="0"),
        schema=DOCUMENTS_SCHEMA,
    )

    op.alter_column(
        "documents",
        "revision",
        new_column_name="current_revision_number",
        server_default="0",
        schema=DOCUMENTS_SCHEMA,
    )

    # ── Events table ─────────────────────────────────────────────────────
    op.add_column(
        "events",
        sa.Column("current_media_version", sa.Integer(), nullable=False, server_default="0"),
        schema=EVENTS_SCHEMA,
    )

    op.alter_column(
        "events",
        "revision",
        new_column_name="current_revision_number",
        server_default="0",
        schema=EVENTS_SCHEMA,
    )

    op.drop_column("events", "version", schema=EVENTS_SCHEMA)
