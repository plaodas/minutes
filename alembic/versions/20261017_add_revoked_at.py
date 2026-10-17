"""add service_tokens.revoked_at

Revision ID: 20261017_add_revoked_at
Revises: 20261017_add_audit_events
Create Date: 2026-10-17 00:00:00.000000
"""

import sqlalchemy as sa

from alembic import op

revision = "20261017_add_revoked_at"
down_revision = "20261017_add_audit_events"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "service_tokens",
        sa.Column("revoked_at", sa.DateTime(), nullable=True),
    )
    op.execute(
        "UPDATE service_tokens SET revoked_at = CURRENT_TIMESTAMP "
        "WHERE revoked IS TRUE AND revoked_at IS NULL"
    )


def downgrade():
    op.drop_column("service_tokens", "revoked_at")
