import logging

from minutes.celery_app import celery
from minutes.pipeline.formatting import (
    build_system_prompt as _build_system_prompt,
)
from minutes.pipeline.task_runner import run_audio_pipeline
from minutes.task_deletion import delete_task_permanently


def build_system_prompt(meta_obj):
    return _build_system_prompt(meta_obj)


@celery.task(bind=True)
def hard_delete_task(self, task_id: str, requester: str | None = None):
    """Admin Celery job: delete MinIO objects for a task and remove DB rows.

    This task is retryable by Celery if MinIO deletion fails.
    """
    return delete_task_permanently(task_id, requester)


@celery.task(bind=True)
def process_audio(self, input_path: str):
    """Run the shared audio pipeline and persist its task lifecycle."""
    task_id = getattr(self.request, "id", None)
    logging.getLogger("minutes.tasks").info(
        "process_audio start: task_id=%r input=%s", task_id, input_path
    )
    return run_audio_pipeline(input_path, task_id)
