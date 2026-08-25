from fastapi import FastAPI, UploadFile, File, HTTPException, BackgroundTasks
from fastapi.responses import PlainTextResponse, JSONResponse
import tempfile
import shutil
import os
from minutes.audio import preprocess
from minutes.transcribe import transcribe
from minutes.ollama import format_minutes_from_raw
from minutes.tasks import process_audio
from minutes.celery_app import celery
from celery.result import AsyncResult
from minutes.bg_store import (
    create_task,
    update_task_success,
    update_task_failure,
    get_task,
)
import uuid


def _run_pipeline_background(input_path: str, task_id: str):
    try:
        mono, norm, clean = preprocess(input_path)
        raw_text, segments = transcribe(clean, model_size="medium", prompt=None)
        final_minutes = format_minutes_from_raw(raw_text)

        now = uuid.uuid4().hex
        outputs_dir = os.environ.get("OUTPUTS_DIR", "outputs")
        os.makedirs(outputs_dir, exist_ok=True)
        out_file = os.path.join(outputs_dir, f"minutes_{now}.txt")
        with open(out_file, "w", encoding="utf-8") as f:
            f.write(final_minutes)

        update_task_success(task_id, {"output_file": out_file})
    except Exception as exc:
        update_task_failure(task_id, str(exc))


app = FastAPI(title="Minutes Service (prototype)")


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/transcribe-upload", response_class=PlainTextResponse)
def transcribe_upload(file: UploadFile = File(...)):
    """Accept an audio file upload, run preprocess->transcribe->format, return minutes as plain text.

    This is a synchronous prototype endpoint intended for small/short audio files.
    """
    # Save uploaded file into uploads/ so workers can access it (shared volume)
    uploads_dir = os.environ.get("UPLOADS_DIR", "uploads")
    os.makedirs(uploads_dir, exist_ok=True)
    suffix = os.path.splitext(file.filename)[1] or ".wav"
    tmp_path = None
    try:
        dest_path = os.path.join(uploads_dir, file.filename)
        with open(dest_path, "wb") as out:
            shutil.copyfileobj(file.file, out)

        # Enqueue Celery task
        task = process_audio.delay(dest_path)
        return JSONResponse({"task_id": task.id})
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


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


@app.get("/status/{task_id}")
def task_status(task_id: str):
    res = AsyncResult(task_id, app=celery)
    return {"task_id": task_id, "status": res.status, "info": str(res.info)}


@app.get("/result/{task_id}")
def task_result(task_id: str):
    res = AsyncResult(task_id, app=celery)
    if not res.ready():
        return JSONResponse({"status": res.status}, status_code=202)
    if res.failed():
        return JSONResponse({"status": "failed", "info": str(res.info)}, status_code=500)
    return JSONResponse({"status": "success", "result": res.result})


@app.post("/transcribe-upload-bg", response_class=JSONResponse)
def transcribe_upload_bg(file: UploadFile = File(...), background_tasks: BackgroundTasks = None):
    """Minimal async endpoint using FastAPI BackgroundTasks (no Redis/Celery).

    Note: tasks are stored in a file `bg_tasks.json` under the app directory.
    This is best-effort persistence; process restart will not resume running tasks.
    """
    uploads_dir = os.environ.get("UPLOADS_DIR", "uploads")
    os.makedirs(uploads_dir, exist_ok=True)
    dest_path = os.path.join(uploads_dir, file.filename)
    try:
        with open(dest_path, "wb") as out:
            shutil.copyfileobj(file.file, out)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))

    task_id = uuid.uuid4().hex
    create_task(task_id)
    # schedule background work
    background_tasks.add_task(_run_pipeline_background, dest_path, task_id)
    return JSONResponse({"task_id": task_id})


@app.get("/bg/status/{task_id}")
def bg_status(task_id: str):
    t = get_task(task_id)
    if not t:
        return JSONResponse({"error": "unknown task"}, status_code=404)
    return JSONResponse({"task_id": task_id, "status": t["status"], "error": t.get("error")})


@app.get("/bg/result/{task_id}")
def bg_result(task_id: str):
    t = get_task(task_id)
    if not t:
        return JSONResponse({"error": "unknown task"}, status_code=404)
    if t["status"] != "success":
        return JSONResponse({"status": t["status"], "error": t.get("error")}, status_code=202)
    return JSONResponse({"status": "success", "result": t.get("result")})
