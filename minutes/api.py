from fastapi import FastAPI, UploadFile, File, HTTPException, BackgroundTasks
import asyncio
import logging
import logging
from fastapi.responses import PlainTextResponse, JSONResponse
from typing import Dict, Any, List
from pydantic import BaseModel
import json
from minutes.schemas import (
    CreateTaskResponse,
    FormatRawRequest,
    FormatRawResponse,
    StatusResponse,
    ResultSuccess,
)
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
    update_task_status,
)
from minutes.bg_store import update_task_cancelled
from minutes.bg_store import DB_PATH
import uuid
from minutes.db import SessionLocal
from minutes.models import TaskHistory
import uuid
from minutes.reconcile_bg_tasks import reconcile_once

# Configuration: request limits for /bg/histories
MAX_IDS_PER_REQUEST = int(os.environ.get("MAX_BG_HISTORIES_IDS", "500"))
# Hard cap to absolutely reject too-large requests
HARD_IDS_LIMIT = int(os.environ.get("MAX_BG_HISTORIES_HARD_LIMIT", "5000"))
# Internal batch size used to split large id lists into smaller DB IN(...) queries
BG_HISTORIES_BATCH_SIZE = int(os.environ.get("BG_HISTORIES_BATCH_SIZE", "200"))


def _run_pipeline_background(input_path: str, task_id: str):
    try:
        # update intermediate status: preprocessing
        update_task_status(task_id, "preprocess")
        mono, norm, clean = preprocess(input_path)

        # update intermediate status: transcribing
        update_task_status(task_id, "transcribing")
        raw_text, segments = transcribe(clean, model_size="medium", prompt=None)

        # update intermediate status: formatting
        update_task_status(task_id, "formatting")
        final_minutes = format_minutes_from_raw(raw_text)

        # detect Ollama fallback (service-wide behavior: fallback responses are
        # prefixed with "[FALLBACK] ") and log it for observability.
        logger = logging.getLogger("minutes.api")
        if isinstance(final_minutes, str) and final_minutes.startswith("[FALLBACK]"):
            logger.warning("Task %s used Ollama fallback: %s", task_id, final_minutes.splitlines()[0])

        now = uuid.uuid4().hex
        outputs_dir = os.environ.get("OUTPUTS_DIR", "outputs")
        os.makedirs(outputs_dir, exist_ok=True)
        tmp_file = os.path.join(outputs_dir, f"minutes_{now}.txt.tmp")
        out_file = os.path.join(outputs_dir, f"minutes_{now}.txt")

        # write atomically and flush to disk before marking task success
        with open(tmp_file, "w", encoding="utf-8") as f:
            f.write(final_minutes)
            f.flush()
            try:
                os.fsync(f.fileno())
            except Exception:
                # fsync may not be available in all environments; continue
                pass

        # atomic replace
        os.replace(tmp_file, out_file)

        # verify output exists and is non-empty before updating task store
        if not os.path.exists(out_file) or os.path.getsize(out_file) == 0:
            raise RuntimeError(f"Output file write failed or empty: {out_file}")

        update_task_success(task_id, {"output_file": out_file})
    except Exception as exc:
        update_task_failure(task_id, str(exc))


app = FastAPI(title="Minutes Service (prototype)")


@app.on_event("startup")
async def startup_reconciler():
    """Run a single reconciliation at startup, then schedule periodic runs.

    Interval is controlled by `RECONCILE_INTERVAL_SECONDS` (default 3600).
    """
    logger = logging.getLogger("minutes.api")
    try:
        # run once immediately in a thread to avoid blocking the event loop
        await asyncio.to_thread(reconcile_once)
        logger.info("Initial bg task reconciliation completed")
    except Exception as exc:
        logger.exception("Initial reconciliation failed: %s", exc)

    interval = int(os.environ.get("RECONCILE_INTERVAL_SECONDS", "3600"))

    async def reconcile_loop():
        while True:
            try:
                await asyncio.sleep(interval)
                await asyncio.to_thread(reconcile_once)
                logger.info("Periodic bg task reconciliation completed")
            except asyncio.CancelledError:
                logger.info("Reconcile loop cancelled")
                break
            except Exception:
                logger.exception("Reconcile loop error")

    # store the task so it can be cancelled on shutdown
    app.state.reconcile_task = asyncio.create_task(reconcile_loop())


