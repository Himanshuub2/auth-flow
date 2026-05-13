"""Add applicability_type and applicability_refs to event_revisions.

Revision ID: 0006_event_revision_applicability
Revises: 0004_version_revision_numeric_media
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "0006_event_revision_applicability"
down_revision: Union[str, None] = "0004_version_revision_numeric_media"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

EVENTS_SCHEMA = "events"


def upgrade() -> None:
    op.add_column(
        "event_revisions",
        sa.Column(
            "applicability_type",
            postgresql.ENUM(
                "ALL",
                "DIVISION",
                "EMPLOYEE",
                name="applicability_type",
                schema=EVENTS_SCHEMA,
                create_type=False,
            ),
            nullable=True,
        ),
        schema=EVENTS_SCHEMA,
    )
    op.add_column(
        "event_revisions",
        sa.Column("applicability_refs", postgresql.ARRAY(sa.Text()), nullable=True),
        schema=EVENTS_SCHEMA,
    )

    op.execute(
        sa.text(
            f"""
            UPDATE {EVENTS_SCHEMA}.event_revisions AS er
            SET applicability_type = e.applicability_type,
                applicability_refs = e.applicability_refs
            FROM {EVENTS_SCHEMA}.events AS e
            WHERE er.event_id = e.id
            """
        )
    )

    op.alter_column(
        "event_revisions",
        "applicability_type",
        nullable=False,
        schema=EVENTS_SCHEMA,
    )


def downgrade() -> None:
    op.drop_column("event_revisions", "applicability_refs", schema=EVENTS_SCHEMA)
    op.drop_column("event_revisions", "applicability_type", schema=EVENTS_SCHEMA)
