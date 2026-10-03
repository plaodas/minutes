"""add tasks.search_text for history search

Revision ID: 20261003_add_task_search_text
Revises: 20260913_add_task_name
Create Date: 2026-10-03 00:00:00.000000
"""

import sqlalchemy as sa

from alembic import op

revision = "20261003_add_task_search_text"
down_revision = "20260913_add_task_name"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("tasks", sa.Column("search_text", sa.Text(), nullable=True))
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return

    op.execute("""
        UPDATE tasks
        SET search_text = lower(
            concat_ws(
                E'\\n',
                NULLIF(name, ''),
                NULLIF(result->>'transcript', ''),
                NULLIF(result->>'summary', ''),
                NULLIF(result->>'minutes', '')
            )
        )
        WHERE search_text IS NULL
        """)
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_tasks_search_text_trgm
        ON tasks USING gin (search_text gin_trgm_ops)
        """)


def downgrade():
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute("DROP INDEX IF EXISTS idx_tasks_search_text_trgm")
    op.drop_column("tasks", "search_text")
