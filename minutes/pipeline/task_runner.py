import logging
import os
from typing import Any

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
from minutes.ollama import format_minutes_from_raw
from minutes.pipeline.service import PipelineService
from minutes.transcribe import transcribe

logger = logging.getLogger("minutes.pipeline.task_runner")


def run_audio_pipeline(input_path: str, task_id: str | None = None) -> dict[str, Any]:
    """Run the shared pipeline and persist success or failure for a task."""
    logger.info("audio pipeline start: task_id=%r input=%s", task_id, input_path)
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
            delete_intermediate=os.environ.get("DELETE_INTERMEDIATE", "true").lower()
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
