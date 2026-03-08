"""SQLite-only init: events + documents tables (prefixed names), no schemas.

Use when DATABASE_URL is sqlite. Run: alembic upgrade sqlite@head
Event media table: event_files; documents media: documents_files.

Revision ID: 0001_sqlite
Revises: None
Create Date: 2026-03-08

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0001_sqlite"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = ("sqlite",)
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ─── Events: users ─────────────────────────────────────────────────
    op.create_table(
        "events_users",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column("full_name", sa.String(length=255), nullable=False),
        sa.Column("division_cluster", sa.String(length=100), nullable=True),
        sa.Column("designation", sa.String(length=100), nullable=True),
        sa.Column("policy_hub_admin", sa.Boolean(), server_default=sa.text("0"), nullable=False),
        sa.Column("is_admin", sa.Boolean(), server_default=sa.text("0"), nullable=False),
        sa.Column("knowledge_hub_admin", sa.Boolean(), server_default=sa.text("0"), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_events_users_email"), "events_users", ["email"], unique=True)

    # Default test user (no password; use TESTING_SKIP_AUTH for testing)
    op.execute(
        sa.text(
            "INSERT INTO events_users (email, full_name, policy_hub_admin, is_admin, knowledge_hub_admin) "
            "VALUES ('divyanshu@test.com', 'divyanshu', 0, 1, 0)"
        )
    )

    # ─── Events: events ─────────────────────────────────────────────────
    op.create_table(
        "events_events",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("event_name", sa.String(length=255), nullable=False),
        sa.Column("sub_event_name", sa.String(length=255), nullable=True),
        sa.Column("event_dates", sa.JSON(), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("tags", sa.JSON(), nullable=True),
        sa.Column("current_media_version", sa.Integer(), nullable=False),
        sa.Column("current_revision_number", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("applicability_type", sa.String(length=20), nullable=False),
        sa.Column("applicability_refs", sa.JSON(), nullable=True),
        sa.Column("replaces_document_id", sa.Integer(), nullable=True),
        sa.Column("created_by", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("change_remarks", sa.Text(), nullable=True),
        sa.Column("deactivate_remarks", sa.Text(), nullable=True),
        sa.Column("deactivated_at", sa.DateTime(), nullable=True),
        sa.Column("deactivated_by", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(["created_by"], ["events_users.id"]),
        sa.ForeignKeyConstraint(["replaces_document_id"], ["events_events.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["deactivated_by"], ["events_users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )

    # ─── Events: event_revisions ─────────────────────────────────────────
    op.create_table(
        "event_revisions",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("event_id", sa.Integer(), nullable=False),
        sa.Column("media_version", sa.Integer(), nullable=False),
        sa.Column("revision_number", sa.Integer(), nullable=False),
        sa.Column("event_name", sa.String(length=255), nullable=False),
        sa.Column("sub_event_name", sa.String(length=255), nullable=True),
        sa.Column("event_dates", sa.JSON(), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("tags", sa.JSON(), nullable=True),
        sa.Column("created_by", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("change_remarks", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["created_by"], ["events_users.id"]),
        sa.ForeignKeyConstraint(["event_id"], ["events_events.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("event_id", "media_version", "revision_number", name="uq_event_version_revision"),
    )

    # ─── Events: event_files ─────────────────────────────────────────────
    op.create_table(
        "event_files",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("event_id", sa.Integer(), nullable=False),
        sa.Column("media_versions", sa.JSON(), nullable=False),
        sa.Column("file_type", sa.String(length=20), nullable=False),
        sa.Column("file_url", sa.String(length=500), nullable=False),
        sa.Column("thumbnail_url", sa.String(length=500), nullable=True),
        sa.Column("caption", sa.String(length=255), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("sort_order", sa.Integer(), nullable=False),
        sa.Column("file_size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("original_filename", sa.String(length=255), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.ForeignKeyConstraint(["event_id"], ["events_events.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )

    # ─── Documents: legislation, sub_legislation ─────────────────────────
    op.create_table(
        "documents_legislation",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name", name="uq_legislation_name"),
    )
    op.create_table(
        "documents_sub_legislation",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("legislation_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.ForeignKeyConstraint(["legislation_id"], ["documents_legislation.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )

    # ─── Documents: documents ────────────────────────────────────────────
    op.create_table(
        "documents_documents",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("document_type", sa.String(length=50), nullable=False),
        sa.Column("tags", sa.JSON(), nullable=False),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("legislation_id", sa.Integer(), nullable=True),
        sa.Column("sub_legislation_id", sa.Integer(), nullable=True),
        sa.Column("version", sa.Integer(), server_default=sa.text("1"), nullable=False),
        sa.Column("next_review_date", sa.Date(), nullable=True),
        sa.Column("download_allowed", sa.Boolean(), server_default=sa.text("1"), nullable=False),
        sa.Column("linked_document_ids", sa.JSON(), nullable=True),
        sa.Column("applicability_type", sa.String(length=20), nullable=False, server_default="ALL"),
        sa.Column("applicability_refs", sa.JSON(), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="DRAFT"),
        sa.Column("current_media_version", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("current_revision_number", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("change_remarks", sa.Text(), nullable=True),
        sa.Column("deactivate_remarks", sa.Text(), nullable=True),
        sa.Column("deactivated_at", sa.DateTime(), nullable=True),
        sa.Column("deactivated_by", sa.Integer(), nullable=True),
        sa.Column("replaces_document_id", sa.Integer(), nullable=True),
        sa.Column("created_by", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.ForeignKeyConstraint(["legislation_id"], ["documents_legislation.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["sub_legislation_id"], ["documents_sub_legislation.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["replaces_document_id"], ["documents_documents.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["created_by"], ["events_users.id"]),
        sa.ForeignKeyConstraint(["deactivated_by"], ["events_users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )

    # ─── Documents: document_revisions ────────────────────────────────────
    op.create_table(
        "document_revisions",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("document_id", sa.Integer(), nullable=False),
        sa.Column("media_version", sa.Integer(), nullable=False),
        sa.Column("revision_number", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("document_type", sa.String(length=50), nullable=False),
        sa.Column("tags", sa.JSON(), nullable=True),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("applicability_type", sa.String(length=20), nullable=False, server_default="ALL"),
        sa.Column("applicability_refs", sa.JSON(), nullable=True),
        sa.Column("created_by", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.ForeignKeyConstraint(["document_id"], ["documents_documents.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by"], ["events_users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("document_id", "media_version", "revision_number", name="uq_doc_version_revision"),
    )

    # ─── Documents: documents_files ──────────────────────────────────────
    op.create_table(
        "documents_files",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("document_id", sa.Integer(), nullable=False),
        sa.Column("media_versions", sa.JSON(), nullable=False),
        sa.Column("file_type", sa.String(length=20), nullable=False),
        sa.Column("file_url", sa.String(500), nullable=False),
        sa.Column("original_filename", sa.String(255), nullable=False),
        sa.Column("file_size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("sort_order", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.ForeignKeyConstraint(["document_id"], ["documents_documents.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )

    # ─── Seed legislation ────────────────────────────────────────────────
    op.execute(sa.text("""
        INSERT OR IGNORE INTO documents_legislation (name) VALUES
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
    """))
    op.execute(sa.text("""
        INSERT INTO documents_sub_legislation (legislation_id, name)
        SELECT l.id, 'Section 134 – Directors Report' FROM documents_legislation l WHERE l.name = 'The Companies Act, 2013'
    """))
    op.execute(sa.text("""
        INSERT INTO documents_sub_legislation (legislation_id, name)
        SELECT l.id, 'Section 177 – Audit Committee' FROM documents_legislation l WHERE l.name = 'The Companies Act, 2013'
    """))
    op.execute(sa.text("""
        INSERT INTO documents_sub_legislation (legislation_id, name)
        SELECT l.id, 'Section 188 – Related Party Transactions' FROM documents_legislation l WHERE l.name = 'The Companies Act, 2013'
    """))
    op.execute(sa.text("""
        INSERT INTO documents_sub_legislation (legislation_id, name)
        SELECT l.id, 'Regulation 17 – Board Composition' FROM documents_legislation l WHERE l.name = 'SEBI (LODR) Regulations, 2015'
    """))
    op.execute(sa.text("""
        INSERT INTO documents_sub_legislation (legislation_id, name)
        SELECT l.id, 'Regulation 30 – Disclosure of Events' FROM documents_legislation l WHERE l.name = 'SEBI (LODR) Regulations, 2015'
    """))
    op.execute(sa.text("""
        INSERT INTO documents_sub_legislation (legislation_id, name)
        SELECT l.id, 'Regulation 46 – Website Disclosures' FROM documents_legislation l WHERE l.name = 'SEBI (LODR) Regulations, 2015'
    """))
    op.execute(sa.text("""
        INSERT INTO documents_sub_legislation (legislation_id, name)
        SELECT l.id, 'Section 6 – Capital Account Transactions' FROM documents_legislation l WHERE l.name = 'FEMA, 1999'
    """))
    op.execute(sa.text("""
        INSERT INTO documents_sub_legislation (legislation_id, name)
        SELECT l.id, 'Section 7 – Export/Import of Currency' FROM documents_legislation l WHERE l.name = 'FEMA, 1999'
    """))


def downgrade() -> None:
    op.drop_table("documents_files")
    op.drop_table("document_revisions")
    op.drop_table("documents_documents")
    op.drop_table("documents_sub_legislation")
    op.drop_table("documents_legislation")
    op.drop_table("event_files")
    op.drop_table("event_revisions")
    op.drop_table("events_events")
    op.drop_index(op.f("ix_events_users_email"), table_name="events_users")
    op.drop_table("events_users")
