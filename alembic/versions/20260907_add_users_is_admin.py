"""add is_admin column to users table

Revision ID: 20260907_add_users_is_admin
Revises: 20260906_add_task_deleted
Create Date: 2026-09-07 00:00:00.000000
"""
from alembic import op
import sqlalchemy as sa

revision = '20260907_add_users_is_admin'
down_revision = '20260906_add_task_deleted'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('users', sa.Column('is_admin', sa.Boolean(), nullable=False, server_default='false'))


def downgrade():
    op.drop_column('users', 'is_admin')
