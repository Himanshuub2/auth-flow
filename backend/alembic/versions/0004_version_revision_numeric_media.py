"""Version/revision refactor + numeric media_version on revision tables.

Combines former 0004_version_revision + 0005_media_version_numeric into one step.

- Events/documents: remove current_media_version; revision (INTEGER); version NUMERIC(10,2)
- event_revisions / document_revisions: media_version NUMERIC(10,2)

Revision ID: 0004_version_revision_numeric_media
Revises: bb46983d6af6

If a database already ran the old chain (0004_version_revision then 0005_media_version_numeric),
stamp it once: alembic stamp 0004_version_revision_numeric_media
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0004_version_revision_numeric_media"
down_revision: Union[str, None] = "bb46983d6af6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

EVENTS_SCHEMA = "events"
DOCUMENTS_SCHEMA = "documents"


def upgrade() -> None:
    # ── Events table ─────────────────────────────────────────────────────
    op.add_column(
        "events",
        sa.Column("version", sa.Numeric(10, 2), nullable=False, server_default="1.0"),
        schema=EVENTS_SCHEMA,
    )

    op.alter_column(
        "events",
        "current_revision_number",
        new_column_name="revision",
        schema=EVENTS_SCHEMA,
    )
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

    op.drop_column("events", "current_media_version", schema=EVENTS_SCHEMA)

    # ── Documents table ──────────────────────────────────────────────────
    op.alter_column(
        "documents",
        "current_revision_number",
        new_column_name="revision",
        schema=DOCUMENTS_SCHEMA,
    )
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

    op.drop_column("documents", "current_media_version", schema=DOCUMENTS_SCHEMA)

    op.alter_column(
        "documents",
        "version",
        type_=sa.Numeric(10, 2),
        postgresql_using="version::numeric(10,2)",
        server_default="1.0",
        nullable=False,
        schema=DOCUMENTS_SCHEMA,
    )

    # ── Revision tables: media_version → NUMERIC ─────────────────────────
    op.alter_column(
        "event_revisions",
        "media_version",
        type_=sa.Numeric(10, 2),
        postgresql_using="media_version::numeric(10,2)",
        existing_nullable=False,
        schema=EVENTS_SCHEMA,
    )

    op.alter_column(
        "document_revisions",
        "media_version",
        type_=sa.Numeric(10, 2),
        postgresql_using="media_version::numeric(10,2)",
        existing_nullable=False,
        schema=DOCUMENTS_SCHEMA,
    )


def downgrade() -> None:
    op.alter_column(
        "document_revisions",
        "media_version",
        type_=sa.Integer(),
        postgresql_using="media_version::integer",
        existing_nullable=False,
        schema=DOCUMENTS_SCHEMA,
    )

    op.alter_column(
        "event_revisions",
        "media_version",
        type_=sa.Integer(),
        postgresql_using="media_version::integer",
        existing_nullable=False,
        schema=EVENTS_SCHEMA,
    )

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
