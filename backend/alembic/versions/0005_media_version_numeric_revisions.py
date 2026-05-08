"""change media_version in revisions to numeric

Revision ID: 0005_media_version_numeric
Revises: 0004_version_revision
Create Date: 2026-05-08
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "0005_media_version_numeric"
down_revision: Union[str, None] = "0004_version_revision"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

EVENTS_SCHEMA = "events"
DOCUMENTS_SCHEMA = "documents"


def upgrade() -> None:
    op.alter_column(
        "event_revisions",
        "media_version",
        type_=sa.Numeric(10, 2),
        postgresql_using="media_version::numeric(10,2)",
        existing_nullable=False,
        schema=EVENTS_SCHEMA,
    )

    op.alter_column(
        "document_revisions",
        "media_version",
        type_=sa.Numeric(10, 2),
        postgresql_using="media_version::numeric(10,2)",
        existing_nullable=False,
        schema=DOCUMENTS_SCHEMA,
    )


def downgrade() -> None:
    op.alter_column(
        "document_revisions",
        "media_version",
        type_=sa.Integer(),
        postgresql_using="media_version::integer",
        existing_nullable=False,
        schema=DOCUMENTS_SCHEMA,
    )

    op.alter_column(
        "event_revisions",
        "media_version",
        type_=sa.Integer(),
        postgresql_using="media_version::integer",
        existing_nullable=False,
        schema=EVENTS_SCHEMA,
    )
