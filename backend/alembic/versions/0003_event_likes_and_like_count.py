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
    op.add_column(
        "events",
        sa.Column("like_count", sa.Integer(), nullable=False, server_default="0"),
        schema=EVENTS,
    )
    op.create_table(
        "event_likes",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("event_id", sa.Integer(), nullable=False),
        sa.Column("staff_id", sa.String(length=255), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["event_id"], [f"{EVENTS}.events.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["staff_id"], [f"{USERS}.users.staff_id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("event_id", "staff_id", name="uq_event_likes_event_staff"),
        schema=EVENTS,
    )
    op.create_index(
        "ix_events_event_likes_event_id",
        "event_likes",
        ["event_id"],
        unique=False,
        schema=EVENTS,
    )
    op.create_index(
        "ix_events_event_likes_staff_id",
        "event_likes",
        ["staff_id"],
        unique=False,
        schema=EVENTS,
    )


def downgrade() -> None:
    op.drop_index("ix_events_event_likes_staff_id", table_name="event_likes", schema=EVENTS)
    op.drop_index("ix_events_event_likes_event_id", table_name="event_likes", schema=EVENTS)
    op.drop_table("event_likes", schema=EVENTS)
    op.drop_column("events", "like_count", schema=EVENTS)
