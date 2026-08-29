"""create index on task_history(task_id, event_ts desc)

Revision ID: 20260829_task_history_index
Revises: 20260829_add_minutes_text
Create Date: 2026-08-29 00:00:00.000001
"""
from alembic import op

# revision identifiers, used by Alembic.
revision = '20260829_task_history_index'
down_revision = '20260829_add_minutes_text'
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
    CREATE INDEX IF NOT EXISTS idx_task_history_task_id_event_ts ON task_history (task_id, event_ts DESC);
    """)


def downgrade():
    op.execute("""
    DROP INDEX IF EXISTS idx_task_history_task_id_event_ts;
    """)
