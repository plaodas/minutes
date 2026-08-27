import datetime
import os
import json
import contextlib
import wave
from minutes.celery_app import celery
from minutes.audio import preprocess
from minutes.transcribe import transcribe
from minutes.ollama import format_minutes_from_raw
import datetime
import os
from minutes.bg_store import update_task_success, update_task_failure
from minutes.bg_store import update_task_status, update_task_progress
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
    try:
        # mark preprocessing stage
        if task_id:
            update_task_status(task_id, "preprocess")
        mono, norm, clean = preprocess(input_path)

        # try to determine audio duration (seconds) from the cleaned wav file
        def _get_wav_duration(path: str):
            try:
                with contextlib.closing(wave.open(path, "rb")) as wf:
                    frames = wf.getnframes()
                    rate = wf.getframerate()
                    return frames / float(rate)
            except Exception:
                return None

        audio_duration = _get_wav_duration(clean)

        # If an external inference service is configured, call it via HTTP.
        inference_url = os.environ.get("INFERENCE_URL")
        # mark transcribing stage before calling inference/local transcribe
        if task_id:
            update_task_status(task_id, "transcribing")

        if inference_url:
            # Call inference endpoint and stream NDJSON lines for progress
            with open(clean, "rb") as fh:
                files = {"file": (os.path.basename(clean), fh, "audio/wav")}
                resp = requests.post(inference_url, files=files, stream=True, timeout=600)
            resp.raise_for_status()
            raw_text = ""
            segments = []
            # parse NDJSON stream
            for line in resp.iter_lines(decode_unicode=True):
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                except Exception:
                    continue
                typ = obj.get("type")
                if typ == "segment":
                    # update progress using end time as a heuristic
                    try:
                        end = float(obj.get("end", 0.0) or 0.0)
                        if task_id:
                            update_task_status(task_id, f"transcribing:{end:.1f}s")
                            if audio_duration and audio_duration > 0:
                                pct = min(100.0, (end / audio_duration) * 100.0)
                                update_task_progress(task_id, pct)
                    except Exception:
                        pass
                    segments.append(obj)
                elif typ == "final":
                    raw_text = obj.get("raw_text", "")
                    # if final contains segments, extend
                    if isinstance(obj.get("segments"), list):
                        segments = obj.get("segments")
                    # mark final progress as 100%
                    if task_id:
                        update_task_progress(task_id, 100.0)
                elif typ == "error":
                    raise RuntimeError(obj.get("error"))
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

            raw_text, segments = transcribe(clean, model_size="medium", prompt=None, progress_callback=_progress)
            if task_id:
                # ensure we mark progress complete when local transcribe finishes
                update_task_progress(task_id, 100.0)

        # mark formatting stage
        if task_id:
            update_task_status(task_id, "formatting")

        final_minutes = format_minutes_from_raw(raw_text)

        now = datetime.datetime.now().strftime("%Y%m%d%H%M%S")
        outputs_dir = os.environ.get("OUTPUTS_DIR", "outputs")
        os.makedirs(outputs_dir, exist_ok=True)
        out_file = os.path.join(outputs_dir, f"minutes_{now}.txt")
        with open(out_file, "w", encoding="utf-8") as f:
            f.write(final_minutes)

        # Update shared task store for API visibility
        if task_id:
            update_task_success(task_id, {"output_file": out_file})

        return {"status": "success", "output_file": out_file}
    except Exception as e:
        # Record failure in shared store if possible
        if task_id:
            try:
                update_task_failure(task_id, str(e))
            except Exception:
                pass
        raise
