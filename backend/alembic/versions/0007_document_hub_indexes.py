"""B-tree indexes for document hub filtering/sorting and files by document."""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0007_document_hub_indexes"
down_revision: Union[str, None] = "0006_event_revision_applicability"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

DOCUMENTS = "documents"


def upgrade() -> None:
    # Partial index: hub only lists ACTIVE rows with no superseding document_id.
    op.execute(
        sa.text(f"""
CREATE INDEX ix_documents_hub_type_updated
ON {DOCUMENTS}.documents (document_type, updated_at DESC NULLS LAST)
WHERE status = 'ACTIVE' AND replaces_document_id IS NULL
""")
    )
    # DISTINCT ON flyer lookup + general file lookups by document.
    op.create_index(
        "ix_files_document_sort",
        "files",
        ["document_id", "sort_order", "id"],
        schema=DOCUMENTS,
    )


def downgrade() -> None:
    op.drop_index("ix_files_document_sort", table_name="files", schema=DOCUMENTS)
    op.drop_index("ix_documents_hub_type_updated", table_name="documents", schema=DOCUMENTS)
