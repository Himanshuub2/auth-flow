"""Combined database setup: events + documents schemas, all tables, current state.

Single migration for fresh installs. Includes: schemas, tables (replaces_document_id),
enums (event_status/document_status: DRAFT, ACTIVE, INACTIVE — no PUBLISHED), and seed data.

Revision ID: 0001_combined
Revises: None
Create Date: 2026-03-07

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "0001_combined"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

EVENTS = "events"
DOCUMENTS = "documents"
USER_SCHEMA = EVENTS  # users live in events schema


def upgrade() -> None:
    # ─── Schemas ─────────────────────────────────────────────────────────
    op.execute(sa.text(f"CREATE SCHEMA IF NOT EXISTS {EVENTS}"))
    op.execute(sa.text(f"CREATE SCHEMA IF NOT EXISTS {DOCUMENTS}"))

    # ─── Events schema: enums (DRAFT/ACTIVE/INACTIVE — no PUBLISHED) ───
    for name, values in [
        ("event_status", "'DRAFT', 'ACTIVE', 'INACTIVE'"),
        ("applicability_type", "'ALL', 'DIVISION', 'EMPLOYEE'"),
        ("file_type", "'IMAGE', 'VIDEO'"),
    ]:
        op.execute(
            sa.text(
                f"DO $$ BEGIN CREATE TYPE {EVENTS}.{name} AS ENUM ({values}); "
                f"EXCEPTION WHEN duplicate_object THEN NULL; END $$;"
            )
        )

    # ─── Events schema: users ─────────────────────────────────────────────
    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column("password_hash", sa.String(length=255), nullable=False),
        sa.Column("full_name", sa.String(length=255), nullable=False),
        sa.Column("division_cluster", sa.String(length=100), nullable=True),
        sa.Column("designation", sa.String(length=100), nullable=True),
        sa.Column("policy_hub_admin", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("is_admin", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("knowledge_hub_admin", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        schema=EVENTS,
    )
    op.create_index(
        op.f("ix_events_users_email"), "users", ["email"], unique=True, schema=EVENTS
    )

    # ─── Events schema: events ────────────────────────────────────────────
    op.create_table(
        "events",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("event_name", sa.String(length=255), nullable=False),
        sa.Column("sub_event_name", sa.String(length=255), nullable=True),
        sa.Column("event_dates", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("tags", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("current_media_version", sa.Integer(), nullable=False),
        sa.Column("current_revision_number", sa.Integer(), nullable=False),
        sa.Column("staging_file_ids", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default="[]"),
        sa.Column(
            "status",
            postgresql.ENUM(
                "DRAFT", "ACTIVE", "INACTIVE",
                name="event_status", schema=EVENTS, create_type=False,
            ),
            nullable=False,
        ),
        sa.Column(
            "applicability_type",
            postgresql.ENUM(
                "ALL", "DIVISION", "EMPLOYEE",
                name="applicability_type", schema=EVENTS, create_type=False,
            ),
            nullable=False,
        ),
        sa.Column("applicability_refs", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("replaces_document_id", sa.Integer(), nullable=True),
        sa.Column("created_by", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("change_remarks", sa.Text(), nullable=True),
        sa.Column("deactivate_remarks", sa.Text(), nullable=True),
        sa.Column("deactivated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("deactivated_by", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(["created_by"], [f"{EVENTS}.users.id"]),
        sa.ForeignKeyConstraint(["replaces_document_id"], [f"{EVENTS}.events.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["deactivated_by"], [f"{EVENTS}.users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        schema=EVENTS,
    )

    # ─── Events schema: event_revisions ────────────────────────────────────
    op.create_table(
        "event_revisions",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("event_id", sa.Integer(), nullable=False),
        sa.Column("media_version", sa.Integer(), nullable=False),
        sa.Column("revision_number", sa.Integer(), nullable=False),
        sa.Column("event_name", sa.String(length=255), nullable=False),
        sa.Column("sub_event_name", sa.String(length=255), nullable=True),
        sa.Column("event_dates", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("tags", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("file_ids", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default="[]"),
        sa.Column("created_by", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("change_remarks", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["created_by"], [f"{EVENTS}.users.id"]),
        sa.ForeignKeyConstraint(["event_id"], [f"{EVENTS}.events.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("event_id", "media_version", "revision_number", name="uq_event_version_revision"),
        schema=EVENTS,
    )

    # ─── Events schema: files (event media) ────────────────────────────────
    op.create_table(
        "files",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("event_id", sa.Integer(), nullable=False),
        sa.Column(
            "file_type",
            postgresql.ENUM("IMAGE", "VIDEO", name="file_type", schema=EVENTS, create_type=False),
            nullable=False,
        ),
        sa.Column("file_url", sa.String(length=500), nullable=False),
        sa.Column("thumbnail_url", sa.String(length=500), nullable=True),
        sa.Column("caption", sa.String(length=255), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("sort_order", sa.Integer(), nullable=False),
        sa.Column("file_size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("original_filename", sa.String(length=255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["event_id"], [f"{EVENTS}.events.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        schema=EVENTS,
    )

    # ─── Documents schema: enums ──────────────────────────────────────────
    op.execute(sa.text(
        f"DO $$ BEGIN CREATE TYPE {DOCUMENTS}.document_type AS ENUM ("
        "'POLICY','GUIDANCE_NOTE','LAW_REGULATION','TRAINING_MATERIAL',"
        "'EWS','FAQ','LATEST_NEWS_AND_ANNOUNCEMENTS'"
        "); EXCEPTION WHEN duplicate_object THEN NULL; END $$;"
    ))
    op.execute(sa.text(
        f"DO $$ BEGIN CREATE TYPE {DOCUMENTS}.document_status AS ENUM ("
        "'DRAFT','ACTIVE','INACTIVE'"
        "); EXCEPTION WHEN duplicate_object THEN NULL; END $$;"
    ))
    op.execute(sa.text(
        f"DO $$ BEGIN CREATE TYPE {DOCUMENTS}.doc_applicability_type AS ENUM ("
        "'ALL','DIVISION','EMPLOYEE'"
        "); EXCEPTION WHEN duplicate_object THEN NULL; END $$;"
    ))
    op.execute(sa.text(
        f"DO $$ BEGIN CREATE TYPE {DOCUMENTS}.doc_file_type AS ENUM ("
        "'IMAGE','DOCUMENT'"
        "); EXCEPTION WHEN duplicate_object THEN NULL; END $$;"
    ))

    # ─── Documents schema: legislation ──────────────────────────────────────
    op.create_table(
        "legislation",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("name", sa.String(255), nullable=False, unique=True),
        sa.PrimaryKeyConstraint("id"),
        schema=DOCUMENTS,
    )
    op.create_table(
        "sub_legislation",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("legislation_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.ForeignKeyConstraint(["legislation_id"], [f"{DOCUMENTS}.legislation.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        schema=DOCUMENTS,
    )

    # ─── Documents schema: documents ──────────────────────────────────────
    op.create_table(
        "documents",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column(
            "document_type",
            postgresql.ENUM(
                "POLICY", "GUIDANCE_NOTE", "LAW_REGULATION", "TRAINING_MATERIAL",
                "EWS", "FAQ", "LATEST_NEWS_AND_ANNOUNCEMENTS",
                name="document_type", schema=DOCUMENTS, create_type=False,
            ),
            nullable=False,
        ),
        sa.Column("tags", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("legislation_id", sa.Integer(), nullable=True),
        sa.Column("sub_legislation_id", sa.Integer(), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("next_review_date", sa.Date(), nullable=True),
        sa.Column("download_allowed", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("linked_document_ids", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column(
            "applicability_type",
            postgresql.ENUM(
                "ALL", "DIVISION", "EMPLOYEE",
                name="doc_applicability_type", schema=DOCUMENTS, create_type=False,
            ),
            nullable=False,
            server_default="ALL",
        ),
        sa.Column("applicability_refs", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column(
            "status",
            postgresql.ENUM(
                "DRAFT", "ACTIVE", "INACTIVE",
                name="document_status", schema=DOCUMENTS, create_type=False,
            ),
            nullable=False,
            server_default="DRAFT",
        ),
        sa.Column("current_media_version", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("current_revision_number", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("staging_file_ids", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default="[]"),
        sa.Column("change_remarks", sa.Text(), nullable=True),
        sa.Column("deactivate_remarks", sa.Text(), nullable=True),
        sa.Column("deactivated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("deactivated_by", sa.Integer(), nullable=True),
        sa.Column("replaces_document_id", sa.Integer(), nullable=True),
        sa.Column("created_by", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["legislation_id"], [f"{DOCUMENTS}.legislation.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["sub_legislation_id"], [f"{DOCUMENTS}.sub_legislation.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["replaces_document_id"], [f"{DOCUMENTS}.documents.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["created_by"], [f"{USER_SCHEMA}.users.id"]),
        sa.ForeignKeyConstraint(["deactivated_by"], [f"{USER_SCHEMA}.users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        schema=DOCUMENTS,
    )

    # ─── Documents schema: document_revisions ─────────────────────────────
    op.create_table(
        "document_revisions",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("document_id", sa.Integer(), nullable=False),
        sa.Column("media_version", sa.Integer(), nullable=False),
        sa.Column("revision_number", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column(
            "document_type",
            postgresql.ENUM(
                "POLICY", "GUIDANCE_NOTE", "LAW_REGULATION", "TRAINING_MATERIAL",
                "EWS", "FAQ", "LATEST_NEWS_AND_ANNOUNCEMENTS",
                name="document_type", schema=DOCUMENTS, create_type=False,
            ),
            nullable=False,
        ),
        sa.Column("tags", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column(
            "applicability_type",
            postgresql.ENUM(
                "ALL", "DIVISION", "EMPLOYEE",
                name="doc_applicability_type", schema=DOCUMENTS, create_type=False,
            ),
            nullable=False,
            server_default="ALL",
        ),
        sa.Column("applicability_refs", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("file_ids", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default="[]"),
        sa.Column("created_by", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["document_id"], [f"{DOCUMENTS}.documents.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by"], [f"{USER_SCHEMA}.users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("document_id", "media_version", "revision_number", name="uq_doc_version_revision"),
        schema=DOCUMENTS,
    )

    # ─── Documents schema: files ─────────────────────────────────────────
    op.create_table(
        "files",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("document_id", sa.Integer(), nullable=False),
        sa.Column(
            "file_type",
            postgresql.ENUM("IMAGE", "DOCUMENT", name="doc_file_type", schema=DOCUMENTS, create_type=False),
            nullable=False,
        ),
        sa.Column("file_url", sa.String(500), nullable=False),
        sa.Column("original_filename", sa.String(255), nullable=False),
        sa.Column("file_size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["document_id"], [f"{DOCUMENTS}.documents.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        schema=DOCUMENTS,
    )

    # ─── Seed legislation ─────────────────────────────────────────────────
    op.execute(sa.text(f"""
        INSERT INTO {DOCUMENTS}.legislation (name) VALUES
        ('The Companies Act, 2013'),
        ('SEBI (LODR) Regulations, 2015'),
        ('FEMA, 1999'),
        ('Income Tax Act, 1961'),
        ('GST Act, 2017'),
        ('Motor Vehicles Act, 1988'),
        ('Industrial Disputes Act, 1947'),
        ('Consumer Protection Act, 2019'),
        ('Environment Protection Act, 1986'),
        ('Information Technology Act, 2000')
        ON CONFLICT (name) DO NOTHING;
    """))
    op.execute(sa.text(f"""
        INSERT INTO {DOCUMENTS}.sub_legislation (legislation_id, name)
        SELECT l.id, s.name
        FROM {DOCUMENTS}.legislation l
        CROSS JOIN (VALUES
            ('Section 134 – Directors Report'),
            ('Section 177 – Audit Committee'),
            ('Section 188 – Related Party Transactions')
        ) AS s(name)
        WHERE l.name = 'The Companies Act, 2013';
    """))
    op.execute(sa.text(f"""
        INSERT INTO {DOCUMENTS}.sub_legislation (legislation_id, name)
        SELECT l.id, s.name
        FROM {DOCUMENTS}.legislation l
        CROSS JOIN (VALUES
            ('Regulation 17 – Board Composition'),
            ('Regulation 30 – Disclosure of Events'),
            ('Regulation 46 – Website Disclosures')
        ) AS s(name)
        WHERE l.name = 'SEBI (LODR) Regulations, 2015';
    """))
    op.execute(sa.text(f"""
        INSERT INTO {DOCUMENTS}.sub_legislation (legislation_id, name)
        SELECT l.id, s.name
        FROM {DOCUMENTS}.legislation l
        CROSS JOIN (VALUES
            ('Section 6 – Capital Account Transactions'),
            ('Section 7 – Export/Import of Currency')
        ) AS s(name)
        WHERE l.name = 'FEMA, 1999';
    """))


def downgrade() -> None:
    op.drop_table("files", schema=DOCUMENTS)
    op.drop_table("document_revisions", schema=DOCUMENTS)
    op.drop_table("documents", schema=DOCUMENTS)
    op.drop_table("sub_legislation", schema=DOCUMENTS)
    op.drop_table("legislation", schema=DOCUMENTS)
    for name in ("doc_file_type", "doc_applicability_type", "document_status", "document_type"):
        op.execute(sa.text(f"DROP TYPE IF EXISTS {DOCUMENTS}.{name}"))

    op.drop_table("files", schema=EVENTS)
    op.drop_table("event_revisions", schema=EVENTS)
    op.drop_table("events", schema=EVENTS)
    op.drop_index(op.f("ix_events_users_email"), table_name="users", schema=EVENTS)
    op.drop_table("users", schema=EVENTS)
    for name in ("file_type", "applicability_type", "event_status"):
        op.execute(sa.text(f"DROP TYPE IF EXISTS {EVENTS}.{name}"))

    op.execute(sa.text(f"DROP SCHEMA IF EXISTS {DOCUMENTS}"))
    op.execute(sa.text(f"DROP SCHEMA IF EXISTS {EVENTS}"))
