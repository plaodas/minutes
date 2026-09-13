"""add task deleted columns

Revision ID: 20260906_add_task_deleted
Revises: 20260906_merge_heads
Create Date: 2026-09-06 00:00:00.000000
"""

from alembic import op

# revision identifiers, used by Alembic.
revision = "20260906_add_task_deleted"
down_revision = "20260906_merge_heads"
branch_labels = None
depends_on = None


def upgrade():
    # 20260901_add_timestamps already adds deleted_at on a linear history.
    op.execute(
        "ALTER TABLE tasks ADD COLUMN IF NOT EXISTS deleted BOOLEAN NOT NULL DEFAULT false"
    )
    op.execute("ALTER TABLE tasks ADD COLUMN IF NOT EXISTS deleted_at TIMESTAMP NULL")


def downgrade():
    # Remove soft-delete columns
    op.drop_column("tasks", "deleted_at")
    op.drop_column("tasks", "deleted")
