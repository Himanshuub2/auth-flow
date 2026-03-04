"""initialize db

Revision ID: 9830694260df
Revises: 
Create Date: 2026-03-04 11:45:25.547795

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '9830694260df'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(sa.text('CREATE SCHEMA IF NOT EXISTS ecp_events'))
    op.execute(sa.text('CREATE SCHEMA IF NOT EXISTS ecp_documents'))
    for name, values in [
        ("event_status", "'DRAFT', 'PUBLISHED', 'ACTIVE', 'INACTIVE'"),
        ("applicability_type", "'ALL', 'DIVISION', 'EMPLOYEE'"),
        ("file_type", "'IMAGE', 'VIDEO'"),
    ]:
        op.execute(
            sa.text(
                f"DO $$ BEGIN CREATE TYPE {name} AS ENUM ({values}); EXCEPTION WHEN duplicate_object THEN NULL; END $$;"
            )
        )

    op.create_table('users',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('email', sa.String(length=255), nullable=False),
    sa.Column('password_hash', sa.String(length=255), nullable=False),
    sa.Column('full_name', sa.String(length=255), nullable=False),
    sa.Column('division_cluster', sa.String(length=100), nullable=True),
    sa.Column('designation', sa.String(length=100), nullable=True),
    sa.Column('policy_hub_admin', sa.Boolean(), server_default=sa.text('false'), nullable=False),
    sa.Column('is_admin', sa.Boolean(), server_default=sa.text('false'), nullable=False),
    sa.Column('knowledge_hub_admin', sa.Boolean(), server_default=sa.text('false'), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.PrimaryKeyConstraint('id'),
    schema='ecp_events'
    )
    op.create_index(op.f('ix_ecp_events_users_email'), 'users', ['email'], unique=True, schema='ecp_events')
    op.create_table('events',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('event_name', sa.String(length=255), nullable=False),
    sa.Column('sub_event_name', sa.String(length=255), nullable=True),
    sa.Column('event_dates', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    sa.Column('description', sa.Text(), nullable=True),
    sa.Column('tags', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    sa.Column('current_media_version', sa.Integer(), nullable=False),
    sa.Column('current_revision_number', sa.Integer(), nullable=False),
    sa.Column('status', postgresql.ENUM('DRAFT', 'PUBLISHED', 'ACTIVE', 'INACTIVE', name='event_status', create_type=False), nullable=False),
    sa.Column('applicability_type', postgresql.ENUM('ALL', 'DIVISION', 'EMPLOYEE', name='applicability_type', create_type=False), nullable=False),
    sa.Column('applicability_refs', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    sa.Column('draft_parent_id', sa.Integer(), nullable=True),
    sa.Column('created_by', sa.Integer(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['created_by'], ['ecp_events.users.id'], ),
    sa.ForeignKeyConstraint(['draft_parent_id'], ['ecp_events.events.id'], ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id'),
    schema='ecp_events'
    )
    op.create_table('event_revisions',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('event_id', sa.Integer(), nullable=False),
    sa.Column('media_version', sa.Integer(), nullable=False),
    sa.Column('revision_number', sa.Integer(), nullable=False),
    sa.Column('event_name', sa.String(length=255), nullable=False),
    sa.Column('sub_event_name', sa.String(length=255), nullable=True),
    sa.Column('event_dates', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    sa.Column('description', sa.Text(), nullable=True),
    sa.Column('tags', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    sa.Column('created_by', sa.Integer(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['created_by'], ['ecp_events.users.id'], ),
    sa.ForeignKeyConstraint(['event_id'], ['ecp_events.events.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('event_id', 'media_version', 'revision_number', name='uq_event_version_revision'),
    schema='ecp_events'
    )
    op.create_table('files',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('event_id', sa.Integer(), nullable=False),
    sa.Column('media_versions', postgresql.ARRAY(sa.Integer()), nullable=False),
    sa.Column('file_type', postgresql.ENUM('IMAGE', 'VIDEO', name='file_type', create_type=False), nullable=False),
    sa.Column('file_url', sa.String(length=500), nullable=False),
    sa.Column('thumbnail_url', sa.String(length=500), nullable=True),
    sa.Column('caption', sa.String(length=255), nullable=True),
    sa.Column('description', sa.Text(), nullable=True),
    sa.Column('sort_order', sa.Integer(), nullable=False),
    sa.Column('file_size_bytes', sa.BigInteger(), nullable=False),
    sa.Column('original_filename', sa.String(length=255), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['event_id'], ['ecp_events.events.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    schema='ecp_events'
    )


def downgrade() -> None:
    op.drop_table('files', schema='ecp_events')
    op.drop_table('event_revisions', schema='ecp_events')
    op.drop_table('events', schema='ecp_events')
    op.drop_index(op.f('ix_ecp_events_users_email'), table_name='users', schema='ecp_events')
    op.drop_table('users', schema='ecp_events')
    for name in ("file_type", "applicability_type", "event_status"):
        op.execute(sa.text(f"DROP TYPE IF EXISTS {name}"))
