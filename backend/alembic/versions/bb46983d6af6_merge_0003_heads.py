"""merge 0003 heads

Revision ID: bb46983d6af6
Revises: 0003_bulk_applicability, 0003_event_likes
Create Date: 2026-04-17 13:18:56.381796

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'bb46983d6af6'
down_revision: Union[str, None] = ('0003_bulk_applicability', '0003_event_likes')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
