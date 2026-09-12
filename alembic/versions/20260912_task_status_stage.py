"""constrain tasks.status to TaskStage values

Revision ID: 20260912_task_status_stage
Revises: 20260908_add_service_tokens
Create Date: 2026-09-12 00:00:00.000000
"""

import sqlalchemy as sa

from alembic import op

revision = "20260912_task_status_stage"
down_revision = "20260908_add_service_tokens"
branch_labels = None
depends_on = None

# Keep in sync with minutes.schemas.TaskStage values.
_TASK_STAGES = (
    "pending",
    "preprocess",
    "transcribing",
    "formatting",
    "success",
    "failed",
    "cancelled",
    "deleted",
)


def upgrade():
    quoted = ", ".join(f"'{stage}'" for stage in _TASK_STAGES)
    op.execute(
        sa.text(f"UPDATE tasks SET status = 'pending' WHERE status NOT IN ({quoted})")
    )
    op.create_check_constraint(
        "ck_tasks_status_stage",
        "tasks",
        f"status IN ({quoted})",
    )


def downgrade():
    op.drop_constraint("ck_tasks_status_stage", "tasks", type_="check")
