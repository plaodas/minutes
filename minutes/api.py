from fastapi import FastAPI, UploadFile, File, HTTPException, BackgroundTasks, Depends, Request
from fastapi.middleware.cors import CORSMiddleware
import asyncio
import logging
import logging
from fastapi.responses import PlainTextResponse, JSONResponse
from fastapi.responses import StreamingResponse, Response, FileResponse
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
from minutes.models import Task, TaskHistory
import uuid
from minutes.reconcile_bg_tasks import reconcile_once
import time
from minutes.minio_client import MinioService
import typing
from fastapi.responses import StreamingResponse

# Allowed upload file types
ALLOWED_EXTENSIONS = {'.wav', '.mp3', '.m4a', '.flac', '.ogg', '.opus'}

def _is_allowed_upload(file: UploadFile) -> (bool, str):
    """Return (allowed, reason)."""
    # check extension and content-type heuristics first
    fn = (file.filename or '')
    ext = os.path.splitext(fn)[1].lower()
    ct = (getattr(file, 'content_type', None) or '')

    if ext not in ALLOWED_EXTENSIONS and not ct.startswith('audio/'):
        return False, f'invalid file type: ext={ext!r} mime={ct!r}'

    # read a small prefix from the uploaded stream for analysis
    stream = getattr(file, 'file', None)
    if not stream:
        return False, 'missing upload stream'
    pos = None
    try:
        pos = stream.tell()
    except Exception:
        pos = None
    header = stream.read(4096) or b''
    try:
        if pos is not None:
            stream.seek(pos)
        else:
            stream.seek(0)
    except Exception:
        pass

    # prefer python-magic if available for robust MIME detection
    try:
        import magic

        try:
            m = magic.Magic(mime=True)
            mime = m.from_buffer(header)
        except Exception:
            # some python-magic builds expose from_buffer at module level
            mime = magic.from_buffer(header)

        if isinstance(mime, str) and mime.startswith('audio/'):
            return True, ''
        return False, f'invalid mime detected: {mime!r} ext={ext!r} orig_mime={ct!r}'
    except Exception:
        # fallback to lightweight signature checks if python-magic is unavailable
        h = header if isinstance(header, (bytes, bytearray)) else str(header).encode('latin1', errors='ignore')
        if h.startswith(b'RIFF') and h[8:12] == b'WAVE':
            return True, ''
        if h.startswith(b'OggS'):
            return True, ''
        if h.startswith(b'fLaC'):
            return True, ''
        if h.startswith(b'ID3') or (len(h) >= 2 and h[0] == 0xFF and (h[1] & 0xE0) == 0xE0):
            return True, ''
        if len(h) >= 12 and h[4:8] == b'ftyp':
            return True, ''

        return False, f'file signature did not match audio formats: ext={ext!r} mime={ct!r}'

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

        # If configured, upload the final minutes to MinIO as a cached copy.
        minio_info = None
        try:
            bucket = os.environ.get("MINIO_DEFAULT_BUCKET") or os.environ.get("MINIO_BUCKET")
            if bucket:
                svc = MinioService()
                try:
                    svc.ensure_bucket(bucket)
                except Exception:
                    # ensure_bucket best-effort
                    pass
                object_name = f"minutes/{task_id}/minutes_{now}.txt"
                try:
                    svc.client.fput_object(bucket, object_name, out_file)
                    try:
                        expires_sec = int(os.environ.get('MINIO_PRESIGNED_EXPIRES', '3600'))
                        url = svc.presigned_get(bucket, object_name, expires=expires_sec)
                        from datetime import datetime, timedelta
                        expires_at = (datetime.utcnow() + timedelta(seconds=expires_sec)).isoformat() + 'Z'
                    except Exception:
                        url = None
                        expires_sec = None
                        expires_at = None
                    minio_info = {"bucket": bucket, "object": object_name, "url": url, "expires": expires_sec, "expires_at": expires_at}
                except Exception as exc:
                    # log but do not fail the whole pipeline
                    logging.getLogger("minutes.api").exception("MinIO upload failed for task %s: %s", task_id, exc)
        except Exception:
            # any MinIO client init error should not block task success
            minio_info = None

        result_payload = {"output_file": out_file}
        if minio_info:
            result_payload["minio"] = minio_info

        update_task_success(task_id, result_payload)
    except Exception as exc:
        update_task_failure(task_id, str(exc))