@app.on_event("shutdown")
async def shutdown_reconciler():
    task = getattr(app.state, "reconcile_task", None)
    if task and not task.done():
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/transcribe-upload", response_model=CreateTaskResponse)
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
        return {"task_id": task.id}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.post("/format-raw", response_model=FormatRawResponse)
def format_raw(payload: FormatRawRequest):
    """Accept JSON {"raw": "..."} and return formatted minutes as JSON."""
    raw = payload.raw
    if not raw:
        return JSONResponse({"error": "missing 'raw' field"}, status_code=400)

    try:
        minutes = format_minutes_from_raw(raw)
        return {"minutes": minutes}
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


@app.post("/transcribe-upload-bg", response_model=CreateTaskResponse)
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

    # Enqueue as a Celery task so we can support revoke/terminate later.
    try:
        task = process_audio.delay(dest_path)
        task_id = task.id
        create_task(task_id)
        return {"task_id": task_id}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.get("/bg/status/{task_id}", response_model=StatusResponse)
def bg_status(task_id: str):
    t = get_task(task_id)
    if not t:
        return JSONResponse({"error": "unknown task"}, status_code=404)
    return {"task_id": task_id, "status": t["status"], "error": t.get("error"), "progress": t.get("progress")}


@app.get(
    "/bg/result/{task_id}",
    responses={
        200: {"description": "success", "content": {"application/json": {}}},
        202: {"description": "pending or failed"},
        404: {"description": "unknown task"},
    },
)
def bg_result(task_id: str):
    t = get_task(task_id)
    if not t:
        return JSONResponse({"error": "unknown task"}, status_code=404)
    if t["status"] != "success":
        return JSONResponse({"status": t["status"], "error": t.get("error")}, status_code=202)
    return {"status": "success", "result": t.get("result")}


