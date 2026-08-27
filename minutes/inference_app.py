from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.responses import StreamingResponse, JSONResponse
import os
import logging
import json
import threading
import queue
from minutes.transcribe import transcribe

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("minutes.inference")

app = FastAPI(title="Minutes Inference Service")


@app.post("/transcribe")
async def transcribe_endpoint(file: UploadFile = File(...)):
    uploads_dir = os.environ.get("UPLOADS_DIR", "uploads")
    os.makedirs(uploads_dir, exist_ok=True)
    dest_path = os.path.join(uploads_dir, file.filename)
    try:
        with open(dest_path, "wb") as out:
            content = await file.read()
            out.write(content)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))

    # Stream NDJSON: run transcribe in a background thread and emit one JSON
    # object per line for each segment as it is produced, then the final object.
    q = queue.Queue()
    segs = []

    def _progress(s):
        try:
            st = float(getattr(s, "start", 0.0) or 0.0)
            ed = float(getattr(s, "end", 0.0) or 0.0)
            txt = str(getattr(s, "text", ""))
            obj = {"type": "segment", "start": st, "end": ed, "text": txt}
            segs.append(obj)
            line = json.dumps(obj, ensure_ascii=False)
            logger.info("stream segment: %s", line[:200])
            q.put(line + "\n")
        except Exception:
            try:
                q.put(json.dumps({"type": "segment", "text": str(s)}, ensure_ascii=False) + "\n")
            except Exception:
                pass

    def worker():
        try:
            raw_text, _ = transcribe(dest_path, model_size="medium", prompt=None, progress_callback=_progress)
            final = {"type": "final", "raw_text": raw_text, "segments": segs}
            q.put(json.dumps(final, ensure_ascii=False) + "\n")
        except Exception as exc:
            q.put(json.dumps({"type": "error", "error": str(exc)}, ensure_ascii=False) + "\n")
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
