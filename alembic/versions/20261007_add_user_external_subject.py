"""add users.external_subject for external provisioning

Revision ID: 20261007_add_user_external_subject
Revises: 20261003_add_task_search_text
Create Date: 2026-10-07 00:00:00.000000
"""

import sqlalchemy as sa

from alembic import op

revision = "20261007_add_user_external_subject"
down_revision = "20261003_add_task_search_text"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "users",
        sa.Column("external_subject", sa.String(length=255), nullable=True),
    )
    op.create_index(
        "ix_users_external_subject",
        "users",
        ["external_subject"],
        unique=True,
    )


def downgrade():
    op.drop_index("ix_users_external_subject", table_name="users")
    op.drop_column("users", "external_subject")
