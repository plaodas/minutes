"""make buckets.owner_id non-null with server_default

Revision ID: 20260905_make_buckets_owner_not_null
Revises: 20260901_add_buckets_table
Create Date: 2026-09-05 00:00:00.000000
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision = '20260905_make_buckets_owner_not_null'
down_revision = '20260901_add_buckets_table'
branch_labels = None
depends_on = None


def upgrade():
    dummy = '00000000-0000-0000-0000-000000000000'
    # Set existing NULL owner_id values to the dummy UUID
    op.execute(f"UPDATE buckets SET owner_id = '{dummy}' WHERE owner_id IS NULL;")

    # Alter column: set server_default and make NOT NULL
    op.alter_column(
        'buckets',
        'owner_id',
        existing_type=postgresql.UUID(as_uuid=True),
        nullable=False,
        server_default=sa.text(f"'{dummy}'::uuid"),
    )


def downgrade():
    dummy = '00000000-0000-0000-0000-000000000000'
    # Remove server_default and allow NULL again
    op.alter_column(
        'buckets',
        'owner_id',
        existing_type=postgresql.UUID(as_uuid=True),
        nullable=True,
        server_default=None,
    )

    # Optionally revert dummy values to NULL (best-effort)
    op.execute(f"UPDATE buckets SET owner_id = NULL WHERE owner_id = '{dummy}';")
