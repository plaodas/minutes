import logging
import os

import requests
from requests.exceptions import RequestException
from sqlalchemy.exc import SQLAlchemyError

from minutes.audio import preprocess
from minutes.bg_store import (
    get_task,
    update_task_failure,
    update_task_progress,
    update_task_status,
    update_task_success,
)
from minutes.celery_app import celery
from minutes.ollama import format_minutes_from_raw
from minutes.pipeline.formatting import (
    build_system_prompt as _build_system_prompt,
)
from minutes.pipeline.service import PipelineService
from minutes.task_deletion import delete_task_permanently
from minutes.transcribe import transcribe


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
    logger = logging.getLogger("minutes.tasks")
    logger.info("process_audio start: task_id=%r input=%s", task_id, input_path)

    try:
        metadata = None
        if task_id:
            try:
                task = get_task(task_id)
                if task:
                    metadata = task.get("result") or {}
            except SQLAlchemyError:
                logger.exception("Failed to load metadata for task %s", task_id)

        service = PipelineService(
            preprocess=preprocess,
            transcriber=transcribe,
            formatter=format_minutes_from_raw,
            post=requests.post,
        )
        structured = service.run(
            input_path,
            task_id=task_id,
            metadata=metadata,
            update_status=lambda stage, detail=None: (
                update_task_status(task_id, stage, detail) if task_id else None
            ),
            update_progress=lambda progress: (
                update_task_progress(task_id, progress) if task_id else None
            ),
            inference_url=os.environ.get("INFERENCE_URL"),
            delete_intermediate=os.environ.get(
                "DELETE_INTERMEDIATE", "true"
            ).lower()
            in ("1", "true", "yes"),
        )
        if task_id:
            update_task_success(task_id, structured)
        return {"status": "success", "result": structured}
    except (
        RuntimeError,
        ValueError,
        TypeError,
        OSError,
        RequestException,
        SQLAlchemyError,
    ) as exc:
        if task_id:
            try:
                update_task_failure(task_id, str(exc))
            except SQLAlchemyError:
                logger.exception("Failed to record task failure for %s", task_id)
        raise
