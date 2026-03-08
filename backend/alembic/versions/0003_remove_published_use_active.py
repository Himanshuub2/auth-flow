"""Replace PUBLISHED with ACTIVE: data migration and enum cleanup.

- Set any PUBLISHED rows to ACTIVE.
- Recreate event_status and document_status enums without PUBLISHED.

Revision ID: 0003_remove_published
Revises: 0002_rename
Create Date: 2026-03-08

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0003_remove_published"
down_revision: Union[str, None] = "0002_rename"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

EVENTS = "events"
DOCUMENTS = "documents"


def upgrade() -> None:
    # 1. Data: map PUBLISHED -> ACTIVE
    op.execute(sa.text(f"UPDATE {EVENTS}.events SET status = 'ACTIVE' WHERE status::text = 'PUBLISHED'"))
    op.execute(sa.text(f"UPDATE {DOCUMENTS}.documents SET status = 'ACTIVE' WHERE status::text = 'PUBLISHED'"))

    # 2. Events: new enum without PUBLISHED (drop default so type change works)
    op.execute(sa.text(f"ALTER TABLE {EVENTS}.events ALTER COLUMN status DROP DEFAULT"))
    op.execute(sa.text(f"CREATE TYPE {EVENTS}.event_status_new AS ENUM ('DRAFT', 'ACTIVE', 'INACTIVE')"))
    op.execute(sa.text(
        f"ALTER TABLE {EVENTS}.events ALTER COLUMN status TYPE {EVENTS}.event_status_new "
        f"USING status::text::{EVENTS}.event_status_new"
    ))
    op.execute(sa.text(f"DROP TYPE {EVENTS}.event_status"))
    op.execute(sa.text(f"ALTER TYPE {EVENTS}.event_status_new RENAME TO event_status"))
    op.execute(sa.text(f"ALTER TABLE {EVENTS}.events ALTER COLUMN status SET DEFAULT 'DRAFT'::{EVENTS}.event_status"))

    # 3. Documents: new enum without PUBLISHED (drop default so type change works)
    op.execute(sa.text(f"ALTER TABLE {DOCUMENTS}.documents ALTER COLUMN status DROP DEFAULT"))
    op.execute(sa.text(f"CREATE TYPE {DOCUMENTS}.document_status_new AS ENUM ('DRAFT', 'ACTIVE', 'INACTIVE')"))
    op.execute(sa.text(
        f"ALTER TABLE {DOCUMENTS}.documents ALTER COLUMN status TYPE {DOCUMENTS}.document_status_new "
        f"USING status::text::{DOCUMENTS}.document_status_new"
    ))
    op.execute(sa.text(f"DROP TYPE {DOCUMENTS}.document_status"))
    op.execute(sa.text(f"ALTER TYPE {DOCUMENTS}.document_status_new RENAME TO document_status"))
    op.execute(sa.text(f"ALTER TABLE {DOCUMENTS}.documents ALTER COLUMN status SET DEFAULT 'DRAFT'::{DOCUMENTS}.document_status"))


def downgrade() -> None:
    # Restore enums with PUBLISHED
    op.execute(sa.text(f"CREATE TYPE {EVENTS}.event_status_old AS ENUM ('DRAFT', 'PUBLISHED', 'ACTIVE', 'INACTIVE')"))
    op.execute(sa.text(
        f"ALTER TABLE {EVENTS}.events ALTER COLUMN status TYPE {EVENTS}.event_status_old "
        f"USING status::text::{EVENTS}.event_status_old"
    ))
    op.execute(sa.text(f"DROP TYPE {EVENTS}.event_status"))
    op.execute(sa.text(f"ALTER TYPE {EVENTS}.event_status_old RENAME TO event_status"))

    op.execute(sa.text(f"CREATE TYPE {DOCUMENTS}.document_status_old AS ENUM ('DRAFT', 'PUBLISHED', 'ACTIVE', 'INACTIVE')"))
    op.execute(sa.text(
        f"ALTER TABLE {DOCUMENTS}.documents ALTER COLUMN status TYPE {DOCUMENTS}.document_status_old "
        f"USING status::text::{DOCUMENTS}.document_status_old"
    ))
    op.execute(sa.text(f"DROP TYPE {DOCUMENTS}.document_status"))
    op.execute(sa.text(f"ALTER TYPE {DOCUMENTS}.document_status_old RENAME TO document_status"))