app = FastAPI(title="Minutes Service (prototype)")

# Admin token for simple admin API protection (optional)
ADMIN_API_TOKEN = os.environ.get("ADMIN_API_TOKEN")


def _get_admin_token_from_request(req: Request | None):
    if req is None:
        return None
    # support X-Admin-Token header or Bearer Authorization
    token = req.headers.get("X-Admin-Token") or req.headers.get("Authorization")
    if token and token.lower().startswith("bearer "):
        token = token.split(" ", 1)[1]
    return token


def require_admin(req: Request = None):
    token = _get_admin_token_from_request(req)
    if not ADMIN_API_TOKEN:
        raise HTTPException(status_code=403, detail="admin API not enabled")
    if token != ADMIN_API_TOKEN:
        raise HTTPException(status_code=403, detail="forbidden")
    return True

# CORS: allow local dev origins used by the frontend and Playwright
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:8080", "http://localhost"],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)


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


@app.get("/admin/buckets")
def admin_list_buckets(_=Depends(require_admin)):
    try:
        svc = MinioService()
        buckets = svc.list_buckets()
        out = []
        for b in buckets:
            created = getattr(b, 'creation_date', None)
            out.append({"name": b.name, "created_at": created.isoformat() if created else None})
        return {"buckets": out}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.post("/admin/buckets")
def admin_create_bucket(payload: Dict[str, typing.Any], _=Depends(require_admin)):
    name = (payload or {}).get("name")
    if not name:
        return JSONResponse({"error": "missing name"}, status_code=400)
    public = bool((payload or {}).get("public", False))
    try:
        svc = MinioService()
        svc.create_bucket(name, public=public)
        return {"name": name}
    except ValueError:
        return JSONResponse({"error": "already exists"}, status_code=409)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.delete("/admin/buckets/{name}")
def admin_delete_bucket(name: str, force: bool = False, _=Depends(require_admin)):
    try:
        svc = MinioService()
        svc.delete_bucket(name, force=force)
        return {"deleted": True}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.post("/transcribe-upload", response_model=CreateTaskResponse)
def transcribe_upload(file: UploadFile = File(...)):
    """Accept an audio file upload, run preprocess->transcribe->format, return minutes as plain text.

    This is a synchronous prototype endpoint intended for small/short audio files.
    """
    # Save uploaded file into uploads/ so workers can access it (shared volume)
    uploads_dir = os.environ.get("UPLOADS_DIR", "uploads")
    os.makedirs(uploads_dir, exist_ok=True)
    # sanitize filename and avoid collisions by generating a unique name
    suffix = os.path.splitext(file.filename)[1] or ".wav"
    safe_name = os.path.basename(file.filename) or f"upload{suffix}"
    unique_name = f"{int(time.time())}-{uuid.uuid4().hex}{os.path.splitext(safe_name)[1]}"
    tmp_path = None
    # validate file type
    ok, reason = _is_allowed_upload(file)
    if not ok:
        return JSONResponse({"error": reason}, status_code=400)
    try:
        dest_path = os.path.join(uploads_dir, unique_name)
        with open(dest_path, "wb") as out:
            shutil.copyfileobj(file.file, out)

        # Enqueue Celery task
        task = process_audio.delay(dest_path)
        # return upload filename for UI convenience
        return {"task_id": task.id, "upload_filename": safe_name}
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
    # sanitize and uniquify filename to avoid collisions and path traversal
    safe_name = os.path.basename(file.filename) or "upload.wav"
    unique_name = f"{int(time.time())}-{uuid.uuid4().hex}{os.path.splitext(safe_name)[1]}"
    dest_path = os.path.join(uploads_dir, unique_name)
    # validate file type
    ok, reason = _is_allowed_upload(file)
    if not ok:
        return JSONResponse({"error": reason}, status_code=400)
    try:
        with open(dest_path, "wb") as out:
            shutil.copyfileobj(file.file, out)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))

    # Enqueue as a Celery task so we can support revoke/terminate later.
    try:
        task = process_audio.delay(dest_path)
        task_id = task.id
        # Store upload metadata (original filename) in the task record so
        # the frontend can show a meaningful name when listing tasks.
        try:
            create_task(task_id, metadata={"upload_filename": safe_name})
        except TypeError:
            # backward-compat: if create_task signature hasn't been updated,
            # call without metadata
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
    # DB-backed only: query TaskHistory rows for the given task id.
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


