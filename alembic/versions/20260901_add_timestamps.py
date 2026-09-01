"""add created_at/updated_at/deleted_at columns where missing

Revision ID: 20260901_add_timestamps
Revises: 20260829_task_history_index
Create Date: 2026-09-01 00:00:00.000000
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '20260901_add_timestamps'
down_revision = '20260829_task_history_index'
branch_labels = None
depends_on = None


def upgrade():
    # users: ensure updated_at and deleted_at
    op.execute("""
    ALTER TABLE users
      ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP DEFAULT now();
    """)
    op.execute("""
    ALTER TABLE users
      ADD COLUMN IF NOT EXISTS deleted_at TIMESTAMP NULL;
    """)

    # tasks: ensure deleted_at
    op.execute("""
    ALTER TABLE tasks
      ADD COLUMN IF NOT EXISTS deleted_at TIMESTAMP NULL;
    """)

    # task_history: ensure created_at, updated_at, deleted_at
    op.execute("""
    ALTER TABLE task_history
      ADD COLUMN IF NOT EXISTS created_at TIMESTAMP DEFAULT now();
    """)
    op.execute("""
    ALTER TABLE task_history
      ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP DEFAULT now();
    """)
    op.execute("""
    ALTER TABLE task_history
      ADD COLUMN IF NOT EXISTS deleted_at TIMESTAMP NULL;
    """)


def downgrade():
    # remove columns if they exist
    op.execute("""
    ALTER TABLE task_history DROP COLUMN IF EXISTS deleted_at;
    ALTER TABLE task_history DROP COLUMN IF EXISTS updated_at;
    ALTER TABLE task_history DROP COLUMN IF EXISTS created_at;
    """)
    op.execute("""
    ALTER TABLE tasks DROP COLUMN IF EXISTS deleted_at;
    """)
    op.execute("""
    ALTER TABLE users DROP COLUMN IF EXISTS deleted_at;
    ALTER TABLE users DROP COLUMN IF EXISTS updated_at;
    """)
