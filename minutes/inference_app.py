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
        raw_text, segments = transcribe(dest_path, model_size="medium", prompt=None)
        logger.info("transcribe returned types: raw_text=%s, segments=%s", type(raw_text), type(segments))
        # Convert segments (may be generator/objects) to serializable form
        segs = []
        for s in segments:
            try:
                segs.append({"start": float(getattr(s, "start", None) or 0.0),
                             "end": float(getattr(s, "end", None) or 0.0),
                             "text": str(getattr(s, "text", ""))})
            except Exception:
                # fallback: string representation
                segs.append({"text": str(s)})
        return JSONResponse({"raw_text": raw_text, "segments": segs})
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))