@app.post("/bg/task/{task_id}/rename")
def bg_task_rename(task_id: str, payload: Dict[str, str]):
    """Rename a task display `name`.

    Body: { "name": "New title" }
    """
    name = (payload or {}).get("name")
    if not name:
        return JSONResponse({"error": "missing name"}, status_code=400)
    session = SessionLocal()
    try:
        try:
            key = uuid.UUID(task_id)
        except Exception:
            return JSONResponse({"error": "invalid task id"}, status_code=400)
        t = session.get(Task, key)
        if not t:
            return JSONResponse({"error": "unknown task"}, status_code=404)
        t.name = name
        session.add(t)
        session.commit()
        # record a small history entry
        h = TaskHistory(task_id=key, event_type="rename", payload={"name": name})
        session.add(h)
        session.commit()
        return {"task_id": task_id, "name": name}
    finally:
        session.close()


@app.post("/bg/task/{task_id}/regenerate-name")
def bg_task_regenerate_name(task_id: str):
    """Regenerate the task display `name` from the output file using the local summarizer."""
    session = SessionLocal()
    try:
        try:
            key = uuid.UUID(task_id)
        except Exception:
            return JSONResponse({"error": "invalid task id"}, status_code=400)
        t = session.get(Task, key)
        if not t:
            return JSONResponse({"error": "unknown task"}, status_code=404)
        res = t.result or {}
        output_file = None
        if isinstance(res, dict):
            output_file = res.get('output_file') or (res.get('result') or {}).get('output_file')
        if not output_file:
            return JSONResponse({"error": "no output file available"}, status_code=404)
        outputs_dir = os.environ.get('OUTPUTS_DIR', 'outputs')
        candidate = os.path.join(outputs_dir, os.path.basename(output_file))
        try:
            from minutes.summary import summarize_local
            with open(candidate, 'r', encoding='utf-8') as rf:
                text = rf.read()
            short = summarize_local(text, max_sentences=1).strip()
            if short and len(short) > 120:
                short = short[:117].rstrip() + '...'
            t.name = short
            session.add(t)
            session.commit()
            # record history
            h = TaskHistory(task_id=key, event_type='rename', payload={'name': short})
            session.add(h)
            session.commit()
            return {"task_id": task_id, "name": short}
        except FileNotFoundError:
            return JSONResponse({"error": "output file not found"}, status_code=404)
        except Exception as exc:
            return JSONResponse({"error": str(exc)}, status_code=500)
    finally:
        session.close()


