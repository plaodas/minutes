"""add tasks.name for history titles

Revision ID: 20260913_add_task_name
Revises: 20260912_task_status_stage
Create Date: 2026-09-13 00:00:00.000000
"""

from alembic import op

revision = "20260913_add_task_name"
down_revision = "20260912_task_status_stage"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("ALTER TABLE tasks ADD COLUMN IF NOT EXISTS name VARCHAR(255)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_tasks_name ON tasks (name)")


def downgrade():
    op.execute("DROP INDEX IF EXISTS ix_tasks_name")
    op.execute("ALTER TABLE tasks DROP COLUMN IF EXISTS name")
