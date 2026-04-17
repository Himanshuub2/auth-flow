"""add bulk_applicability_requests table

Revision ID: 0003_bulk_applicability
Revises: 0002_updated_by
Create Date: 2026-04-07
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import ENUM, JSONB


revision: str = "0003_bulk_applicability"
down_revision: Union[str, None] = "0002_updated_by"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

SCHEMA = "documents"
USERS_SCHEMA = "users"


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    user_columns = {c["name"] for c in inspector.get_columns("users", schema=USERS_SCHEMA)}
    if "organization_vertical" not in user_columns:
        op.add_column(
            "users",
            sa.Column("organization_vertical", sa.String(length=255), nullable=True),
            schema=USERS_SCHEMA,
        )

    status_enum = ENUM(
        "PENDING",
        "IN_PROGRESS",
        "COMPLETED",
        "FAILED",
        name="bulk_applicability_status",
        schema=SCHEMA,
        create_type=False,
    )
    status_enum.create(bind, checkfirst=True)

    if inspector.has_table("bulk_applicability_requests", schema=SCHEMA):
        return

    op.create_table(
        "bulk_applicability_requests",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("file_name", sa.String(255), nullable=False),
        sa.Column("uploaded_file_url", sa.String(500), nullable=False),
        sa.Column("selected_types", JSONB, nullable=False, server_default="[]"),
        sa.Column(
            "status",
            status_enum,
            nullable=False,
            server_default="PENDING",
        ),
        sa.Column("error_message", sa.Text, nullable=True),
        sa.Column("change_remarks", sa.Text, nullable=True),
        sa.Column("created_by", sa.String(255), nullable=False),
        sa.Column("updated_by", sa.String(255), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["created_by"], ["users.users.staff_id"],
            name="fk_bulk_applicability_created_by",
        ),
        sa.ForeignKeyConstraint(
            ["updated_by"], ["users.users.staff_id"],
            name="fk_bulk_applicability_updated_by",
            ondelete="SET NULL",
        ),
        schema=SCHEMA,
    )

    op.create_index(
        "ix_bulk_applicability_status_created",
        "bulk_applicability_requests",
        ["status", "created_at"],
        schema=SCHEMA,
    )
    op.create_index(
        "ix_bulk_applicability_updated_at",
        "bulk_applicability_requests",
        ["updated_at"],
        schema=SCHEMA,
    )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if inspector.has_table("bulk_applicability_requests", schema=SCHEMA):
        op.drop_index(
            "ix_bulk_applicability_updated_at",
            table_name="bulk_applicability_requests",
            schema=SCHEMA,
        )
        op.drop_index(
            "ix_bulk_applicability_status_created",
            table_name="bulk_applicability_requests",
            schema=SCHEMA,
        )
        op.drop_table("bulk_applicability_requests", schema=SCHEMA)
        op.execute(f"DROP TYPE IF EXISTS {SCHEMA}.bulk_applicability_status;")

    user_columns = {c["name"] for c in inspector.get_columns("users", schema=USERS_SCHEMA)}
    if "organization_vertical" in user_columns:
        op.drop_column("users", "organization_vertical", schema=USERS_SCHEMA)
