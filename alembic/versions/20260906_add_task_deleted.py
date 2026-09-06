"""add task deleted columns

Revision ID: 20260906_add_task_deleted
Revises: 20260906_merge_heads
Create Date: 2026-09-06 00:00:00.000000
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '20260906_add_task_deleted'
down_revision = '20260906_merge_heads'
branch_labels = None
depends_on = None


def upgrade():
    # Add soft-delete columns to tasks
    op.add_column('tasks', sa.Column('deleted', sa.Boolean(), nullable=False, server_default=sa.text('false')))
    op.add_column('tasks', sa.Column('deleted_at', sa.DateTime(), nullable=True))


def downgrade():
    # Remove soft-delete columns
    op.drop_column('tasks', 'deleted_at')
    op.drop_column('tasks', 'deleted')
