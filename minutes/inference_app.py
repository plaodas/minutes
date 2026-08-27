from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.responses import JSONResponse
import os
import logging
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

    try:
        # Use the project's transcribe wrapper (this will import faster_whisper)
        segs = []

        def _progress(s):
            try:
                st = float(getattr(s, "start", 0.0) or 0.0)
                ed = float(getattr(s, "end", 0.0) or 0.0)
                txt = str(getattr(s, "text", ""))
                logger.info("segment produced: start=%.3f end=%.3f text=%s", st, ed, txt[:80])
            except Exception:
                logger.info("segment produced (unserializable): %s", str(s))

        raw_text, segments = transcribe(dest_path, model_size="medium", prompt=None, progress_callback=_progress)
        logger.info("transcribe returned types: raw_text=%s, segments=%s", type(raw_text), type(segments))
        # Convert segments (materialized list) to serializable form
        for s in segments:
            try:
                segs.append({"start": float(getattr(s, "start", None) or 0.0),
                             "end": float(getattr(s, "end", None) or 0.0),
                             "text": str(getattr(s, "text", ""))})
            except Exception:
                segs.append({"text": str(s)})
        return JSONResponse({"raw_text": raw_text, "segments": segs})
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))
