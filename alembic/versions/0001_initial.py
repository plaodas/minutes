"""create initial users, tasks and task_history tables

Revision ID: 0001_initial
Revises:
Create Date: 2026-08-28 00:00:00.000000
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = '0001_initial'
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'users',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column('username', sa.String(), nullable=False, unique=True),
        sa.Column('password_hash', sa.String(), nullable=False),
        sa.Column('email', sa.String(), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()')),
    )

    op.create_table(
        'tasks',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('users.id'), nullable=True),
        sa.Column('status', sa.String(), nullable=False),
        sa.Column('progress', sa.Numeric(), nullable=True, server_default='0'),
        sa.Column('result', postgresql.JSONB(), nullable=True),
        sa.Column('fail_count', sa.Integer(), nullable=True, server_default='0'),
        sa.Column('last_failure_ts', sa.DateTime(), nullable=True),
        sa.Column('last_success_ts', sa.DateTime(), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.text('now()')),
        sa.Column('schema_version', sa.Integer(), nullable=False, server_default='1'),
    )
    op.create_index(op.f('ix_tasks_status'), 'tasks', ['status'], unique=False)

    op.create_table(
        'task_history',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('task_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('tasks.id'), nullable=False),
        sa.Column('event_ts', sa.DateTime(), server_default=sa.text('now()')),
        sa.Column('event_type', sa.String(), nullable=True),
        sa.Column('payload', postgresql.JSONB(), nullable=True),
    )


def downgrade():
    op.drop_table('task_history')
    op.drop_index(op.f('ix_tasks_status'), table_name='tasks')
    op.drop_table('tasks')
    op.drop_table('users')
