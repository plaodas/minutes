"""add buckets table

Revision ID: 20260901_add_buckets_table
Revises: 20260901_add_timestamps
Create Date: 2026-09-01 00:05:00.000000
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision = '20260901_add_buckets_table'
down_revision = '20260901_add_timestamps'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'buckets',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column('name', sa.String(), nullable=False, unique=True),
        sa.Column('owner_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('users.id'), nullable=True),
        sa.Column('public', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('metadata', postgresql.JSONB(), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.text('now()')),
        sa.Column('deleted_at', sa.DateTime(), nullable=True),
    )
    op.create_index(op.f('ix_buckets_name'), 'buckets', ['name'], unique=True)


def downgrade():
    op.drop_index(op.f('ix_buckets_name'), table_name='buckets')
    op.drop_table('buckets')
