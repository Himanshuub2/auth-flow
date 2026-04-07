"""add updated_by to events and documents

Revision ID: 0002_updated_by
Revises: 0001_combined
Create Date: 2026-04-07
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "0002_updated_by"
down_revision: Union[str, None] = "0001_combined"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "events",
        sa.Column("updated_by", sa.String(length=255), nullable=True),
        schema="events",
    )
    op.add_column(
        "documents",
        sa.Column("updated_by", sa.String(length=255), nullable=True),
        schema="documents",
    )

    op.create_foreign_key(
        "fk_events_updated_by_users",
        "events",
        "users",
        ["updated_by"],
        ["staff_id"],
        source_schema="events",
        referent_schema="users",
        ondelete="SET NULL",
    )
    op.create_foreign_key(
        "fk_documents_updated_by_users",
        "documents",
        "users",
        ["updated_by"],
        ["staff_id"],
        source_schema="documents",
        referent_schema="users",
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint("fk_documents_updated_by_users", "documents", schema="documents", type_="foreignkey")
    op.drop_constraint("fk_events_updated_by_users", "events", schema="events", type_="foreignkey")
    op.drop_column("documents", "updated_by", schema="documents")
    op.drop_column("events", "updated_by", schema="events")
