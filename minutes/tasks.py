import datetime
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
from minutes.pipeline.artifacts import write_text_atomic
from minutes.pipeline.audio import prepare_audio
from minutes.pipeline.formatting import (
    build_pipeline_result,
    format_transcript,
)
from minutes.pipeline.formatting import (
    build_system_prompt as _build_system_prompt,
)
from minutes.pipeline.storage import cache_minutes_artifact
from minutes.pipeline.transcription import transcribe_locally, transcribe_remotely
from minutes.schemas import TaskStage
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
    """Celery task: preprocess -> transcribe -> format.

    On success/failure this task will update the shared `bg_tasks.json`
    so the FastAPI endpoints can return consistent state for background
    jobs regardless of whether they were started via BackgroundTasks
    or Celery.
    """
    task_id = getattr(self.request, "id", None)
    # Debug: log task id and input path early so we can correlate DB rows
    # with worker processing.
    logger = logging.getLogger("minutes.tasks")
    logger.info("process_audio start: task_id=%r input=%s", task_id, input_path)
    # also print to stdout for immediate worker logs visibility
    print(f"DEBUG process_audio start task_id={task_id!r} input={input_path}")
    # Do NOT hold a long-lived DB session during preprocessing/transcription.
    # `update_task_*` helper functions manage their own short-lived sessions.
    try:
        # mark preprocessing stage
        logger = logging.getLogger("minutes.tasks")
        if task_id:
            logger.debug(
                "process_audio: setting task status 'preprocess' for %s", task_id
            )
            update_task_status(task_id, TaskStage.PREPROCESS)
            logger.debug("process_audio: update_task_status returned for %s", task_id)

        try:
            prepared = prepare_audio(input_path, preprocess)
        except (RuntimeError, OSError, ValueError, TypeError) as e:
            logger.exception("process_audio: preprocess failed for %s", input_path)
            # Record failure in task store if possible, then re-raise
            if task_id:
                try:
                    update_task_failure(task_id, f"preprocess failed: {e}")
                except SQLAlchemyError:
                    logger.exception(
                        "process_audio: failed to record preprocess failure for %s",
                        task_id,
                    )
            raise
        mono = prepared.mono
        norm = prepared.normalized
        clean = prepared.clean
        audio_duration = prepared.duration_seconds

        # If an external inference service is configured, call it via HTTP.
        inference_url = os.environ.get("INFERENCE_URL")
        # mark transcribing stage before calling inference/local transcribe
        if task_id:
            update_task_status(task_id, TaskStage.TRANSCRIBING)

        if inference_url:
            transcription = transcribe_remotely(
                clean,
                inference_url=inference_url,
                duration_seconds=audio_duration,
                post=requests.post,
                update_status=lambda stage, detail=None: (
                    update_task_status(task_id, stage, detail) if task_id else None
                ),
                update_progress=lambda progress: (
                    update_task_progress(task_id, progress) if task_id else None
                ),
            )
        else:
            transcription = transcribe_locally(
                clean,
                duration_seconds=audio_duration,
                transcriber=transcribe,
                update_status=lambda stage, detail=None: (
                    update_task_status(task_id, stage, detail) if task_id else None
                ),
                update_progress=lambda progress: (
                    update_task_progress(task_id, progress) if task_id else None
                ),
            )
            raw_text = transcription.raw_text
            segments = transcription.segments

        # mark formatting stage
        if task_id:
            update_task_status(task_id, TaskStage.FORMATTING)

        # Attempt to read task metadata to customize the formatting prompt
        meta = None
        try:
            if task_id:
                trec = get_task(task_id)
                if trec:
                    meta = trec.get("result") or {}
        except SQLAlchemyError:
            meta = None

        final_minutes = format_transcript(raw_text, meta, format_minutes_from_raw)

        now = datetime.datetime.now(tz=datetime.timezone.utc).strftime("%Y%m%d%H%M%S")
        outputs_dir = os.environ.get("OUTPUTS_DIR", "outputs")
        out_file = os.path.join(outputs_dir, f"minutes_{now}.txt")
        write_text_atomic(final_minutes, out_file)

        structured = build_pipeline_result(
            transcript=raw_text,
            segments=segments,
            minutes=final_minutes,
            output_file=out_file,
        )

        minio_artifact = cache_minutes_artifact(task_id, now, out_file)
        if minio_artifact:
            structured["minio"] = minio_artifact

        # Update shared task store for API visibility with structured result
        if task_id:
            update_task_success(task_id, structured)

        # Optionally remove intermediate files produced by preprocessing
        try:
            DELETE_INTERMEDIATE = os.environ.get(
                "DELETE_INTERMEDIATE", "true"
            ).lower() in ("1", "true", "yes")
            if DELETE_INTERMEDIATE:
                # Only remove files that are in the same directory as the input_path
                base_dir = os.path.dirname(os.path.abspath(input_path)) or os.getcwd()
                for p in (mono, norm, clean):
                    try:
                        if not p:
                            continue
                        p_abs = os.path.abspath(p)
                        # safety check: ensure the intermediate lives under the same directory
                        if not p_abs.startswith(base_dir):
                            logger = logging.getLogger("minutes.tasks")
                            logger.warning(
                                "Skipping removal of intermediate outside base dir: %s",
                                p_abs,
                            )
                            continue
                        if os.path.exists(p_abs):
                            os.remove(p_abs)
                            logger = logging.getLogger("minutes.tasks")
                            logger.info(
                                "Removed intermediate file %s for task %s",
                                p_abs,
                                task_id,
                            )
                    except OSError:
                        logger = logging.getLogger("minutes.tasks")
                        logger.exception(
                            "Failed to remove intermediate %s for task %s", p, task_id
                        )
        except (OSError, ValueError):
            logging.getLogger("minutes.tasks").exception(
                "Error while cleaning intermediates"
            )

        return {"status": "success", "result": structured}
    except (
        RuntimeError,
        ValueError,
        TypeError,
        OSError,
        RequestException,
        SQLAlchemyError,
    ) as e:
        # Record failure in shared store if possible
        if task_id:
            try:
                update_task_failure(task_id, str(e))
            except SQLAlchemyError:
                pass
        raise