@app.get("/bg/history/{task_id}")
def bg_history(task_id: str, limit: int = 100, offset: int = 0):
    """Return task history events. Works with DB-backed store or file-backed fallback."""
    # DB-backed
    if os.environ.get("DATABASE_URL"):
        session = SessionLocal()
        try:
            try:
                key = uuid.UUID(task_id)
            except Exception:
                return JSONResponse({"error": "invalid task id"}, status_code=400)
            rows = (
                session.query(TaskHistory)
                .filter(TaskHistory.task_id == key)
                .order_by(TaskHistory.event_ts.desc())
                .offset(int(offset))
                .limit(int(limit))
                .all()
            )
            out = []
            for r in rows:
                out.append({
                    "event_ts": r.event_ts.isoformat() + "Z" if r.event_ts else None,
                    "event_type": r.event_type,
                    "payload": r.payload,
                })
            return {"task_id": task_id, "history": out}
        finally:
            session.close()

    # File-backed fallback
    try:
        with open(DB_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        return JSONResponse({"error": "unknown task"}, status_code=404)

    t = data.get(task_id)
    if not t:
        return JSONResponse({"error": "unknown task"}, status_code=404)
    history = t.get("history", [])
    sliced = history[int(offset) : int(offset) + int(limit)]
    return {"task_id": task_id, "history": sliced}


class IdList(BaseModel):
    ids: List[str]
    limit: int | None = 1
    offset: int | None = 0


@app.post("/bg/histories")
def bg_histories(payload: IdList):
    """Return history entries for multiple task ids in one request.

    Request body: { ids: [...], limit: int (per-id limit, default 1), offset: int }
    Response: { histories: { id: [events...] } }
    """
    ids = payload.ids or []
    limit = int(payload.limit or 1)
    offset = int(payload.offset or 0)
    if not ids:
        return {"histories": {}}

    n_ids = len(ids)
    if n_ids > HARD_IDS_LIMIT:
        raise HTTPException(status_code=413, detail=f"too many ids in request ({n_ids} > {HARD_IDS_LIMIT})")

    # Warning for large requests; we'll still process but in batches
    warnings: List[str] = []
    if n_ids > MAX_IDS_PER_REQUEST:
        warnings.append(f"request contains {n_ids} ids; processing in internal batches of {BG_HISTORIES_BATCH_SIZE}")

    out: Dict[str, List[Dict[str, Any]]] = {}

    # DB-backed path: reuse a single session and process ids in chunks to keep IN(...) lists small
    if os.environ.get("DATABASE_URL"):
        session = SessionLocal()
        try:
            # pre-fill keys with empty lists so missing ids return []
            for i in ids:
                out[str(i)] = []

            from sqlalchemy import select, func

            for start in range(0, n_ids, BG_HISTORIES_BATCH_SIZE):
                chunk = ids[start : start + BG_HISTORIES_BATCH_SIZE]

                # build mapping of valid UUIDs in this chunk
                valid_map = {}
                for i in chunk:
                    # skip obviously-invalid short strings to avoid accidental coercion
                    if not isinstance(i, str) or len(i) not in (32, 36):
                        continue
                    try:
                        u = uuid.UUID(i)
                        valid_map[u] = str(i)
                    except Exception:
                        # invalid UUIDs are left as empty lists
                        continue

                if not valid_map:
                    continue

                # window function per task_id ordered by event_ts desc
                rownum = func.row_number().over(partition_by=TaskHistory.task_id, order_by=TaskHistory.event_ts.desc()).label("rn")
                subq = (
                    select(
                        TaskHistory.id,
                        TaskHistory.task_id,
                        TaskHistory.event_ts,
                        TaskHistory.event_type,
                        TaskHistory.payload,
                        rownum,
                    )
                    .where(TaskHistory.task_id.in_(list(valid_map.keys())))
                    .subquery()
                )

                q = (
                    select(subq)
                    .where(subq.c.rn > offset)
                    .where(subq.c.rn <= (offset + limit))
                    .order_by(subq.c.task_id, subq.c.rn)
                )
                res = session.execute(q).all()

                for row in res:
                    tid = str(row.task_id)
                    entries = out.setdefault(tid, [])
                    entries.append(
                        {
                            "event_ts": row.event_ts.isoformat() + "Z" if row.event_ts else None,
                            "event_type": row.event_type,
                            "payload": row.payload,
                        }
                    )

            resp = {"histories": out}
            if warnings:
                resp["warnings"] = warnings
            return resp
        finally:
            session.close()

    # file-backed fallback: read once and process in chunks
    try:
        with open(DB_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        return {"histories": {}}

    for start in range(0, n_ids, BG_HISTORIES_BATCH_SIZE):
        chunk = ids[start : start + BG_HISTORIES_BATCH_SIZE]
        for i in chunk:
            t = data.get(i)
            if not t:
                out[str(i)] = []
                continue
            hist = t.get("history", [])
            if not hist:
                out[str(i)] = []
                continue
            sliced = hist[max(0, len(hist) - offset - limit) : len(hist) - offset]
            out[str(i)] = list(reversed(sliced))

    resp = {"histories": out}
    if warnings:
        resp["warnings"] = warnings
    return resp


@app.post("/bg/cancel/{task_id}")
def bg_cancel(task_id: str):
    """Request cancellation for a background task started via Celery.

    This attempts to revoke/terminate the Celery task and marks the
    task cancelled in the local task store for immediate API visibility.
    """
    try:
        celery.control.revoke(task_id, terminate=True, signal="SIGTERM")
    except Exception:
        # best-effort: ignore revoke errors and still mark cancelled
        pass
    # mark cancelled in our bg store
    try:
        update_task_cancelled(task_id)
    except Exception:
        pass
    return {"task_id": task_id, "cancelled": True}
