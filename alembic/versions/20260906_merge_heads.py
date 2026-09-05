"""merge heads

Revision ID: 20260906_merge_heads
Revises: 0001_initial, 20260905_make_buckets_owner_not_null
Create Date: 2026-09-06 00:00:00.000000
"""
from alembic import op


# revision identifiers, used by Alembic.
revision = '20260906_merge_heads'
down_revision = ('0001_initial', '20260905_owner_not_null')
branch_labels = None
depends_on = None


def upgrade():
    # Merge migration: no-op to join two independent migration chains
    pass


def downgrade():
    # Downgrade not supported for merge-only migration
    pass
