from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.responses import PlainTextResponse, JSONResponse
import tempfile
import shutil
import os
from minutes.audio import preprocess
from minutes.transcribe import transcribe
from minutes.ollama import format_minutes_from_raw


app = FastAPI(title="Minutes Service (prototype)")


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/transcribe-upload", response_class=PlainTextResponse)
def transcribe_upload(file: UploadFile = File(...)):
    """Accept an audio file upload, run preprocess->transcribe->format, return minutes as plain text.

    This is a synchronous prototype endpoint intended for small/short audio files.
    """
    suffix = os.path.splitext(file.filename)[1] or ".wav"
    tmp_path = None
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
            tmp_path = tmp.name
            shutil.copyfileobj(file.file, tmp)

        mono, norm, clean = preprocess(tmp_path)
        raw_text, segments = transcribe(clean, model_size="medium", prompt=None)
        minutes = format_minutes_from_raw(raw_text)

        return PlainTextResponse(content=minutes)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))
    finally:
        try:
            if tmp_path and os.path.exists(tmp_path):
                os.remove(tmp_path)
        except Exception:
            pass


@app.post("/format-raw", response_class=PlainTextResponse)
def format_raw(payload: dict):
    """Accept JSON {"raw": "..."} and return formatted minutes."""
    raw = payload.get("raw")
    if not raw:
        return JSONResponse({"error": "missing 'raw' field"}, status_code=400)

    try:
        minutes = format_minutes_from_raw(raw)
        return PlainTextResponse(content=minutes)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))
