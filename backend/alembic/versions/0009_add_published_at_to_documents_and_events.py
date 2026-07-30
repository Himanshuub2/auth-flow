"""add published_at to documents and events.

Revision ID: 0009_add_published_at_to_documents_and_events
Revises: 0008_documents_applicability_refs_varchar255_array
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0009_add_published_at_to_documents_and_events"
down_revision: Union[str, None] = "0008_documents_applicability_refs_varchar255_array"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("documents", sa.Column("published_at", sa.DateTime(timezone=True), nullable=True), schema="documents")
    op.add_column("events", sa.Column("published_at", sa.DateTime(timezone=True), nullable=True), schema="events")


def downgrade() -> None:
    op.drop_column("events", "published_at", schema="events")
    op.drop_column("documents", "published_at", schema="documents")
