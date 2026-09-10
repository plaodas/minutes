import datetime
import os
import json
import contextlib
import wave
import logging
from requests.exceptions import ChunkedEncodingError, RequestException
from minutes.celery_app import celery
from minutes.audio import preprocess
from minutes.transcribe import transcribe
from minutes.ollama import format_minutes_from_raw, DEFAULT_SYSTEM_PROMPT
import datetime
import os
from minutes.bg_store import get_task, update_task_success, update_task_failure, update_task_status, update_task_progress
import requests
from typing import Tuple, Any


def build_system_prompt(meta_obj):
    """Construct a system prompt from metadata dict (language/include_actions)."""
    if not isinstance(meta_obj, dict):
        return None
    sp = DEFAULT_SYSTEM_PROMPT
    lang = meta_obj.get('language')
    if lang and isinstance(lang, str) and lang.lower() not in ('auto', 'auto-detect', 'auto detect'):
        if 'jap' in lang.lower():
            sp = '出力は日本語で行ってください。\n' + sp
        else:
            sp = 'Please produce the output in English.\n' + sp
    inc = meta_obj.get('include_actions')
    if inc is False:
        sp = sp + '\n' + 'Do not extract action items. Skip STEP3.'
    return sp


@celery.task(bind=True)
def hard_delete_task(self, task_id: str, requester: str | None = None):
    """Admin Celery job: delete MinIO objects for a task and remove DB rows.

    This task is retryable by Celery if MinIO deletion fails.
    """
    logger = logging.getLogger('minutes.tasks')
    from minutes.db import session_scope
    from minutes.minio_client import MinioService
    from minutes.models import Task, TaskHistory, Bucket
    from datetime import datetime
    with session_scope() as db:
        # normalize key
        try:
            from minutes.bg_store import _parse_key
            key = _parse_key(task_id)
        except Exception:
            key = task_id

        t = db.get(Task, key)
        if not t:
            logger.info('hard_delete_task: unknown task %s', task_id)
            return {'deleted': False, 'reason': 'unknown task'}

        res = t.result or {}
        # attempt MinIO deletion if present
        try:
            if isinstance(res, dict):
                minio_info = res.get('minio') if isinstance(res.get('minio'), dict) else None
                svc = None
                if minio_info and minio_info.get('bucket'):
                    svc = MinioService()
                    bucket = minio_info.get('bucket')
                    # if an object key is provided, delete it; otherwise delete prefix for task
                    if minio_info.get('object'):
                        logger.info('hard_delete_task removing object %s/%s', bucket, minio_info.get('object'))
                        svc.delete_object(bucket, minio_info.get('object'), ignore_missing=True)
                    else:
                        prefix = f'minutes/{task_id}/'
                        logger.info('hard_delete_task removing objects under %s prefix in bucket %s', prefix, bucket)
                        svc.delete_objects_with_prefix(bucket, prefix, ignore_missing=True)
        except Exception as exc:
            logger.exception('hard_delete_task: MinIO deletion failed for %s: %s', task_id, exc)
            # raise to allow Celery to retry; session_scope will rollback
            raise

        # remove output file if present locally
        try:
            output_file = res.get('output_file') or (res.get('result') or {}).get('output_file')
            if output_file:
                outputs_dir = os.environ.get('OUTPUTS_DIR', 'outputs')
                candidate = os.path.join(outputs_dir, os.path.basename(output_file))
                if os.path.exists(candidate):
                    os.remove(candidate)
        except Exception:
            logger.exception('hard_delete_task: failed to remove local output for %s', task_id)

        # delete TaskHistory and Task rows
        try:
            db.query(TaskHistory).filter(TaskHistory.task_id == key).delete()
            # attempt to delete Task row
            db.delete(t)
        except Exception:
            logger.exception('hard_delete_task: failed DB delete for %s', task_id)
            raise

        # attempt to delete Bucket row if no other task references it
        try:
            if isinstance(res, dict) and res.get('minio') and res['minio'].get('bucket'):
                bucket_name = res['minio'].get('bucket')
                # check other tasks referencing this bucket
                other = db.query(Task).filter(Task.result['minio']['bucket'].astext == bucket_name).count()
                if other == 0:
                    b = db.query(Bucket).filter(Bucket.name == bucket_name).one_or_none()
                    if b:
                        db.delete(b)
        except Exception:
            # non-fatal
            logger.exception('hard_delete_task: failed to cleanup bucket row for %s', task_id)

        # record audit history row
        try:
            from minutes.bg_store import record_history

            record_history(task_id, 'deleted_hard', {'requester': requester or None, 'deleted_at': datetime.utcnow().isoformat()})
        except Exception:
            logger.exception('hard_delete_task: failed to record deletion history for %s', task_id)
    # session_scope will commit/close automatically
    logger.info('hard_delete_task completed for %s', task_id)
    return {'deleted': True}


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
    # with worker processing. Keep robust to avoid raising during logging.
    try:
        logger = logging.getLogger("minutes.tasks")
        logger.info("process_audio start: task_id=%r input=%s", task_id, input_path)
        # also print to stdout for immediate worker logs visibility
        print(f"DEBUG process_audio start task_id={repr(task_id)} input={input_path}")
    except Exception:
        pass
    # Do NOT hold a long-lived DB session during preprocessing/transcription.
    # `update_task_*` helper functions manage their own short-lived sessions.
    try:
        # mark preprocessing stage
        logger = logging.getLogger("minutes.tasks")
        if task_id:
            try:
                logger.debug("process_audio: setting task status 'preprocess' for %s", task_id)
            except Exception:
                pass
            update_task_status(task_id, "preprocess")
            try:
                logger.debug("process_audio: update_task_status returned for %s", task_id)
            except Exception:
                pass

        # Log input file presence and size before calling preprocess
        try:
            inp_exists = os.path.exists(input_path)
            inp_size = os.path.getsize(input_path) if inp_exists else None
        except Exception:
            inp_exists = False
            inp_size = None
        try:
            logger.info("process_audio: preprocess start input=%s exists=%s size=%s cwd=%s", input_path, inp_exists, inp_size, os.getcwd())
        except Exception:
            pass

        # Call preprocess with timing and robust exception logging
        import time as _time
        _start = _time.time()
        try:
            mono, norm, clean = preprocess(input_path)
        except Exception as e:
            try:
                logger.exception("process_audio: preprocess failed for %s: %s", input_path, e)
            except Exception:
                pass
            # Record failure in task store if possible, then re-raise
            if task_id:
                try:
                    update_task_failure(task_id, f"preprocess failed: {e}")
                except Exception:
                    try:
                        logger.exception("process_audio: failed to record preprocess failure for %s", task_id)
                    except Exception:
                        pass
            raise
        _dur = _time.time() - _start
        try:
            logger.info("process_audio: preprocess completed in %.2fs -> mono=%s norm=%s clean=%s", _dur, mono, norm, clean)
        except Exception:
            pass
        # log sizes of produced files
        for p in (mono, norm, clean):
            try:
                s = os.path.getsize(p) if (p and os.path.exists(p)) else None
                logger.debug("process_audio: preprocess output %s exists=%s size=%s", p, (p and os.path.exists(p)), s)
            except Exception:
                try:
                    logger.debug("process_audio: preprocess output %s check failed", p)
                except Exception:
                    pass

        # Validate cleaned WAV exists and appears valid before continuing.
        try:
            if not clean or not os.path.exists(clean) or os.path.getsize(clean) == 0:
                raise RuntimeError(f"Invalid data found when processing input: '{clean}'")
            # ensure it's a readable WAV and inspect sample rate
            import wave as _wave
            with contextlib.closing(_wave.open(clean, "rb")) as wf:
                rate = wf.getframerate()
                channels = wf.getnchannels()
        except Exception as e:
            # raise with the familiar message shape so existing handlers record it
            raise RuntimeError(f"Invalid data found when processing input: '{clean}'") from e
        # Warn if sample rate differs from expected (we force 16k in preprocess)
        try:
            logger = logging.getLogger("minutes.tasks")
            if rate and rate != 16000:
                logger.warning("Unexpected sample rate %s Hz for %s", rate, clean)
        except Exception:
            pass

        # try to determine audio duration (seconds) from the cleaned wav file
        def _get_wav_duration(path: str):
            try:
                with contextlib.closing(wave.open(path, "rb")) as wf:
                    frames = wf.getnframes()
                    rate = wf.getframerate()
                    return frames / float(rate)
            except Exception as e:
                logger = logging.getLogger("minutes.tasks")
                logger.debug("wave.open failed for %s: %s", path, e)
                # fallback: try ffprobe
                try:
                    import subprocess
                    out = subprocess.check_output([
                        "ffprobe", "-v", "error", "-show_entries", "format=duration",
                        "-of", "default=noprint_wrappers=1:nokey=1", path
                    ], stderr=subprocess.DEVNULL)
                    try:
                        return float(out.strip())
                    except Exception:
                        return None
                except Exception as e2:
                    logger.debug("ffprobe fallback failed for %s: %s", path, e2)
                    return None

        audio_duration = _get_wav_duration(clean)
        logger = logging.getLogger("minutes.tasks")
        logger.info("Determined audio_duration=%s for %s", audio_duration, clean)

        # If an external inference service is configured, call it via HTTP.
        inference_url = os.environ.get("INFERENCE_URL")
        # mark transcribing stage before calling inference/local transcribe
        if task_id:
            update_task_status(task_id, "transcribing")

        if inference_url:
            # Call inference endpoint and stream NDJSON lines for progress.
            # If the chunked stream unexpectedly ends, retry once using a
            # non-streaming fallback to obtain the final output.
            logger = logging.getLogger("minutes.tasks")
            raw_text = ""
            segments = []
            files = {"file": (os.path.basename(clean), open(clean, "rb"), "audio/wav")}
            try:
                size = os.path.getsize(clean) if os.path.exists(clean) else None
            except Exception:
                size = None
            logger.info("inference: calling %s file=%s size=%s", inference_url, os.path.basename(clean), size)
            try_stream = True
            attempts = 0
            max_attempts = 3
            backoff = 1
            while attempts < max_attempts:
                attempts += 1
                try:
                    resp = requests.post(inference_url, files=files, stream=True, timeout=(5, 360), headers={"Connection": "keep-alive"})
                    logger.info("inference: http POST sent (attempt=%s) -> status=%s", attempts, getattr(resp, 'status_code', None))
                    try:
                        logger.debug("inference response headers: %s", dict(resp.headers))
                    except Exception:
                        pass
                    resp.raise_for_status()
                    # parse NDJSON stream
                    for line in resp.iter_lines(decode_unicode=True, chunk_size=1024):
                        if not line:
                            continue
                        logger.debug("inference: ndjson raw line: %s", (line[:200] if isinstance(line, str) else str(line)[:200]))
                        try:
                            obj = json.loads(line)
                        except Exception:
                            logger.debug("inference: failed to parse ndjson line: %r", (line[:200] if isinstance(line, str) else str(line)[:200]))
                            continue
                        typ = obj.get("type")
                        if typ == "heartbeat":
                            # ignore heartbeats
                            continue
                        if typ == "segment":
                            try:
                                end = float(obj.get("end", 0.0) or 0.0)
                                if task_id:
                                    update_task_status(task_id, f"transcribing:{end:.1f}s")
                                    if audio_duration and audio_duration > 0:
                                        pct = min(100.0, (end / audio_duration) * 100.0)
                                        logger.debug("Updating progress for %s: %.2f%% (end=%.2f)", task_id, pct, end)
                                        update_task_progress(task_id, pct)
                            except Exception:
                                pass
                            segments.append(obj)
                        elif typ == "final":
                            raw_text = obj.get("raw_text", "")
                            if isinstance(obj.get("segments"), list):
                                segments = obj.get("segments")
                            if task_id:
                                update_task_progress(task_id, 100.0)
                                logger.debug("Marking progress 100%% for %s (final)", task_id)
                            try:
                                logger.info("inference: final received (len=%s)", len(raw_text) if raw_text is not None else 0)
                            except Exception:
                                pass
                        elif typ == "error":
                            raise RuntimeError(obj.get("error"))
                    # if we completed without exception, break
                    break
                except ChunkedEncodingError as e:
                    logger.exception("ChunkedEncodingError from inference (attempt %s): %s", attempts, e)
                    try_stream = False
                except RequestException as e:
                    logger.exception("RequestException from inference (attempt %s): %s", attempts, e)
                    try_stream = False

                # fallback: non-streaming request to get whole response body
                if not try_stream and attempts < max_attempts:
                    try:
                        logger.info("Attempting non-streaming fallback request to inference (attempt %s)", attempts + 1)
                        # need to re-open the file for the new request
                        with open(clean, "rb") as fh2:
                            files2 = {"file": (os.path.basename(clean), fh2, "audio/wav")}
                            resp2 = requests.post(inference_url, files=files2, timeout=(5, 300), headers={"Connection": "keep-alive"})
                        logger.info("inference fallback response status=%s", getattr(resp2, 'status_code', None))
                        try:
                            body = resp2.text
                        except Exception:
                            body = None
                        for line in body.splitlines():
                            if not line:
                                continue
                            try:
                                obj = json.loads(line)
                            except Exception:
                                continue
                            typ = obj.get("type")
                            if typ == "heartbeat":
                                continue
                            if typ == "segment":
                                try:
                                    end = float(obj.get("end", 0.0) or 0.0)
                                    if task_id:
                                        update_task_status(task_id, f"transcribing:{end:.1f}s", db=db)
                                        if audio_duration and audio_duration > 0:
                                            pct = min(100.0, (end / audio_duration) * 100.0)
                                            logger.debug("Updating progress for %s: %.2f%% (end=%.2f)", task_id, pct, end)
                                            update_task_progress(task_id, pct, db=db)
                                except Exception:
                                    pass
                                segments.append(obj)
                            elif typ == "final":
                                raw_text = obj.get("raw_text", "")
                                if isinstance(obj.get("segments"), list):
                                    segments = obj.get("segments")
                                if task_id:
                                    update_task_progress(task_id, 100.0)
                                    logger.debug("Marking progress 100%% for %s (final-fallback)", task_id)
                            elif typ == "error":
                                raise RuntimeError(obj.get("error"))
                        break
                    except Exception as e:
                        logger.exception("Fallback inference request failed: %s", e)
                        # sleep exponential backoff before retrying
                        try:
                            import time
                            time.sleep(backoff)
                            backoff = min(60, backoff * 2)
                        except Exception:
                            pass
                        continue
            # close the original file object in files
            try:
                files["file"][1].close()
            except Exception:
                pass
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
                except Exception:
                    pass

            raw_text, segments = transcribe(clean, model_size="small", prompt=None, progress_callback=_progress)
            if task_id:
                # ensure we mark progress complete when local transcribe finishes
                update_task_progress(task_id, 100.0)

        # mark formatting stage
        if task_id:
            update_task_status(task_id, "formatting")
            # proactively publish an SSE event so frontends update immediately
            try:
                from minutes.sse import publish_event

                publish_event({
                    "type": "task.event",
                    "task_id": str(task_id),
                    "event_type": "status",
                    "payload": {"status": "formatting"},
                })
            except Exception:
                pass

        # Attempt to read task metadata to customize the formatting prompt
        meta = None
        try:
            if task_id:
                trec = get_task(task_id)
                if trec:
                    meta = trec.get('result') or {}
        except Exception:
            meta = None


        system_prompt = build_system_prompt(meta)

        if system_prompt:
            final_minutes = format_minutes_from_raw(raw_text, system_prompt=system_prompt)
        else:
            final_minutes = format_minutes_from_raw(raw_text)

        now = datetime.datetime.now().strftime("%Y%m%d%H%M%S")
        outputs_dir = os.environ.get("OUTPUTS_DIR", "outputs")
        os.makedirs(outputs_dir, exist_ok=True)
        out_file = os.path.join(outputs_dir, f"minutes_{now}.txt")
        with open(out_file, "w", encoding="utf-8") as f:
            f.write(final_minutes)

        # Build structured result: transcript, segments, formatted minutes, summary, action items
        try:
            from minutes.summary import summarize_local
        except Exception:
            def summarize_local(x, max_sentences=3):
                return ""

        # summary: prefer summarizing formatted minutes for readability
        try:
            summary_text = summarize_local(final_minutes, max_sentences=3)
        except Exception:
            summary_text = ""

        # action items: simple heuristic parse from formatted minutes
        try:
            import re

            items = []
            m = re.search(r"(?ims)^\s*action items\s*$\n(.*?)(?:\n\s*$|$)", final_minutes)
            section = None
            if m:
                section = m.group(1)
            if section:
                for line in section.splitlines():
                    s = line.strip().lstrip("-•* ")
                    if not s:
                        continue
                    items.append({"text": s})
            else:
                # fallback: search for TODO/Action: patterns
                for line in final_minutes.splitlines():
                    if re.search(r"\b(Action|TODO|Action Item)[:\-]", line, re.I):
                        items.append({"text": line.strip()})
        except Exception:
            items = []

        structured = {
            "transcript": raw_text,
            "segments": segments,
            "minutes": final_minutes,
            "summary": summary_text,
            "action_items": items,
            "output_file": out_file,
        }

        # If configured, upload the final minutes to MinIO as a cached copy
        try:
            bucket = os.environ.get("MINIO_DEFAULT_BUCKET") or os.environ.get("MINIO_BUCKET")
            if bucket:
                try:
                    from minutes.minio_client import MinioService
                    svc = MinioService()
                    logging.getLogger('minutes.tasks').info('Attempting MinIO upload for task %s to bucket %s', task_id, bucket)
                    try:
                        svc.ensure_bucket(bucket)
                    except Exception:
                        # best-effort
                        pass
                    object_name = f"minutes/{task_id}/minutes_{now}.txt"
                    try:
                        svc.client.fput_object(bucket, object_name, out_file)
                        logging.getLogger('minutes.tasks').info('MinIO fput_object succeeded for task %s object %s', task_id, object_name)
                        try:
                            expires_sec = int(os.environ.get('MINIO_PRESIGNED_EXPIRES', '3600'))
                            url = svc.presigned_get(bucket, object_name, expires=expires_sec)
                            # use module-level datetime to avoid UnboundLocalError when
                            # a local import shadows the name
                            from datetime import timedelta
                            expires_at = (datetime.datetime.utcnow() + timedelta(seconds=expires_sec)).isoformat() + 'Z'
                        except Exception:
                            url = None
                            expires_sec = None
                            expires_at = None
                        structured['minio'] = {"bucket": bucket, "object": object_name, "url": url, "expires": expires_sec, "expires_at": expires_at}
                    except Exception:
                        logging.getLogger('minutes.tasks').exception('MinIO upload failed for task %s', task_id)
                except Exception:
                    logging.getLogger('minutes.tasks').exception('Failed initializing MinIO client for task %s', task_id)
        except Exception:
            # swallow any MinIO-related errors; shouldn't fail the task
            pass

        # Update shared task store for API visibility with structured result
        if task_id:
            update_task_success(task_id, structured)

        # Optionally remove intermediate files produced by preprocessing
        try:
            DELETE_INTERMEDIATE = os.environ.get("DELETE_INTERMEDIATE", "true").lower() in ("1", "true", "yes")
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
                            logger = logging.getLogger('minutes.tasks')
                            logger.warning('Skipping removal of intermediate outside base dir: %s', p_abs)
                            continue
                        if os.path.exists(p_abs):
                            os.remove(p_abs)
                            logger = logging.getLogger('minutes.tasks')
                            logger.info('Removed intermediate file %s for task %s', p_abs, task_id)
                    except Exception:
                        logger = logging.getLogger('minutes.tasks')
                        logger.exception('Failed to remove intermediate %s for task %s', p, task_id)
        except Exception:
            logging.getLogger('minutes.tasks').exception('Error while cleaning intermediates')

        return {"status": "success", "result": structured}
    except Exception as e:
        # Record failure in shared store if possible
        if task_id:
            try:
                update_task_failure(task_id, str(e))
            except Exception:
                pass
        raise

