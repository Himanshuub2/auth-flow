"""documents + document_revisions: applicability_refs as varchar(255)[] (not jsonb).

Revision ID: 0008_documents_applicability_refs_varchar255_array
Revises: 0007_document_hub_indexes
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0008_documents_applicability_refs_varchar255_array"
down_revision: Union[str, None] = "0007_document_hub_indexes"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

SCHEMA = "documents"


def upgrade() -> None:
    # documents.applicability_refs
    op.execute(
        sa.text(f"""
DO $$
BEGIN
  IF EXISTS (
    SELECT 1 FROM information_schema.columns c
    WHERE c.table_schema = '{SCHEMA}' AND c.table_name = 'documents'
      AND c.column_name = 'applicability_refs' AND c.data_type = 'jsonb'
  ) THEN
    ALTER TABLE {SCHEMA}.documents
      ALTER COLUMN applicability_refs TYPE varchar(255)[]
      USING CASE WHEN applicability_refs IS NULL THEN NULL
        ELSE COALESCE(
          ARRAY(
            SELECT (jsonb_array_elements_text(applicability_refs))::varchar(255)
          ),
          '{{}}'::varchar(255)[]
        )
      END;
  ELSIF EXISTS (
    SELECT 1 FROM information_schema.columns c
    WHERE c.table_schema = '{SCHEMA}' AND c.table_name = 'documents'
      AND c.column_name = 'applicability_refs' AND c.data_type = 'ARRAY' AND c.udt_name = '_text'
  ) THEN
    ALTER TABLE {SCHEMA}.documents
      ALTER COLUMN applicability_refs TYPE varchar(255)[]
      USING applicability_refs::varchar(255)[];
  END IF;
END$$;
""")
    )
    # document_revisions.applicability_refs
    op.execute(
        sa.text(f"""
DO $$
BEGIN
  IF EXISTS (
    SELECT 1 FROM information_schema.columns c
    WHERE c.table_schema = '{SCHEMA}' AND c.table_name = 'document_revisions'
      AND c.column_name = 'applicability_refs' AND c.data_type = 'jsonb'
  ) THEN
    ALTER TABLE {SCHEMA}.document_revisions
      ALTER COLUMN applicability_refs TYPE varchar(255)[]
      USING CASE WHEN applicability_refs IS NULL THEN NULL
        ELSE COALESCE(
          ARRAY(
            SELECT (jsonb_array_elements_text(applicability_refs))::varchar(255)
          ),
          '{{}}'::varchar(255)[]
        )
      END;
  ELSIF EXISTS (
    SELECT 1 FROM information_schema.columns c
    WHERE c.table_schema = '{SCHEMA}' AND c.table_name = 'document_revisions'
      AND c.column_name = 'applicability_refs' AND c.data_type = 'ARRAY' AND c.udt_name = '_text'
  ) THEN
    ALTER TABLE {SCHEMA}.document_revisions
      ALTER COLUMN applicability_refs TYPE varchar(255)[]
      USING applicability_refs::varchar(255)[];
  END IF;
END$$;
""")
    )


def downgrade() -> None:
    op.execute(
        sa.text(f"""
ALTER TABLE {SCHEMA}.documents
  ALTER COLUMN applicability_refs TYPE text[]
  USING applicability_refs::text[];
""")
    )
    op.execute(
        sa.text(f"""
ALTER TABLE {SCHEMA}.document_revisions
  ALTER COLUMN applicability_refs TYPE text[]
  USING applicability_refs::text[];
""")
    )
