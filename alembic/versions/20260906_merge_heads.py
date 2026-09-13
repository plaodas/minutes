"""merge heads (kept as a no-op so existing DBs stay stamped)

Revision ID: 20260906_merge_heads
Revises: 20260905_owner_not_null
Create Date: 2026-09-06 00:00:00.000000

0001_initial is now the parent of 20260829_add_minutes_text, so this
revision no longer needs to join two roots.
"""

# revision identifiers, used by Alembic.
revision = "20260906_merge_heads"
down_revision = "20260905_owner_not_null"
branch_labels = None
depends_on = None


def upgrade():
    # Merge migration: no-op to join two independent migration chains
    pass


def downgrade():
    # Downgrade not supported for merge-only migration
    pass
