"""Rename draft_parent_id to replaces_document_id (events and documents).

For DBs created with old migrations that had draft_parent_id.
No-op if column is already replaces_document_id (e.g. from 0001_combined).

Revision ID: 0002_rename
Revises: 0001_combined
Create Date: 2026-03-07

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0002_rename"
down_revision: Union[str, None] = "0001_combined"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Only rename if draft_parent_id exists (old DBs)
    op.execute(sa.text("""
        DO $$ BEGIN
            IF EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_schema = 'events' AND table_name = 'events' AND column_name = 'draft_parent_id'
            ) THEN
                ALTER TABLE events.events RENAME COLUMN draft_parent_id TO replaces_document_id;
            END IF;
        END $$
    """))
    op.execute(sa.text("""
        DO $$ BEGIN
            IF EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_schema = 'documents' AND table_name = 'documents' AND column_name = 'draft_parent_id'
            ) THEN
                ALTER TABLE documents.documents RENAME COLUMN draft_parent_id TO replaces_document_id;
            END IF;
        END $$
    """))


def downgrade() -> None:
    op.execute(sa.text("""
        DO $$ BEGIN
            IF EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_schema = 'events' AND table_name = 'events' AND column_name = 'replaces_document_id'
            ) THEN
                ALTER TABLE events.events RENAME COLUMN replaces_document_id TO draft_parent_id;
            END IF;
        END $$
    """))
    op.execute(sa.text("""
        DO $$ BEGIN
            IF EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_schema = 'documents' AND table_name = 'documents' AND column_name = 'replaces_document_id'
            ) THEN
                ALTER TABLE documents.documents RENAME COLUMN replaces_document_id TO draft_parent_id;
            END IF;
        END $$
    """))
