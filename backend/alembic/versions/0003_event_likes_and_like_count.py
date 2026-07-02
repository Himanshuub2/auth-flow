"""event likes table and like_count on events

Revision ID: 0003_event_likes
Revises: 0002_updated_by
Create Date: 2026-04-11

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0003_event_likes"
down_revision: Union[str, None] = "0002_updated_by"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

EVENTS = "events"
USERS = "users"


def upgrade() -> None:
    # Idempotent: 0001_combined may already create like_count + event_likes on fresh installs.
    op.execute(
        sa.text(
            f"""
            ALTER TABLE {EVENTS}.events
            ADD COLUMN IF NOT EXISTS like_count INTEGER NOT NULL DEFAULT 0;
            """
        )
    )
    op.execute(
        sa.text(
            f"""
            CREATE TABLE IF NOT EXISTS {EVENTS}.event_likes (
                id SERIAL PRIMARY KEY,
                event_id INTEGER NOT NULL
                    REFERENCES {EVENTS}.events(id) ON DELETE CASCADE,
                staff_id VARCHAR(255) NOT NULL
                    REFERENCES {USERS}.users(staff_id),
                created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                CONSTRAINT uq_event_likes_event_staff UNIQUE (event_id, staff_id)
            );
            """
        )
    )
    op.execute(
        sa.text(
            f"""
            CREATE INDEX IF NOT EXISTS ix_events_event_likes_event_id
                ON {EVENTS}.event_likes (event_id);
            """
        )
    )
    op.execute(
        sa.text(
            f"""
            CREATE INDEX IF NOT EXISTS ix_events_event_likes_staff_id
                ON {EVENTS}.event_likes (staff_id);
            """
        )
    )


def downgrade() -> None:
    op.drop_index("ix_events_event_likes_staff_id", table_name="event_likes", schema=EVENTS)
    op.drop_index("ix_events_event_likes_event_id", table_name="event_likes", schema=EVENTS)
    op.drop_table("event_likes", schema=EVENTS)
    op.drop_column("events", "like_count", schema=EVENTS)
