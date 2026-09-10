import json
import logging
import os
import queue
import threading

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import StreamingResponse
from starlette.concurrency import run_in_threadpool

from minutes.transcribe import transcribe

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("minutes.inference")

app = FastAPI(title="Minutes Inference Service")

# module-level default for FastAPI `File()` to satisfy linter
_UPLOAD_FILE = File(...)


@app.post("/transcribe")
async def transcribe_endpoint(file: UploadFile = _UPLOAD_FILE):
    uploads_dir = os.environ.get("UPLOADS_DIR", "uploads")
    os.makedirs(uploads_dir, exist_ok=True)
    dest_path = os.path.join(uploads_dir, file.filename)
    try:
        content = await file.read()

        def _write_bytes(path: str, data: bytes) -> None:
            with open(path, "wb") as outp:
                outp.write(data)

        await run_in_threadpool(_write_bytes, dest_path, content)
    except (OSError, RuntimeError) as exc:
        raise HTTPException(status_code=500, detail=str(exc))

    # Stream NDJSON: run transcribe in a background thread and emit one JSON
    # object per line for each segment as it is produced, then the final object.
    q = queue.Queue()
    segs = []
    total_duration = None

    def _get_duration(path: str):
        """Try to get audio duration via ffprobe (falls back to None)."""
        try:
            import subprocess

            cmd = [
                "ffprobe",
                "-v",
                "error",
                "-show_entries",
                "format=duration",
                "-of",
                "default=nw=1:nk=1",
                path,
            ]
            out = subprocess.check_output(cmd, stderr=subprocess.STDOUT)
            return float(out.strip())
        except (subprocess.CalledProcessError, FileNotFoundError, ValueError, OSError):
            return None

    def _progress(s):
        try:
            st = float(getattr(s, "start", 0.0) or 0.0)
            ed = float(getattr(s, "end", 0.0) or 0.0)
            txt = str(getattr(s, "text", ""))
            nonlocal total_duration
            if total_duration is None:
                # attempt to probe duration once
                total_duration = _get_duration(dest_path)

            percent = None
            try:
                if total_duration and total_duration > 0:
                    percent = min(100, int(100 * (ed / total_duration)))
            except (TypeError, ValueError):
                percent = None

            obj = {
                "type": "segment",
                "start": st,
                "end": ed,
                "text": txt,
                "percent": percent,
            }
            segs.append(obj)
            line = json.dumps(obj, ensure_ascii=False)
            logger.info("stream segment: %s", line[:200])
            q.put(line + "\n")
        except (TypeError, ValueError, AttributeError, OSError):
            try:
                fallback = (
                    json.dumps({"type": "segment", "text": str(s)}, ensure_ascii=False)
                    + "\n"
                )
                q.put(fallback)
            except (TypeError, ValueError, OSError):
                logger.exception("failed to queue fallback segment for %s", dest_path)

    def worker():
        try:
            raw_text, _ = transcribe(
                dest_path, model_size="small", prompt=None, progress_callback=_progress
            )
            final = {"type": "final", "raw_text": raw_text, "segments": segs}
            q.put(json.dumps(final, ensure_ascii=False) + "\n")
        except (RuntimeError, OSError, ValueError, TypeError) as exc:
            # Log full exception with traceback for debugging on the inference side
            logger.exception("transcribe worker failed for %s", dest_path)
            try:
                q.put(
                    json.dumps({"type": "error", "error": str(exc)}, ensure_ascii=False)
                    + "\n"
                )
            except (TypeError, ValueError, OSError):
                logger.exception("failed to queue error for %s", dest_path)
        finally:
            q.put(None)

    threading.Thread(target=worker, daemon=True).start()

    def event_stream():
        import time

        heartbeat_interval = 2.0
        while True:
            try:
                item = q.get(timeout=heartbeat_interval)
            except queue.Empty:
                hb = json.dumps({"type": "heartbeat", "ts": time.time()}) + "\n"
                yield hb
                continue
            if item is None:
                break
            yield item

    return StreamingResponse(event_stream(), media_type="application/x-ndjson")