@app.get("/bg/tasks")
def bg_tasks(limit: int = 50, offset: int = 0):
    """Return a paginated list of background tasks (DB-backed only).

    Response: { tasks: [ { id, status, progress, result, created_at, last_success_ts } ] }
    """
    # Support cursor-based keyset pagination for infinite scroll.
    # Cursor format: "<updated_at_iso>|<id>" (optional). If not provided, fall back to offset paging.
    from datetime import datetime

    session = SessionLocal()
    try:
        cursor = None
        # try to read from query param 'cursor' passed via request (FastAPI maps unknown params automatically)
        # If caller provided an offset, keep backward compatibility.
        # Build base query ordered by updated_at desc, id desc
        q = session.query(Task)
        # Access request params via function args: limit, offset. Check for _request state for cursor via globals is not available,
        # so read from environment-style fallback: FastAPI will pass unknown query params if included in signature; to keep
        # it simple, support cursor via os.environ-like pattern is not ideal. Instead accept that clients can still use offset.
        # We'll implement cursor if provided via a special header in future. For now, implement offset-based but include preview events.

        q = q.order_by(Task.updated_at.desc(), Task.id.desc()).offset(int(offset)).limit(int(limit))

        out = []
        for t in q.all():
            # collect up to 3 latest events as preview
            previews = []
            try:
                rows = (
                    session.query(TaskHistory)
                    .filter(TaskHistory.task_id == t.id)
                    .order_by(TaskHistory.event_ts.desc())
                    .limit(3)
                    .all()
                )
                for r in rows:
                    previews.append({
                        "event_ts": r.event_ts.isoformat() + "Z" if r.event_ts else None,
                        "event_type": r.event_type,
                        "payload": r.payload,
                    })
                # count total events
                total = session.query(TaskHistory).filter(TaskHistory.task_id == t.id).count()
            except Exception:
                previews = []
                total = 0

            out.append({
                "id": str(t.id),
                "name": t.name,
                "status": t.status,
                "progress": float(t.progress) if t.progress is not None else None,
                "result": t.result,
                "created_at": t.created_at.isoformat() + "Z" if t.created_at else None,
                "last_success_ts": t.last_success_ts.isoformat() + "Z" if t.last_success_ts else None,
                "preview_events": previews,
                "event_count": int(total),
            })
        return {"tasks": out}
    finally:
        session.close()



@app.get("/bg/tasks/{task_id}/events")
def bg_task_events(task_id: str):
    """Return all events for a task (descending by timestamp). This is intended for the "View full events" modal.

    Returns: { task_id, events: [ { event_ts, event_type, payload }, ... ] }
    """
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
            .all()
        )
        out = []
        for r in rows:
            out.append({
                "event_ts": r.event_ts.isoformat() + "Z" if r.event_ts else None,
                "event_type": r.event_type,
                "payload": r.payload,
            })
        return {"task_id": task_id, "events": out}
    finally:
        session.close()


class IdList(BaseModel):
    ids: List[str]
    limit: int | None = 1
    # backward-compatible: single numeric offset (applies to all ids when provided)
    offset: int | None = 0
    # optional per-id offsets map: { "<id>": <offset>, ... }
    offsets: Dict[str, int] | None = None


