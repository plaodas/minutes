from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.responses import StreamingResponse, JSONResponse
import os
import logging
import json
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

    # Stream NDJSON: emit one JSON object per line for segments, then a final object
    def event_stream():
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
                yield line + "\n"
            except Exception:
                try:
                    line = json.dumps({"type": "segment", "text": str(s)})
                    yield line + "\n"
                except Exception:
                    pass

        try:
            raw_text, _ = transcribe(dest_path, model_size="medium", prompt=None, progress_callback=_progress)
            # final object
            final = {"type": "final", "raw_text": raw_text, "segments": segs}
            yield json.dumps(final, ensure_ascii=False) + "\n"
        except Exception as exc:
            err = {"type": "error", "error": str(exc)}
            yield json.dumps(err, ensure_ascii=False) + "\n"

    return StreamingResponse(event_stream(), media_type="application/x-ndjson")
