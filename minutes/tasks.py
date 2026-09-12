import datetime
import json
import logging
import os

import requests
from requests.exceptions import ChunkedEncodingError, RequestException
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
            # Call inference endpoint and stream NDJSON lines for progress.
            # If the chunked stream unexpectedly ends, retry once using a
            # non-streaming fallback to obtain the final output.
            logger = logging.getLogger("minutes.tasks")
            raw_text = ""
            segments = []
            with open(clean, "rb") as fh:
                files = {"file": (os.path.basename(clean), fh, "audio/wav")}
                try:
                    size = os.path.getsize(clean) if os.path.exists(clean) else None
                except OSError:
                    size = None
                logger.info(
                    "inference: calling %s file=%s size=%s",
                    inference_url,
                    os.path.basename(clean),
                    size,
                )
                try_stream = True
                attempts = 0
                max_attempts = 3
                backoff = 1
                while attempts < max_attempts:
                    attempts += 1
                    try:
                        resp = requests.post(
                            inference_url,
                            files=files,
                            stream=True,
                            timeout=(5, 360),
                            headers={"Connection": "keep-alive"},
                        )
                        logger.info(
                            "inference: http POST sent (attempt=%s) -> status=%s",
                            attempts,
                            getattr(resp, "status_code", None),
                        )
                        try:
                            logger.debug(
                                "inference response headers: %s", dict(resp.headers)
                            )
                        except (TypeError, AttributeError):
                            pass
                        resp.raise_for_status()
                        # parse NDJSON stream
                        for line in resp.iter_lines(
                            decode_unicode=True, chunk_size=1024
                        ):
                            if not line:
                                continue
                            logger.debug(
                                "inference: ndjson raw line: %s",
                                (
                                    line[:200]
                                    if isinstance(line, str)
                                    else str(line)[:200]
                                ),
                            )
                            try:
                                obj = json.loads(line)
                            except json.JSONDecodeError:
                                logger.debug(
                                    "inference: failed to parse ndjson line: %r",
                                    (
                                        line[:200]
                                        if isinstance(line, str)
                                        else str(line)[:200]
                                    ),
                                )
                                continue
                            typ = obj.get("type")
                            if typ == "heartbeat":
                                # ignore heartbeats
                                continue
                            if typ == "segment":
                                try:
                                    end = float(obj.get("end", 0.0) or 0.0)
                                    if task_id:
                                        update_task_status(
                                            task_id, f"transcribing:{end:.1f}s"
                                        )
                                        if audio_duration and audio_duration > 0:
                                            pct = min(
                                                100.0, (end / audio_duration) * 100.0
                                            )
                                            logger.debug(
                                                "Updating progress for %s: %.2f%% (end=%.2f)",
                                                task_id,
                                                pct,
                                                end,
                                            )
                                            update_task_progress(task_id, pct)
                                except (ValueError, TypeError, SQLAlchemyError):
                                    pass
                                segments.append(obj)
                            elif typ == "final":
                                raw_text = obj.get("raw_text", "")
                                if isinstance(obj.get("segments"), list):
                                    segments = obj.get("segments")
                                if task_id:
                                    update_task_progress(task_id, 100.0)
                                    logger.debug(
                                        "Marking progress 100%% for %s (final)", task_id
                                    )
                                logger.info(
                                    "inference: final received (len=%s)",
                                    len(raw_text) if raw_text is not None else 0,
                                )
                            elif typ == "error":
                                raise RuntimeError(obj.get("error"))
                        # if we completed without exception, break
                        break
                    except ChunkedEncodingError:
                        logger.exception(
                            "ChunkedEncodingError from inference (attempt %s)",
                            attempts,
                        )
                        try_stream = False
                    except RequestException:
                        logger.exception(
                            "RequestException from inference (attempt %s)", attempts
                        )
                        try_stream = False

                    # fallback: non-streaming request to get whole response body
                    if not try_stream and attempts < max_attempts:
                        try:
                            logger.info(
                                "Attempting non-streaming fallback request to inference (attempt %s)",
                                attempts + 1,
                            )
                            # need to re-open the file for the new request
                            with open(clean, "rb") as fh2:
                                files2 = {
                                    "file": (os.path.basename(clean), fh2, "audio/wav")
                                }
                                resp2 = requests.post(
                                    inference_url,
                                    files=files2,
                                    timeout=(5, 300),
                                    headers={"Connection": "keep-alive"},
                                )
                            logger.info(
                                "inference fallback response status=%s",
                                getattr(resp2, "status_code", None),
                            )
                            try:
                                body = resp2.text
                            except AttributeError:
                                body = None
                            for line in body.splitlines():
                                if not line:
                                    continue
                                try:
                                    obj = json.loads(line)
                                except json.JSONDecodeError:
                                    continue
                                typ = obj.get("type")
                                if typ == "heartbeat":
                                    continue
                                if typ == "segment":
                                    try:
                                        end = float(obj.get("end", 0.0) or 0.0)
                                        if task_id:
                                            update_task_status(
                                                task_id, f"transcribing:{end:.1f}s"
                                            )
                                            if audio_duration and audio_duration > 0:
                                                pct = min(
                                                    100.0,
                                                    (end / audio_duration) * 100.0,
                                                )
                                                logger.debug(
                                                    "Updating progress for %s: %.2f%% (end=%.2f)",
                                                    task_id,
                                                    pct,
                                                    end,
                                                )
                                                update_task_progress(task_id, pct)
                                    except (ValueError, TypeError, SQLAlchemyError):
                                        pass
                                    segments.append(obj)
                                elif typ == "final":
                                    raw_text = obj.get("raw_text", "")
                                    if isinstance(obj.get("segments"), list):
                                        segments = obj.get("segments")
                                    if task_id:
                                        update_task_progress(task_id, 100.0)
                                        logger.debug(
                                            "Marking progress 100%% for %s (final-fallback)",
                                            task_id,
                                        )
                                elif typ == "error":
                                    raise RuntimeError(obj.get("error"))
                            break
                        except (RequestException, OSError, json.JSONDecodeError):
                            logger.exception("Fallback inference request failed")
                            # sleep exponential backoff before retrying
                            try:
                                import time

                                time.sleep(backoff)
                                backoff = min(60, backoff * 2)
                            except (OSError, InterruptedError):
                                pass
                            continue
        else:
            # Use local transcribe with progress callback to update task status
            def _progress(seg):
                try:
                    end = float(getattr(seg, "end", 0.0) or 0.0)
                    if task_id:
                        update_task_status(task_id, f"transcribing:{end:.1f}s")
                        if audio_duration and audio_duration > 0:
                            pct = min(100.0, (end / audio_duration) * 100.0)
                            update_task_progress(task_id, pct)
                except (ValueError, TypeError, SQLAlchemyError):
                    pass

            raw_text, segments = transcribe(
                clean, model_size="small", prompt=None, progress_callback=_progress
            )
            if task_id:
                # ensure we mark progress complete when local transcribe finishes
                update_task_progress(task_id, 100.0)

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
        json.JSONDecodeError,
        ChunkedEncodingError,
    ) as e:
        # Record failure in shared store if possible
        if task_id:
            try:
                update_task_failure(task_id, str(e))
            except SQLAlchemyError:
                pass
        raise
