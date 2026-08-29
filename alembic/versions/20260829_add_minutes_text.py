"""add minutes_text column and search indexes

Revision ID: 20260829_add_minutes_text
Revises:
Create Date: 2026-08-29 00:00:00.000000
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '20260829_add_minutes_text'
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    # add minutes_text column if not exists
    op.execute("""
    ALTER TABLE tasks ADD COLUMN IF NOT EXISTS minutes_text TEXT;
    """)

    # enable pg_trgm extension if available
    op.execute("""
    CREATE EXTENSION IF NOT EXISTS pg_trgm;
    """)

    # trigram GIN index for similarity searches
    op.execute("""
    CREATE INDEX IF NOT EXISTS idx_tasks_minutes_text_trgm ON tasks USING gin (minutes_text gin_trgm_ops);
    """)

    # GIN tsvector expression index for full-text search
    op.execute("""
    CREATE INDEX IF NOT EXISTS idx_tasks_minutes_text_tsv ON tasks USING gin (to_tsvector('simple', COALESCE(minutes_text, '')));
    """)


def downgrade():
    op.execute("""
    DROP INDEX IF EXISTS idx_tasks_minutes_text_tsv;
    DROP INDEX IF EXISTS idx_tasks_minutes_text_trgm;
    ALTER TABLE tasks DROP COLUMN IF EXISTS minutes_text;
    """)