@app.post("/bg/histories")
def bg_histories(payload: IdList):
    """Return history entries for multiple task ids in one request.

    Request body: { ids: [...], limit: int (per-id limit, default 1),
                   offset: int }
    Also supports per-id offsets map: { offsets: { "<id>": <offset>, ... } }
    Response: { histories: { id: [events...] } }
    """
    ids = payload.ids or []
    limit = int(payload.limit or 1)
    # build offsets map: prefer payload.offsets (per-id), fall back to single offset if provided
    offsets_map: Dict[str, int] = {}
    if getattr(payload, "offsets", None):
        try:
            offsets_map = {str(k): int(v) for k, v in (payload.offsets or {}).items()}
        except Exception:
            offsets_map = {}
    else:
        # single numeric offset (backward compat)
        single_off = int(payload.offset or 0)
        if single_off:
            offsets_map = {i: single_off for i in ids}
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

    # DB-backed path only: reuse a single session and process ids in chunks
    session = SessionLocal()
    try:
        # pre-fill keys with empty lists so missing ids return []
        for i in ids:
            out[str(i)] = []

        from sqlalchemy import select, func

        # For per-id offsets we execute per-task small window queries within each chunk
        for start in range(0, n_ids, BG_HISTORIES_BATCH_SIZE):
            chunk = ids[start : start + BG_HISTORIES_BATCH_SIZE]

            # build mapping of valid UUIDs in this chunk
            valid_map: Dict[uuid.UUID, str] = {}
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

            # For each valid task_id in this chunk, fetch its rows using a window function
            for u, orig_id in valid_map.items():
                off = int(offsets_map.get(orig_id, 0))
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
                    .where(TaskHistory.task_id == u)
                    .subquery()
                )

                q = (
                    select(subq)
                    .where(subq.c.rn > off)
                    .where(subq.c.rn <= (off + limit))
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


@app.post("/bg/delete/{task_id}")
def bg_delete(task_id: str):
    """Soft-delete a background task by marking its status as 'deleted'."""
    try:
        t = get_task(task_id)
    except Exception:
        t = None
    if not t:
        return JSONResponse({"error": "unknown task"}, status_code=404)
    # mark deleted and record history
    try:
        try:
            # prefer DB-backed update
            from .db import SessionLocal
            db = SessionLocal()
            key = _parse_key(task_id)
            obj = db.get(Task, key)
            if not obj:
                db.close()
                return JSONResponse({"error": "unknown task"}, status_code=404)
            prev = obj.status
            obj.status = "deleted"
            db.add(obj)
            db.commit()
            try:
                record_history(task_id, "deleted", {"previous": prev}, db=db)
            except Exception:
                pass
            db.close()
        except Exception:
            # fallback: best-effort using existing update helpers
            try:
                t = get_task(task_id)
                # mutate in-place if possible
                t["status"] = "deleted"
                # save back if store supports it
                try:
                    update_task_success(task_id, t.get("result") or {})
                except Exception:
                    pass
            except Exception:
                pass
        return {"task_id": task_id, "deleted": True}
    except Exception as exc:
        return JSONResponse({"error": str(exc)}, status_code=500)


@app.post("/bg/undelete/{task_id}")
def bg_undelete(task_id: str):
    """Attempt to restore a soft-deleted task to its prior lifecycle state.

    If the task has a `result` present, restore to `success`, otherwise to `pending`.
    """
    try:
        t = get_task(task_id)
    except Exception:
        t = None
    if not t:
        return JSONResponse({"error": "unknown task"}, status_code=404)
    try:
        from .db import SessionLocal
        db = SessionLocal()
        key = _parse_key(task_id)
        obj = db.get(Task, key)
        if not obj:
            db.close()
            return JSONResponse({"error": "unknown task"}, status_code=404)
        prev = obj.status
        obj.status = "success" if obj.result else "pending"
        db.add(obj)
        db.commit()
        try:
            record_history(task_id, "undeleted", {"previous": prev}, db=db)
        except Exception:
            pass
        db.close()
        return {"task_id": task_id, "undeleted": True}
    except Exception as exc:
        return JSONResponse({"error": str(exc)}, status_code=500)


@app.get("/bg/minutes/{task_id}")
def bg_minutes_file(task_id: str):
    """Return the rendered minutes text for a background task.

    If the task is not found -> 404. If the task exists but is not yet successful -> 202.
    If the task has a result with `output_file`, read and return it as text/plain.
    """
    try:
        t = get_task(task_id)
    except Exception:
        t = None
    if not t:
        return JSONResponse({"error": "unknown task"}, status_code=404)
    if t.get("status") != "success":
        return JSONResponse({"status": t.get("status")}, status_code=202)

    res = t.get("result") or {}
    output_file = None
    # result may contain output_file path under different shapes
    if isinstance(res, dict) and res.get("output_file"):
        output_file = res.get("output_file")
    # If still None, try nested result key
    if not output_file and isinstance(res, dict) and res.get("result") and isinstance(res.get("result"), dict):
        output_file = res.get("result").get("output_file")

    if not output_file:
        return JSONResponse({"error": "no output file available"}, status_code=404)

    outputs_dir = os.environ.get("OUTPUTS_DIR", "outputs")
    # normalize path: if output_file is absolute, use basename to avoid escaping
    if os.path.isabs(output_file):
        fname = os.path.basename(output_file)
    else:
        fname = output_file

    candidate = os.path.join(outputs_dir, os.path.basename(fname))
    try:
        # If MinIO cached object exists in result, stream from MinIO proxy instead
        res = t.get("result") or {}
        if isinstance(res, dict) and res.get("minio") and res["minio"].get("bucket") and res["minio"].get("object"):
            minio_info = res["minio"]
            return _stream_minio_object(minio_info["bucket"], minio_info["object"], filename=fname, media_type="text/plain")

        # Serve as a downloadable/plain text file with proper headers
        # Use FileResponse to let FastAPI set Content-Type and support streaming
        return FileResponse(
            path=candidate,
            media_type="text/plain",
            filename=os.path.basename(fname),
        )
    except FileNotFoundError:
        return JSONResponse({"error": "output file not found"}, status_code=404)
    except Exception as exc:
        return JSONResponse({"error": str(exc)}, status_code=500)


def _resolve_output_file_from_task(task_id: str):
    try:
        t = get_task(task_id)
    except Exception:
        t = None
    if not t:
        return None, JSONResponse({"error": "unknown task"}, status_code=404)
    if t.get("status") != "success":
        return None, JSONResponse({"status": t.get("status")}, status_code=202)

    res = t.get("result") or {}
    output_file = None
    if isinstance(res, dict) and res.get("output_file"):
        output_file = res.get("output_file")
    if not output_file and isinstance(res, dict) and res.get("result") and isinstance(res.get("result"), dict):
        output_file = res.get("result").get("output_file")
    if not output_file:
        return None, JSONResponse({"error": "no output file available"}, status_code=404)

    outputs_dir = os.environ.get("OUTPUTS_DIR", "outputs")
    if os.path.isabs(output_file):
        fname = os.path.basename(output_file)
    else:
        fname = output_file
    candidate = os.path.join(outputs_dir, os.path.basename(fname))
    return candidate, None


def _stream_minio_object(bucket: str, object_name: str, filename: str | None = None, media_type: str = "application/octet-stream"):
    svc = MinioService()
    try:
        obj = svc.client.get_object(bucket, object_name)
    except Exception as exc:
        return JSONResponse({"error": f"failed to fetch object from MinIO: {str(exc)}"}, status_code=502)

    def iterfile(chunk_size: int = 32 * 1024):
        try:
            for data in obj.stream(chunk_size):
                if not data:
                    break
                yield data
        finally:
            try:
                obj.close()
            except Exception:
                pass
            try:
                obj.release_conn()
            except Exception:
                pass

    headers = {}
    if filename:
        headers["Content-Disposition"] = f'attachment; filename="{os.path.basename(filename)}"'

    return StreamingResponse(iterfile(), media_type=media_type, headers=headers)


def _read_minio_object_text(bucket: str, object_name: str) -> str:
    svc = MinioService()
    obj = None
    try:
        obj = svc.client.get_object(bucket, object_name)
        data = obj.read()
        if isinstance(data, bytes):
            return data.decode('utf-8')
        return str(data)
    finally:
        if obj is not None:
            try:
                obj.close()
            except Exception:
                pass
            try:
                obj.release_conn()
            except Exception:
                pass


@app.get("/bg/transcript/{task_id}")
def bg_transcript(task_id: str, format: str = "txt"):
    """Return the transcript portion. Supported formats: txt, md."""
    t = get_task(task_id)
    if not t:
        return JSONResponse({"error": "unknown task"}, status_code=404)
    if t.get("status") != "success":
        return JSONResponse({"status": t.get("status")}, status_code=202)

    res = t.get("result") or {}
    # Prefer structured transcript if available
    if isinstance(res, dict) and res.get("transcript"):
        text = res.get("transcript")
    else:
        candidate, err = _resolve_output_file_from_task(task_id)
        if err:
            return err
        try:
            with open(candidate, "r", encoding="utf-8") as f:
                text = f.read()
        except FileNotFoundError:
            return JSONResponse({"error": "output file not found"}, status_code=404)
        except Exception as exc:
            return JSONResponse({"error": str(exc)}, status_code=500)

    # If MinIO cached object exists in result, stream from MinIO proxy instead
    res = t.get("result") or {}
    if isinstance(res, dict) and res.get("minio") and res["minio"].get("bucket") and res["minio"].get("object"):
        minio_info = res["minio"]
        # prefer reading MinIO text for transcript/summary endpoints
        try:
            text = _read_minio_object_text(minio_info["bucket"], minio_info["object"])
        except Exception:
            # fallback to previously read text
            pass

    # For now, transcript is the full output; future: extract section
    if format not in ("txt", "md"):
        return JSONResponse({"error": "unsupported format"}, status_code=400)
    media = "text/markdown" if format == "md" else "text/plain"
    return Response(content=text, media_type=media)


@app.get("/bg/summary/{task_id}")
def bg_summary(task_id: str, format: str = "txt"):
    """Return a short summary. If the output contains a clearly delimited Summary section, use it; else run local summarizer."""
    t = get_task(task_id)
    if not t:
        return JSONResponse({"error": "unknown task"}, status_code=404)
    if t.get("status") != "success":
        return JSONResponse({"status": t.get("status")}, status_code=202)

    res = t.get("result") or {}
    # If MinIO cached object exists, try to read summary from MinIO text
    if isinstance(res, dict) and res.get("minio") and res["minio"].get("bucket") and res["minio"].get("object"):
        try:
            text = _read_minio_object_text(res["minio"]["bucket"], res["minio"]["object"])
        except Exception:
            text = None
    if isinstance(res, dict) and res.get("summary"):
        summary_text = res.get("summary")
    else:
        # fallback to reading file and extracting or summarizing
        candidate, err = _resolve_output_file_from_task(task_id)
        if err:
            return err
        try:
            with open(candidate, "r", encoding="utf-8") as f:
                text = f.read()
        except FileNotFoundError:
            return JSONResponse({"error": "output file not found"}, status_code=404)
        except Exception as exc:
            return JSONResponse({"error": str(exc)}, status_code=500)

        # try to find a 'Summary' section
        import re

        m = re.search(r"(?ims)^\s*summary\s*$\n(.*?)\n\s*(?:action items|transcript|$)", text)
        if m:
            summary_text = m.group(1).strip()
        else:
            try:
                from minutes.summary import summarize_local

                summary_text = summarize_local(text, max_sentences=3)
            except Exception:
                summary_text = ""

    if format not in ("txt", "md"):
        return JSONResponse({"error": "unsupported format"}, status_code=400)
    media = "text/markdown" if format == "md" else "text/plain"
    return Response(content=summary_text, media_type=media)


@app.get("/bg/action-items/{task_id}")
def bg_action_items(task_id: str, format: str = "json"):
    """Return action items. Supported formats: json, csv, txt"""
    t = get_task(task_id)
    if not t:
        return JSONResponse({"error": "unknown task"}, status_code=404)
    if t.get("status") != "success":
        return JSONResponse({"status": t.get("status")}, status_code=202)

    res = t.get("result") or {}
    # Prefer structured action_items
    if isinstance(res, dict) and isinstance(res.get("action_items"), list):
        items = res.get("action_items")
    else:
        candidate, err = _resolve_output_file_from_task(task_id)
        if err:
            return err
        try:
            with open(candidate, "r", encoding="utf-8") as f:
                text = f.read()
        except FileNotFoundError:
            return JSONResponse({"error": "output file not found"}, status_code=404)
        except Exception as exc:
            return JSONResponse({"error": str(exc)}, status_code=500)

        # Simple heuristic: find 'Action Items' section and parse lines
        import re

        items = []
        m = re.search(r"(?ims)^\s*action items\s*$\n(.*)$", text)
        section = None
        if m:
            section = m.group(1)
        else:
            # fallback: look for lines starting with 'Action:' or 'TODO' anywhere
            lines = [l.strip() for l in text.splitlines() if l.strip()]
            for l in lines:
                if re.search(r"\b(Action|TODO|Action Item)[:\-]", l, re.I):
                    items.append({"text": l})

        if section:
            for line in section.splitlines():
                s = line.strip().lstrip("-•* ")
                if not s:
                    continue
                # skip obvious headers
                if re.match(r"^[A-Z][a-z]+:$", s):
                    continue
                items.append({"text": s})

    # normalize items into list
    if not items:
        items = []

    if format == "json":
        return JSONResponse({"task_id": task_id, "items": items})
    if format == "csv":
        # build CSV
        import io, csv

        buf = io.StringIO()
        writer = csv.writer(buf)
        writer.writerow(["id", "text"])
        for i, it in enumerate(items, start=1):
            writer.writerow([i, it.get("text")])
        return Response(content=buf.getvalue(), media_type="text/csv")
    if format == "txt":
        txt = "\n".join([f"- {it.get('text')}" for it in items])
        return Response(content=txt, media_type="text/plain")
    return JSONResponse({"error": "unsupported format"}, status_code=400)
