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
from minutes.ollama import format_minutes_from_raw
import datetime
import os
from minutes.bg_store import update_task_success, update_task_failure
from minutes.bg_store import update_task_status, update_task_progress
try:
    from minutes.bg_store import get_session
except Exception:
    get_session = None
import requests
from typing import Tuple, Any


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
    db = None
    if get_session:
        try:
            db = get_session()
        except Exception:
            db = None
    try:
        # mark preprocessing stage
        if task_id:
            update_task_status(task_id, "preprocess", db=db)
        mono, norm, clean = preprocess(input_path)

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
            update_task_status(task_id, "transcribing", db=db)

        if inference_url:
            # Call inference endpoint and stream NDJSON lines for progress.
            # If the chunked stream unexpectedly ends, retry once using a
            # non-streaming fallback to obtain the final output.
            logger = logging.getLogger("minutes.tasks")
            raw_text = ""
            segments = []
            files = {"file": (os.path.basename(clean), open(clean, "rb"), "audio/wav")}
            try_stream = True
            attempts = 0
            max_attempts = 3
            backoff = 1
            while attempts < max_attempts:
                attempts += 1
                try:
                    resp = requests.post(inference_url, files=files, stream=True, timeout=(5, 360), headers={"Connection": "keep-alive"})
                    resp.raise_for_status()
                    # parse NDJSON stream
                    for line in resp.iter_lines(decode_unicode=True, chunk_size=1024):
                        if not line:
                            continue
                        try:
                            obj = json.loads(line)
                        except Exception:
                            continue
                        typ = obj.get("type")
                        if typ == "heartbeat":
                            # ignore heartbeats
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
                                update_task_progress(task_id, 100.0, db=db)
                                logger.debug("Marking progress 100%% for %s (final)", task_id)
                        elif typ == "error":
                            raise RuntimeError(obj.get("error"))
                    # if we completed without exception, break
                    break
                except ChunkedEncodingError as e:
                    logger.warning("ChunkedEncodingError from inference (attempt %s): %s", attempts, e)
                    try_stream = False
                except RequestException as e:
                    logger.warning("RequestException from inference (attempt %s): %s", attempts, e)
                    try_stream = False

                # fallback: non-streaming request to get whole response body
                if not try_stream and attempts < max_attempts:
                    try:
                        logger.info("Attempting non-streaming fallback request to inference (attempt %s)", attempts + 1)
                        # need to re-open the file for the new request
                        with open(clean, "rb") as fh2:
                            files2 = {"file": (os.path.basename(clean), fh2, "audio/wav")}
                            resp2 = requests.post(inference_url, files=files2, timeout=(5, 300), headers={"Connection": "keep-alive"})
                        resp2.raise_for_status()
                        body = resp2.text
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
                                    update_task_progress(task_id, 100.0, db=db)
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
                        update_task_status(task_id, f"transcribing:{end:.1f}s", db=db)
                        if audio_duration and audio_duration > 0:
                            pct = min(100.0, (end / audio_duration) * 100.0)
                            update_task_progress(task_id, pct, db=db)
                except Exception:
                    pass

            raw_text, segments = transcribe(clean, model_size="small", prompt=None, progress_callback=_progress)
            if task_id:
                # ensure we mark progress complete when local transcribe finishes
                update_task_progress(task_id, 100.0, db=db)

        # mark formatting stage
        if task_id:
            update_task_status(task_id, "formatting", db=db)

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

        # Update shared task store for API visibility with structured result
        if task_id:
            update_task_success(task_id, structured, db=db)

        return {"status": "success", "result": structured}
    except Exception as e:
        # Record failure in shared store if possible
        if task_id:
            try:
                update_task_failure(task_id, str(e), db=db)
            except Exception:
                pass
        raise
    finally:
        try:
            if db is not None:
                db.close()
        except Exception:
            pass
