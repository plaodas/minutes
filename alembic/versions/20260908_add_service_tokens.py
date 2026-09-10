"""add service_tokens table

Revision ID: 20260908_add_service_tokens
Revises: 20260907_add_users_is_admin
Create Date: 2026-09-08 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "20260908_add_service_tokens"
down_revision = "20260907_add_users_is_admin"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "service_tokens",
        sa.Column(
            "id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False
        ),
        sa.Column("name", sa.String(), nullable=True),
        sa.Column("token_hash", sa.String(), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("revoked", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()")),
    )
    op.create_index(
        op.f("ix_service_tokens_token_hash"),
        "service_tokens",
        ["token_hash"],
        unique=True,
    )


def downgrade():
    op.drop_index(op.f("ix_service_tokens_token_hash"), table_name="service_tokens")
    op.drop_table("service_tokens")
