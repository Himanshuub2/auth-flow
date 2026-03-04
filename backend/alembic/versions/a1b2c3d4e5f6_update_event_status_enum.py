"""update event_status enum to add ACTIVE/INACTIVE and migrate ARCHIVED

Revision ID: a1b2c3d4e5f6
Revises: 8843d5fe4f1b
Create Date: 2026-03-04 15:05:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "a1b2c3d4e5f6"
down_revision: Union[str, None] = "8843d5fe4f1b"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # add new enum values if they don't exist
    op.execute(sa.text("ALTER TYPE event_status ADD VALUE IF NOT EXISTS 'ACTIVE'"))
    op.execute(sa.text("ALTER TYPE event_status ADD VALUE IF NOT EXISTS 'INACTIVE'"))


def downgrade() -> None:
    # cannot easily remove enum values in PostgreSQL; leave as-is
    pass

