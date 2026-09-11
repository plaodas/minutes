import asyncio
import logging
import os
import shutil
import time
import typing
import uuid
from typing import Any

from celery.exceptions import CeleryError
from celery.result import AsyncResult
from fastapi import (
    BackgroundTasks,
    Cookie,
    Depends,
    FastAPI,
    File,
    Form,
    Header,
    HTTPException,
    Request,
    UploadFile,
)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import (
    FileResponse,
    JSONResponse,
    Response,
    StreamingResponse,
)
from pydantic import BaseModel
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from minutes import tasks
from minutes.audio import preprocess
from minutes.bg_store import (
    _parse_key,
    create_task,
    get_task,
    record_history,
    update_task_cancelled,
    update_task_failure,
    update_task_status,
    update_task_success,
)
from minutes.celery_app import celery
from minutes.db import session_scope
from minutes.minio_client import MinioService
from minutes.models import DUMMY_OWNER_ID, Bucket, Task, TaskHistory
from minutes.ollama import format_minutes_from_raw
from minutes.reconcile_bg_tasks import reconcile_once
from minutes.routers.background_tasks import (
    bg_result,
    bg_task_events,
)
from minutes.routers.background_tasks import (
    router as background_tasks_router,
)
from minutes.schemas import (
    CreateTaskResponse,
    FormatRawRequest,
    FormatRawResponse,
    TaskStage,
    task_stage_from_status,
)
from minutes.transcribe import transcribe

# Allowed upload file types
ALLOWED_EXTENSIONS = {".wav", ".mp3", ".m4a", ".flac", ".ogg", ".opus"}


def _is_allowed_upload(file: UploadFile) -> (bool, str):
    """Return (allowed, reason)."""
    # check extension and content-type heuristics first
    fn = file.filename or ""
    ext = os.path.splitext(fn)[1].lower()
    ct = getattr(file, "content_type", None) or ""

    if ext not in ALLOWED_EXTENSIONS and not ct.startswith("audio/"):
        return False, f"invalid file type: ext={ext!r} mime={ct!r}"

    # read a small prefix from the uploaded stream for analysis
    stream = getattr(file, "file", None)
    if not stream:
        return False, "missing upload stream"
    pos = None
    try:
        pos = stream.tell()
    except (OSError, AttributeError):
        pos = None
    header = stream.read(4096) or b""
    try:
        if pos is not None:
            stream.seek(pos)
        else:
            stream.seek(0)
    except (OSError, ValueError):
        pass

    # prefer python-magic if available for robust MIME detection
    try:
        import magic

        try:
            m = magic.Magic(mime=True)
            mime = m.from_buffer(header)
        except (AttributeError, TypeError):
            # some python-magic builds expose from_buffer at module level
            mime = magic.from_buffer(header)

        if isinstance(mime, str) and mime.startswith("audio/"):
            return True, ""
        return False, f"invalid mime detected: {mime!r} ext={ext!r} orig_mime={ct!r}"
    except ImportError:
        # fallback to lightweight signature checks if python-magic is unavailable
        h = (
            header
            if isinstance(header, (bytes, bytearray))
            else str(header).encode("latin1", errors="ignore")
        )
        if h.startswith(b"RIFF") and h[8:12] == b"WAVE":
            return True, ""
        if h.startswith(b"OggS"):
            return True, ""
        if h.startswith(b"fLaC"):
            return True, ""
        if h.startswith(b"ID3") or (
            len(h) >= 2 and h[0] == 0xFF and (h[1] & 0xE0) == 0xE0
        ):
            return True, ""
        if len(h) >= 12 and h[4:8] == b"ftyp":
            return True, ""

        return (
            False,
            f"file signature did not match audio formats: ext={ext!r} mime={ct!r}",
        )


def _parse_header_user_id(x_user_id: str | None, authorization: str | None = None):
    """Return a uuid.UUID when the header contains a UUID-like value, else None.

    If `x_user_id` is not provided, attempt to resolve an Authorization
    Bearer service token to a user id via `minutes.auth.verify_service_token`.
    """
    logger = logging.getLogger("minutes.api")
    if x_user_id:
        try:
            parsed = _parse_key(x_user_id)
            return parsed if isinstance(parsed, uuid.UUID) else None
        except (ValueError, TypeError, AttributeError):
            return None

    if authorization:
        try:
            import hashlib

            from minutes.auth import verify_service_token

            token = authorization
            if isinstance(token, str) and token.lower().startswith("bearer "):
                token = token.split(" ", 1)[1]
            # fingerprint for auditing (never log raw token)
            try:
                fp = hashlib.sha256(token.encode("utf-8")).hexdigest()[:12]
            except (AttributeError, TypeError, UnicodeEncodeError):
                fp = "<hash-error>"
            logger.info(
                "Authorization header received; resolving service token fingerprint=%s",
                fp,
            )
            uvicorn_logger = logging.getLogger("uvicorn.error")
            uvicorn_logger.info(
                "Authorization header received; resolving service token fingerprint=%s",
                fp,
            )
            user_id = verify_service_token(token)
            if user_id:
                logger.info(
                    "Service token resolved to user=%s fingerprint=%s",
                    str(user_id),
                    fp,
                )
                uvicorn_logger = logging.getLogger("uvicorn.error")
                uvicorn_logger.info(
                    "Service token resolved to user=%s fingerprint=%s",
                    str(user_id),
                    fp,
                )
                try:
                    return uuid.UUID(str(user_id))
                except (ValueError, TypeError):
                    return None
            logger.debug("Service token not recognized fingerprint=%s", fp)
            uvicorn_logger = logging.getLogger("uvicorn.error")
            uvicorn_logger.debug("Service token not recognized fingerprint=%s", fp)
        except (ImportError, SQLAlchemyError, TypeError, ValueError):
            logger.exception("Error resolving service token from Authorization header")
            return None
    return None


# Configuration: request limits for /bg/histories
MAX_IDS_PER_REQUEST = int(os.environ.get("MAX_BG_HISTORIES_IDS", "500"))
# Hard cap to absolutely reject too-large requests
HARD_IDS_LIMIT = int(os.environ.get("MAX_BG_HISTORIES_HARD_LIMIT", "5000"))
# Internal batch size used to split large id lists into smaller DB IN(...) queries
BG_HISTORIES_BATCH_SIZE = int(os.environ.get("BG_HISTORIES_BATCH_SIZE", "200"))


def _run_pipeline_background(input_path: str, task_id: str):
    try:
        # update intermediate status: preprocessing
        update_task_status(task_id, TaskStage.PREPROCESS)
        _mono, _norm, clean = preprocess(input_path)

        # update intermediate status: transcribing
        update_task_status(task_id, TaskStage.TRANSCRIBING)
        raw_text, _segments = transcribe(clean, model_size="medium", prompt=None)

        # update intermediate status: formatting
        update_task_status(task_id, TaskStage.FORMATTING)
        final_minutes = format_minutes_from_raw(raw_text)

        # detect Ollama fallback (service-wide behavior: fallback responses are
        # prefixed with "[FALLBACK] ") and log it for observability.
        logger = logging.getLogger("minutes.api")
        if isinstance(final_minutes, str) and final_minutes.startswith("[FALLBACK]"):
            logger.warning(
                "Task %s used Ollama fallback: %s",
                task_id,
                final_minutes.splitlines()[0],
            )

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
            except OSError:
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
            bucket = os.environ.get("MINIO_DEFAULT_BUCKET") or os.environ.get(
                "MINIO_BUCKET"
            )
            if bucket:
                svc = MinioService()
                try:
                    from minio.error import S3Error

                    svc.ensure_bucket(bucket)
                except S3Error:
                    # ensure_bucket best-effort
                    logging.getLogger("minutes.api").debug(
                        "ensure_bucket failed for %s", bucket, exc_info=True
                    )
                object_name = f"minutes/{task_id}/minutes_{now}.txt"
                try:
                    from minio.error import S3Error

                    svc.client.fput_object(bucket, object_name, out_file)
                    try:
                        expires_sec = int(
                            os.environ.get("MINIO_PRESIGNED_EXPIRES", "3600")
                        )
                        url = svc.presigned_get(
                            bucket, object_name, expires=expires_sec
                        )
                        from datetime import datetime, timedelta, timezone

                        expires_at = (
                            datetime.now(tz=timezone.utc)
                            + timedelta(seconds=expires_sec)
                        ).isoformat()
                    except (ValueError, OSError):
                        url = None
                        expires_sec = None
                        expires_at = None
                    minio_info = {
                        "bucket": bucket,
                        "object": object_name,
                        "url": url,
                        "expires": expires_sec,
                        "expires_at": expires_at,
                    }
                except S3Error:
                    # log but do not fail the whole pipeline
                    logging.getLogger("minutes.api").exception(
                        "MinIO upload failed for task %s", task_id
                    )
        except (OSError, ImportError):
            # any MinIO client init error should not block task success
            minio_info = None

        result_payload = {"output_file": out_file}
        if minio_info:
            result_payload["minio"] = minio_info

        update_task_success(task_id, result_payload)
    except (OSError, ValueError, RuntimeError, SQLAlchemyError, TypeError) as exc:
        update_task_failure(task_id, str(exc))


app = FastAPI(title="Minutes Service (prototype)")
app.include_router(background_tasks_router)

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
    """FastAPI dependency that requires an admin-authenticated user.

    Accepts:
    - a matching `ADMIN_API_TOKEN` via `X-Admin-Token`/Authorization header (legacy)
    - a JWT access token (Bearer) that decodes to a `User` with `is_admin=True`
    - a service token (Bearer) that maps to a `User` with `is_admin=True`
    - a `minutes_session` cookie containing a JWT for an admin user
    """
    # 1) Legacy admin API token (explicit override)
    token = _get_admin_token_from_request(req)
    if ADMIN_API_TOKEN and token == ADMIN_API_TOKEN:
        return True

    # 2) Cookie-based JWT (minutes_session)
    try:
        from minutes.auth import get_current_user_from_cookie

        if req:
            cookie = req.cookies.get("minutes_session")
            if cookie:
                try:
                    user = get_current_user_from_cookie(cookie)
                    if user and getattr(user, "is_admin", False):
                        return True
                except (HTTPException, ValueError, TypeError) as e:
                    logging.getLogger("minutes.api").debug("cookie auth failed: %s", e)
    except (ImportError, ModuleNotFoundError) as e:
        logging.getLogger("minutes.api").debug(
            "get_current_user_from_cookie not available: %s", e
        )

    # 3) Header-based JWT or service token
    try:
        auth = req.headers.get("Authorization") if req else None
        if not auth:
            raise HTTPException(status_code=403, detail="forbidden")
        # delegate to _is_request_admin which understands JWT/service token
        if _is_request_admin(None, auth):
            return True
    except HTTPException:
        raise
    except (ImportError, ValueError, TypeError, SQLAlchemyError) as e:
        logging.getLogger("minutes.api").debug("header auth check failed: %s", e)
        raise HTTPException(status_code=403, detail="forbidden")

    raise HTTPException(status_code=403, detail="forbidden")


# CORS: allow local dev origins used by the frontend and Playwright
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://localhost:8080",
        "http://localhost",
    ],
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
    except (SQLAlchemyError, RuntimeError, OSError):
        logger.exception("Initial reconciliation failed")

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
            except (SQLAlchemyError, RuntimeError, OSError):
                logger.exception("Reconcile loop error")

    # store the task so it can be cancelled on shutdown
    app.state.reconcile_task = asyncio.create_task(reconcile_loop())
    # start Redis-backed SSE relay if configured. Use REDIS_URL or fall back
    # to common broker env vars (CELERY_BROKER_URL / BROKER_URL) so that
    # workers publishing via the broker are relayed to API instances.
    try:
        redis_url = (
            os.environ.get("REDIS_URL")
            or os.environ.get("CELERY_BROKER_URL")
            or os.environ.get("BROKER_URL")
        )
        if redis_url:
            try:
                from minutes.sse import start_redis_listener

                start_redis_listener(redis_url)
            except (ImportError, RuntimeError, OSError):
                logger.exception("failed to start redis listener")
    except (RuntimeError, OSError):
        logger.exception("redis listener startup check failed")


@app.on_event("shutdown")
async def shutdown_reconciler():
    task = getattr(app.state, "reconcile_task", None)
    if task and not task.done():
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
    # stop redis listener if running
    try:
        from minutes.sse import stop_redis_listener

        stop_redis_listener()
    except (ImportError, RuntimeError, OSError):
        logger = logging.getLogger("minutes.api")
        logger.exception("failed to stop redis listener")


@app.get("/api/health")
def health():
    return {"status": "ok"}


@app.get("/api/admin/buckets", dependencies=[Depends(require_admin)])
def admin_list_buckets():
    try:
        svc = MinioService()
        # List DB-backed buckets first, then include any MinIO-only buckets
        with session_scope() as session:
            db_buckets = {b.name: b for b in session.query(Bucket).all()}

        out = []
        try:
            from minio.error import S3Error
        except ImportError:
            S3Error = Exception
        try:
            minio_buckets = svc.list_buckets()
        except (S3Error, OSError):
            minio_buckets = []

        seen = set()
        for b in minio_buckets:
            name = b.name
            created = getattr(b, "creation_date", None)
            rec = db_buckets.get(name)
            out.append(
                {
                    "name": name,
                    "created_at": (
                        rec.created_at.isoformat() + "Z"
                        if rec and rec.created_at
                        else (created.isoformat() if created else None)
                    ),
                    "public": bool(rec.public) if rec is not None else None,
                    "owner_id": str(rec.owner_id) if rec is not None else None,
                    "in_db": rec is not None,
                }
            )
            seen.add(name)

        # include DB-only buckets (if any)
        for name, rec in db_buckets.items():
            if name in seen:
                continue
            out.append(
                {
                    "name": name,
                    "created_at": (
                        rec.created_at.isoformat() + "Z"
                        if rec and rec.created_at
                        else None
                    ),
                    "public": bool(rec.public) if rec is not None else None,
                    "owner_id": str(rec.owner_id) if rec is not None else None,
                    "in_db": True,
                }
            )

        return {"buckets": out}
    except (SQLAlchemyError, OSError, RuntimeError) as exc:
        raise HTTPException(status_code=500, detail=str(exc))


def api_admin_list_buckets():
    return admin_list_buckets()


@app.post("/api/admin/buckets", dependencies=[Depends(require_admin)])
def admin_create_bucket(payload: dict[str, typing.Any]):
    name = (payload or {}).get("name")
    if not name:
        return JSONResponse({"error": "missing name"}, status_code=400)
    public = bool((payload or {}).get("public", False))
    try:
        from minio.error import S3Error
    except ImportError:
        S3Error = Exception
    try:
        svc = MinioService()
        svc.create_bucket(name, public=public)
        # create DB record if not exists
        with session_scope() as session:
            existing = session.query(Bucket).filter(Bucket.name == name).one_or_none()
            if not existing:
                b = Bucket(name=name, public=public)
                session.add(b)
                try:
                    session.commit()
                except IntegrityError:
                    session.rollback()
        return {"name": name}
    except ValueError:
        return JSONResponse({"error": "already exists"}, status_code=409)
    except (S3Error, OSError, SQLAlchemyError) as exc:
        raise HTTPException(status_code=500, detail=str(exc))


def api_admin_create_bucket(payload: dict[str, typing.Any]):
    return admin_create_bucket(payload)


@app.delete("/api/admin/buckets/{name}", dependencies=[Depends(require_admin)])
def admin_delete_bucket(name: str, force: bool = False):
    try:
        try:
            from minio.error import S3Error
        except ImportError:
            S3Error = Exception
        svc = MinioService()
        svc.delete_bucket(name, force=force)
        # remove DB record if present
        with session_scope() as session:
            session.query(Bucket).filter(Bucket.name == name).delete()
            try:
                session.commit()
            except SQLAlchemyError:
                session.rollback()
        return {"deleted": True}
    except (S3Error, OSError, SQLAlchemyError) as exc:
        raise HTTPException(status_code=500, detail=str(exc))


def api_admin_delete_bucket(name: str, force: bool = False):
    return admin_delete_bucket(name, force=force)


@app.post("/api/transcribe-upload", response_model=CreateTaskResponse)
def transcribe_upload(
    file: UploadFile = File(...),  # noqa: B008
    x_user_id: str | None = Header(None),
    authorization: str | None = Header(None),
    language: str | None = Form(None),
    include_actions: str | None = Form(None),
):
    """Accept an audio file upload, run preprocess->transcribe->format, return minutes as plain text.

    This is a synchronous prototype endpoint intended for small/short audio files.
    """
    # Save uploaded file into uploads/ so workers can access it (shared volume)
    uploads_dir = os.environ.get("UPLOADS_DIR", "uploads")
    os.makedirs(uploads_dir, exist_ok=True)
    # sanitize filename and avoid collisions by generating a unique name
    suffix = os.path.splitext(file.filename)[1] or ".wav"
    safe_name = os.path.basename(file.filename) or f"upload{suffix}"
    unique_name = (
        f"{int(time.time())}-{uuid.uuid4().hex}{os.path.splitext(safe_name)[1]}"
    )
    # temporary file path (not used here)
    # validate file type
    ok, reason = _is_allowed_upload(file)
    if not ok:
        return JSONResponse({"error": reason}, status_code=400)
    try:
        dest_path = os.path.join(uploads_dir, unique_name)
        with open(dest_path, "wb") as out:
            shutil.copyfileobj(file.file, out)

        # Enqueue Celery task (use minutes.tasks so tests can monkeypatch it)
        proc = tasks.process_audio
        if hasattr(proc, "delay"):
            task = proc.delay(dest_path)
        else:
            # synchronous callable (test monkeypatch) — call directly
            task = proc(dest_path)
        # return upload filename for UI convenience
        # ensure a Task DB row exists and attach user if provided
        try:
            meta = {"upload_filename": safe_name}
            if language:
                meta["language"] = language
            if include_actions is not None:
                try:
                    meta["include_actions"] = bool(int(include_actions))
                except (ValueError, TypeError):
                    meta["include_actions"] = include_actions in ("1", "true", "True")
            owner = _parse_header_user_id(x_user_id, authorization)
            # Normalize user_id to string when a UUID is returned so callers
            # (and tests that monkeypatch create_task) receive a predictable
            # string value rather than a uuid.UUID object.
            create_task(
                task.id,
                metadata=meta,
                user_id=(str(owner) if isinstance(owner, uuid.UUID) else owner),
            )
        except TypeError:
            # older create_task signature
            try:
                create_task(task.id, metadata={"upload_filename": safe_name})
            except SQLAlchemyError:
                pass
        return {"task_id": task.id, "upload_filename": safe_name}
    except (OSError, RuntimeError, ValueError, SQLAlchemyError) as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.post("/api/format-raw", response_model=FormatRawResponse)
def format_raw(payload: FormatRawRequest):
    """Accept JSON {"raw": "..."} and return formatted minutes as JSON."""
    raw = payload.raw
    if not raw:
        return JSONResponse({"error": "missing 'raw' field"}, status_code=400)

    try:
        minutes = format_minutes_from_raw(raw)
        return {"minutes": minutes}
    except (RuntimeError, ValueError, TypeError) as exc:
        raise HTTPException(status_code=500, detail=str(exc))


def api_format_raw(payload: FormatRawRequest):
    return format_raw(payload)


@app.get("/api/status/{task_id}")
def task_status(task_id: str):
    res = AsyncResult(task_id, app=celery)
    return {"task_id": task_id, "status": res.status, "info": str(res.info)}


def api_task_status(task_id: str):
    return task_status(task_id)


@app.get("/api/result/{task_id}")
def task_result(task_id: str):
    res = AsyncResult(task_id, app=celery)
    if not res.ready():
        return JSONResponse({"status": res.status}, status_code=202)
    if res.failed():
        return JSONResponse(
            {"status": "failed", "info": str(res.info)}, status_code=500
        )
    return JSONResponse({"status": "success", "result": res.result})


def api_task_result(task_id: str):
    return task_result(task_id)


@app.post("/transcribe-upload-bg", response_model=CreateTaskResponse)
def transcribe_upload_bg(
    file: UploadFile = File(...),  # noqa: B008
    background_tasks: BackgroundTasks = None,
    x_user_id: str | None = Header(None),
    authorization: str | None = Header(None),
    language: str | None = Form(None),
    include_actions: str | None = Form(None),
):
    """Minimal async endpoint using FastAPI BackgroundTasks (no Redis/Celery).

    Note: tasks are stored in a file `bg_tasks.json` under the app directory.
    This is best-effort persistence; process restart will not resume running tasks.
    """
    uploads_dir = os.environ.get("UPLOADS_DIR", "uploads")
    os.makedirs(uploads_dir, exist_ok=True)
    # sanitize and uniquify filename to avoid collisions and path traversal
    safe_name = os.path.basename(file.filename) or "upload.wav"
    unique_name = (
        f"{int(time.time())}-{uuid.uuid4().hex}{os.path.splitext(safe_name)[1]}"
    )
    dest_path = os.path.join(uploads_dir, unique_name)
    # validate file type
    ok, reason = _is_allowed_upload(file)
    if not ok:
        return JSONResponse({"error": reason}, status_code=400)
    try:
        with open(dest_path, "wb") as out:
            shutil.copyfileobj(file.file, out)
    except (OSError, AttributeError, ValueError) as exc:
        raise HTTPException(status_code=500, detail=str(exc))

    # Enqueue as a Celery task so we can support revoke/terminate later.
    try:
        proc = tasks.process_audio
        if hasattr(proc, "delay"):
            task = proc.delay(dest_path)
        else:
            task = proc(dest_path)
        task_id = task.id
        # Store upload metadata (original filename + settings) in the task record so
        # the frontend can show a meaningful name when listing tasks and workers can
        # adjust prompts based on user settings.
        try:
            meta = {"upload_filename": safe_name}
            if language:
                meta["language"] = language
            if include_actions is not None:
                try:
                    meta["include_actions"] = bool(int(include_actions))
                except (ValueError, TypeError):
                    meta["include_actions"] = include_actions in ("1", "true", "True")
            owner = _parse_header_user_id(x_user_id, authorization)
            # Ensure we pass a string user id to `create_task` for downstream
            # consumers and tests that expect string values.
            create_task(
                task_id,
                metadata=meta,
                user_id=(str(owner) if isinstance(owner, uuid.UUID) else owner),
            )
        except TypeError:
            # backward-compat: if create_task signature hasn't been updated,
            # call without metadata
            try:
                create_task(task_id)
            except SQLAlchemyError:
                pass
        return {"task_id": task_id}
    except (OSError, RuntimeError, ValueError, SQLAlchemyError) as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.post("/api/transcribe-upload-bg", response_model=CreateTaskResponse)
def api_transcribe_upload_bg(
    file: UploadFile = File(...),  # noqa: B008
    background_tasks: BackgroundTasks = None,
    x_user_id: str | None = Header(None),
    authorization: str | None = Header(None),
    language: str | None = Form(None),
    include_actions: str | None = Form(None),
):
    """Compatibility wrapper for `/api/transcribe-upload-bg` used by the frontend."""
    return transcribe_upload_bg(
        file=file,
        background_tasks=background_tasks,
        x_user_id=x_user_id,
        authorization=authorization,
        language=language,
        include_actions=include_actions,
    )


@app.post("/transcribe-upload", response_model=CreateTaskResponse)
def root_transcribe_upload(
    file: UploadFile = File(...),  # noqa: B008
    x_user_id: str | None = Header(None),
    authorization: str | None = Header(None),
    language: str | None = Form(None),
    include_actions: str | None = Form(None),
):
    """Root-path compatibility wrapper for older clients/tests."""
    return transcribe_upload(
        file=file,
        x_user_id=x_user_id,
        authorization=authorization,
        language=language,
        include_actions=include_actions,
    )


def api_transcribe_upload(
    file: UploadFile = File(...),  # noqa: B008
    x_user_id: str | None = Header(None),
    authorization: str | None = Header(None),
    language: str | None = Form(None),
    include_actions: str | None = Form(None),
):
    """Compatibility wrapper for `/api/transcribe-upload` (synchronous) used by some clients."""
    return transcribe_upload(
        file=file,
        x_user_id=x_user_id,
        authorization=authorization,
        language=language,
        include_actions=include_actions,
    )


def api_bg_result(task_id: str):
    return bg_result(task_id)


@app.get("/api/bg/history/{task_id}")
def bg_history(task_id: str, limit: int = 100, offset: int = 0):
    """Return task history events. Works with DB-backed store or file-backed fallback."""
    # DB-backed only: query TaskHistory rows for the given task id.
    with session_scope() as session:
        try:
            key = uuid.UUID(task_id)
        except (ValueError, TypeError):
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
            out.append(
                {
                    "event_ts": r.event_ts.isoformat() + "Z" if r.event_ts else None,
                    "event_type": r.event_type,
                    "payload": r.payload,
                }
            )
        return {"task_id": task_id, "history": out}


def api_bg_history(task_id: str, limit: int = 100, offset: int = 0):
    return bg_history(task_id, limit=limit, offset=offset)


def api_bg_tasks(limit: int = 50, offset: int = 0):
    """Compatibility wrapper for `/api/bg/tasks`."""
    return bg_tasks(limit=limit, offset=offset)


def api_bg_task_rename(task_id: str, payload: dict[str, str]):
    """Compatibility wrapper for `/api/bg/task/{task_id}/rename`."""
    return bg_task_rename(task_id, payload)


def api_bg_task_regenerate_name(task_id: str):
    """Compatibility wrapper for `/api/bg/task/{task_id}/regenerate-name`."""
    return bg_task_regenerate_name(task_id)


def api_bg_task_events(task_id: str):
    """Compatibility wrapper for `/api/bg/tasks/{task_id}/events`."""
    return bg_task_events(task_id)


@app.post("/api/bg/task/{task_id}/rename")
def bg_task_rename(task_id: str, payload: dict[str, str]):
    """Rename a task display `name`.

    Body: { "name": "New title" }
    """
    name = (payload or {}).get("name")
    if not name:
        return JSONResponse({"error": "missing name"}, status_code=400)
    with session_scope() as session:
        try:
            key = uuid.UUID(task_id)
        except (ValueError, TypeError):
            return JSONResponse({"error": "invalid task id"}, status_code=400)
        t = session.get(Task, key)
        if not t:
            return JSONResponse({"error": "unknown task"}, status_code=404)
        t.name = name
        session.add(t)
        session.commit()
        try:
            record_history(task_id, "rename", {"name": name}, db=session)
        except SQLAlchemyError:
            logging.getLogger("minutes.api").exception(
                "record_history failed for %s", task_id
            )
        return {"task_id": task_id, "name": name}


@app.post("/api/bg/task/{task_id}/regenerate-name")
def bg_task_regenerate_name(task_id: str):
    """Regenerate the task display `name` from the output file using the local summarizer."""
    with session_scope() as session:
        try:
            key = uuid.UUID(task_id)
        except (ValueError, TypeError):
            return JSONResponse({"error": "invalid task id"}, status_code=400)
        t = session.get(Task, key)
        if not t:
            return JSONResponse({"error": "unknown task"}, status_code=404)
        res = t.result or {}
        output_file = None
        if isinstance(res, dict):
            output_file = res.get("output_file") or (res.get("result") or {}).get(
                "output_file"
            )
        if not output_file:
            return JSONResponse({"error": "no output file available"}, status_code=404)
        outputs_dir = os.environ.get("OUTPUTS_DIR", "outputs")
        candidate = os.path.join(outputs_dir, os.path.basename(output_file))
        try:
            from minutes.summary import summarize_local

            with open(candidate, "r", encoding="utf-8") as rf:
                text = rf.read()
            short = summarize_local(text, max_sentences=1).strip()
            if short and len(short) > 120:
                short = short[:117].rstrip() + "..."
            t.name = short
            session.add(t)
            session.commit()
            try:
                record_history(task_id, "rename", {"name": short}, db=session)
            except SQLAlchemyError:
                logging.getLogger("minutes.api").exception(
                    "record_history failed for %s", task_id
                )
            return {"task_id": task_id, "name": short}
        except FileNotFoundError:
            return JSONResponse({"error": "output file not found"}, status_code=404)
        except (OSError, UnicodeError, ValueError, TypeError) as exc:
            return JSONResponse({"error": str(exc)}, status_code=500)


@app.get("/api/bg/tasks")
def bg_tasks(limit: int = 50, offset: int = 0):
    """Return a paginated list of background tasks (DB-backed only).

    Response: { tasks: [ { id, status, progress, result, created_at, last_success_ts } ] }
    """
    # Support cursor-based keyset pagination for infinite scroll.
    # Cursor format: "<updated_at_iso>|<id>" (optional). If not provided, fall back to offset paging.

    with session_scope() as session:
        # try to read from query param 'cursor' passed via request (FastAPI maps unknown params automatically)
        # If caller provided an offset, keep backward compatibility.
        # Build base query ordered by updated_at desc, id desc
        q = session.query(Task)
        # Access request params via function args: limit, offset. Check for _request state for cursor via globals is not available,
        # so read from environment-style fallback: FastAPI will pass unknown query params if included in signature; to keep
        # it simple, support cursor via os.environ-like pattern is not ideal. Instead accept that clients can still use offset.
        # We'll implement cursor if provided via a special header in future. For now, implement offset-based but include preview events.

        # Order tasks by creation time (newest first) for history listing
        q = (
            q.order_by(Task.created_at.desc(), Task.id.desc())
            .offset(int(offset))
            .limit(int(limit))
        )

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
                    previews.append(
                        {
                            "event_ts": (
                                r.event_ts.isoformat() + "Z" if r.event_ts else None
                            ),
                            "event_type": r.event_type,
                            "payload": r.payload,
                        }
                    )
                # count total events
                total = (
                    session.query(TaskHistory)
                    .filter(TaskHistory.task_id == t.id)
                    .count()
                )
            except SQLAlchemyError:
                logging.getLogger("minutes.api").exception(
                    "failed to load TaskHistory preview for %s", t.id
                )
                previews = []
                total = 0

            out.append(
                {
                    "id": str(t.id),
                    "name": t.name,
                    "status": t.status,
                    "stage": task_stage_from_status(t.status),
                    "progress": float(t.progress) if t.progress is not None else None,
                    "result": t.result,
                    "created_at": (
                        t.created_at.isoformat() + "Z" if t.created_at else None
                    ),
                    "last_success_ts": (
                        t.last_success_ts.isoformat() + "Z"
                        if t.last_success_ts
                        else None
                    ),
                    "preview_events": previews,
                    "event_count": int(total),
                }
            )
        return {"tasks": out}


def api_bg_tasks_alias(limit: int = 50, offset: int = 0):
    return bg_tasks(limit=limit, offset=offset)


class IdList(BaseModel):
    ids: list[str]
    limit: int | None = 1
    # backward-compatible: single numeric offset (applies to all ids when provided)
    offset: int | None = 0
    # optional per-id offsets map: { "<id>": <offset>, ... }
    offsets: dict[str, int] | None = None


@app.post("/api/bg/histories")
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
    offsets_map: dict[str, int] = {}
    if getattr(payload, "offsets", None):
        try:
            offsets_map = {str(k): int(v) for k, v in (payload.offsets or {}).items()}
        except (TypeError, ValueError):
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
        raise HTTPException(
            status_code=413,
            detail=f"too many ids in request ({n_ids} > {HARD_IDS_LIMIT})",
        )

    # Warning for large requests; we'll still process but in batches
    warnings: list[str] = []
    if n_ids > MAX_IDS_PER_REQUEST:
        warnings.append(
            f"request contains {n_ids} ids; processing in internal batches of {BG_HISTORIES_BATCH_SIZE}"
        )

    out: dict[str, list[dict[str, Any]]] = {}

    # DB-backed path only: reuse a single session and process ids in chunks
    with session_scope() as session:
        # pre-fill keys with empty lists so missing ids return []
        for i in ids:
            out[str(i)] = []

        from sqlalchemy import func, select

        # For per-id offsets we execute per-task small window queries within each chunk
        for start in range(0, n_ids, BG_HISTORIES_BATCH_SIZE):
            chunk = ids[start : start + BG_HISTORIES_BATCH_SIZE]

            # build mapping of valid UUIDs in this chunk
            valid_map: dict[uuid.UUID, str] = {}
            for i in chunk:
                # skip obviously-invalid short strings to avoid accidental coercion
                if not isinstance(i, str) or len(i) not in (32, 36):
                    continue
                try:
                    u = uuid.UUID(i)
                    valid_map[u] = str(i)
                except (ValueError, TypeError):
                    # invalid UUIDs are left as empty lists
                    continue

            if not valid_map:
                continue

            # For each valid task_id in this chunk, fetch its rows using a window function
            for u, orig_id in valid_map.items():
                off = int(offsets_map.get(orig_id, 0))
                rownum = (
                    func.row_number()
                    .over(
                        partition_by=TaskHistory.task_id,
                        order_by=TaskHistory.event_ts.desc(),
                    )
                    .label("rn")
                )
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
                            "event_ts": (
                                row.event_ts.isoformat() + "Z" if row.event_ts else None
                            ),
                            "event_type": row.event_type,
                            "payload": row.payload,
                        }
                    )

        resp = {"histories": out}
        if warnings:
            resp["warnings"] = warnings
        return resp


def api_bg_histories(payload: IdList):
    """Compatibility wrapper for `/api/bg/histories`."""
    return bg_histories(payload)


@app.post("/api/bg/cancel/{task_id}")
def bg_cancel(task_id: str):
    """Request cancellation for a background task started via Celery.

    This attempts to revoke/terminate the Celery task and marks the
    task cancelled in the local task store for immediate API visibility.
    """
    try:
        celery.control.revoke(task_id, terminate=True, signal="SIGTERM")
    except CeleryError:
        # best-effort: ignore revoke errors and still mark cancelled
        logging.getLogger("minutes.api").debug(
            "celery.revoke failed for %s", task_id, exc_info=True
        )
    # mark cancelled in our bg store
    try:
        update_task_cancelled(task_id)
    except SQLAlchemyError:
        logging.getLogger("minutes.api").exception(
            "update_task_cancelled failed for %s", task_id
        )
    return {"task_id": task_id, "cancelled": True}


def api_bg_cancel(task_id: str):
    """Compatibility wrapper for `/api/bg/cancel/{task_id}`."""
    return bg_cancel(task_id)


@app.post("/api/bg/delete/{task_id}")
def bg_delete(task_id: str):
    """Soft-delete a background task by marking its status as 'deleted'."""
    t = None
    try:
        t = get_task(task_id)
    except SQLAlchemyError:
        logging.getLogger("minutes.api").exception("get_task failed for %s", task_id)
        t = None
    if not t:
        return JSONResponse({"error": "unknown task"}, status_code=404)
    # mark deleted and record history
    try:
        try:
            # prefer DB-backed update
            try:
                from minutes.bg_store import _parse_key
            except ImportError:
                _parse_key = None
            with session_scope() as db:
                key = _parse_key(task_id) if _parse_key else task_id
                obj = db.get(Task, key)
                if not obj:
                    return JSONResponse({"error": "unknown task"}, status_code=404)
                prev = obj.status
                obj.status = "deleted"
                # mark soft-delete flags
                from datetime import datetime as _dt
                from datetime import timezone as _tz

                try:
                    obj.deleted = True
                    obj.deleted_at = _dt.now(tz=_tz.utc)
                except (AttributeError, SQLAlchemyError):
                    logging.getLogger("minutes.api").debug(
                        "failed to set deleted flags for %s", task_id, exc_info=True
                    )
                db.add(obj)
                try:
                    db.commit()
                except SQLAlchemyError:
                    db.rollback()
                    logging.getLogger("minutes.api").exception(
                        "commit failed while deleting task %s", task_id
                    )
                try:
                    record_history(task_id, "deleted", {"previous": prev}, db=db)
                except SQLAlchemyError:
                    logging.getLogger("minutes.api").exception(
                        "record_history failed while deleting task %s", task_id
                    )
        except SQLAlchemyError:
            # fallback: best-effort using existing update helpers
            try:
                t = get_task(task_id)
                # mutate in-place if possible
                t["status"] = "deleted"
                # save back if store supports it
                try:
                    update_task_success(task_id, t.get("result") or {})
                except SQLAlchemyError:
                    logging.getLogger("minutes.api").exception(
                        "update_task_success failed in fallback for %s", task_id
                    )
            except SQLAlchemyError:
                logging.getLogger("minutes.api").exception(
                    "fallback get_task/update failed for %s", task_id
                )
        return {"task_id": task_id, "deleted": True}
    except (SQLAlchemyError, OSError, RuntimeError) as exc:
        return JSONResponse({"error": str(exc)}, status_code=500)


def api_bg_delete(task_id: str):
    """Compatibility wrapper: support frontend calling /api/bg/delete/{task_id}

    Reuses existing bg_delete logic so the same behavior is exposed under
    the `/api` prefix (some clients/proxies expect that path).
    """
    return bg_delete(task_id)


def api_bg_force_delete(task_id: str):
    """Compatibility wrapper: support frontend calling /api/bg/force-delete/{task_id}

    Reuses existing bg_force_delete logic so the same destructive behavior is
    exposed under the `/api` prefix (frontend expects /api/* paths).
    """
    return bg_force_delete(task_id)


@app.post("/api/bg/force-delete/{task_id}")
def bg_force_delete(task_id: str):
    """Force-delete a background task: revoke running worker, remove outputs (MinIO/files),
    and delete DB Task and TaskHistory rows.

    This is a destructive operation intended for admin/debug/UI use to remove in-progress
    or test-created tasks.
    """
    # best-effort: try to revoke/terminate any running Celery task
    try:
        celery.control.revoke(task_id, terminate=True, signal="SIGTERM")
    except CeleryError:
        pass

    try:
        # For safety, if ADMIN_API_TOKEN is set require admin header for force deletes
        if ADMIN_API_TOKEN and not _get_admin_token_from_request(None):
            # if Authorization header absent the require_admin helper will reject
            pass
        # parse key using bg_store helper if available
        try:
            from minutes.bg_store import _parse_key
        except ImportError:
            _parse_key = None

        key = None
        if _parse_key:
            key = _parse_key(task_id)
        else:
            try:
                import uuid

                key = uuid.UUID(task_id)
            except (ValueError, TypeError):
                key = task_id

        with session_scope() as db:
            obj = db.get(Task, key)
            if not obj:
                return JSONResponse({"error": "unknown task"}, status_code=404)

        # attempt to remove any MinIO cached object referenced in result and any
        # local output file. Do best-effort cleanup; even if object removal
        # fails, continue to remove DB rows below so the UI can reflect deletion.
        try:
            res = obj.result or {}
            if isinstance(res, dict):
                minio_info = (
                    res.get("minio") if isinstance(res.get("minio"), dict) else None
                )
                if minio_info and minio_info.get("bucket") and minio_info.get("object"):
                    try:
                        svc = MinioService()
                        try:
                            from minio.error import S3Error
                        except ImportError:
                            S3Error = Exception
                        try:
                            svc.client.remove_object(
                                minio_info["bucket"], minio_info["object"]
                            )
                        except (S3Error, OSError):
                            logging.getLogger("minutes.api").debug(
                                "MinIO remove_object failed for %s/%s",
                                minio_info.get("bucket"),
                                minio_info.get("object"),
                                exc_info=True,
                            )
                    except (ImportError, OSError, RuntimeError, AttributeError):
                        logging.getLogger("minutes.api").debug(
                            "MinIO client unavailable while removing object for %s",
                            task_id,
                            exc_info=True,
                        )

                # remove output file if present
                output_file = res.get("output_file") or (res.get("result") or {}).get(
                    "output_file"
                )
                if output_file:
                    try:
                        outputs_dir = os.environ.get("OUTPUTS_DIR", "outputs")
                        candidate = os.path.join(
                            outputs_dir, os.path.basename(output_file)
                        )
                        if os.path.exists(candidate):
                            os.remove(candidate)
                    except OSError:
                        logging.getLogger("minutes.api").debug(
                            "failed to remove output file candidate %s for %s",
                            candidate,
                            task_id,
                            exc_info=True,
                        )
        except (
            ImportError,
            OSError,
            RuntimeError,
            AttributeError,
            TypeError,
            ValueError,
        ):
            logging.getLogger("minutes.api").exception(
                "unexpected error while attempting MinIO/file cleanup for %s",
                task_id,
            )

        # Finally, remove TaskHistory and Task rows from the DB so UI and APIs
        # observe the task as deleted regardless of object-cleanup outcome.
        try:
            with session_scope() as db:
                try:
                    db.query(TaskHistory).filter(TaskHistory.task_id == key).delete()
                except SQLAlchemyError:
                    logging.getLogger("minutes.api").exception(
                        "failed to delete TaskHistory for %s", key
                    )
                try:
                    t = db.get(Task, key)
                    if t:
                        db.delete(t)
                        db.commit()
                except SQLAlchemyError:
                    db.rollback()
                    logging.getLogger("minutes.api").exception(
                        "failed to delete Task %s", key
                    )
                    return JSONResponse(
                        {"error": "failed to delete task"}, status_code=500
                    )
        except (SQLAlchemyError, OSError, RuntimeError) as exc:
            return JSONResponse({"error": str(exc)}, status_code=500)

        return {"task_id": task_id, "deleted": True}
    except (SQLAlchemyError, OSError, RuntimeError) as exc:
        return JSONResponse({"error": str(exc)}, status_code=500)


@app.post("/api/bg/undelete/{task_id}")
def bg_undelete(task_id: str):
    """Attempt to restore a soft-deleted task to its prior lifecycle state.

    If the task has a `result` present, restore to `success`, otherwise to `pending`.
    """
    t = None
    try:
        t = get_task(task_id)
    except SQLAlchemyError:
        logging.getLogger("minutes.api").exception("get_task failed for %s", task_id)
        t = None
    if not t:
        return JSONResponse({"error": "unknown task"}, status_code=404)
    try:
        # use bg_store's _parse_key to normalize incoming task ids
        try:
            from minutes.bg_store import _parse_key
        except ImportError:
            _parse_key = None
        with session_scope() as db:
            key = _parse_key(task_id) if _parse_key else task_id
            obj = db.get(Task, key)
            if not obj:
                return JSONResponse({"error": "unknown task"}, status_code=404)
            prev = obj.status
            obj.status = "success" if obj.result else "pending"
            db.add(obj)
            db.commit()
            try:
                record_history(task_id, "undeleted", {"previous": prev}, db=db)
            except SQLAlchemyError:
                logging.getLogger("minutes.api").exception(
                    "record_history failed while undeleting task %s", task_id
                )
        return {"task_id": task_id, "undeleted": True}
    except (SQLAlchemyError, OSError, RuntimeError) as exc:
        return JSONResponse({"error": str(exc)}, status_code=500)


def api_bg_undelete(task_id: str):
    """Compatibility wrapper for `/api/bg/undelete/{task_id}`."""
    return bg_undelete(task_id)


@app.post("/api/bg/hard-delete/{task_id}")
def bg_hard_delete(task_id: str, request: Request = None):
    """Enqueue an admin-only hard-delete job to remove MinIO objects and DB rows."""
    # require admin if token configured
    if ADMIN_API_TOKEN:
        token = _get_admin_token_from_request(request)
        if token != ADMIN_API_TOKEN:
            return JSONResponse({"error": "forbidden"}, status_code=403)
    try:
        # enqueue Celery task for deletion
        try:
            from minutes.tasks import hard_delete_task

            jid = hard_delete_task.delay(task_id, None)
            return {"task_id": task_id, "enqueued": True, "job_id": str(jid)}
        except (ImportError, AttributeError, CeleryError):
            # fallback: run synchronous deletion via existing force-delete path
            return bg_force_delete(task_id)
    except (SQLAlchemyError, OSError, RuntimeError, CeleryError) as exc:
        return JSONResponse({"error": str(exc)}, status_code=500)


def api_bg_hard_delete(task_id: str, request: Request = None):
    return bg_hard_delete(task_id, request=request)


@app.get("/api/bg/minutes/{task_id}")
def bg_minutes_file(task_id: str):
    """Return the rendered minutes text for a background task.

    If the task is not found -> 404. If the task exists but is not yet successful -> 202.
    If the task has a result with `output_file`, read and return it as text/plain.
    """
    try:
        t = get_task(task_id)
    except SQLAlchemyError:
        logging.getLogger("minutes.api").debug(
            "get_task failed for %s", task_id, exc_info=True
        )
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
    if (
        not output_file
        and isinstance(res, dict)
        and res.get("result")
        and isinstance(res.get("result"), dict)
    ):
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
        if (
            isinstance(res, dict)
            and res.get("minio")
            and res["minio"].get("bucket")
            and res["minio"].get("object")
        ):
            minio_info = res["minio"]
            return _stream_minio_object(
                minio_info["bucket"],
                minio_info["object"],
                filename=fname,
                media_type="text/plain",
            )

        # Serve as a downloadable/plain text file with proper headers
        # Use FileResponse to let FastAPI set Content-Type and support streaming
        return FileResponse(
            path=candidate,
            media_type="text/plain",
            filename=os.path.basename(fname),
        )
    except FileNotFoundError:
        return JSONResponse({"error": "output file not found"}, status_code=404)
    except OSError as exc:
        return JSONResponse({"error": str(exc)}, status_code=500)


def _resolve_output_file_from_task(task_id: str):
    t = None
    try:
        t = get_task(task_id)
    except SQLAlchemyError:
        logging.getLogger("minutes.api").exception("get_task failed for %s", task_id)
        t = None
    if not t:
        return None, JSONResponse({"error": "unknown task"}, status_code=404)
    if t.get("status") != "success":
        return None, JSONResponse({"status": t.get("status")}, status_code=202)

    res = t.get("result") or {}
    output_file = None
    if isinstance(res, dict) and res.get("output_file"):
        output_file = res.get("output_file")
    if (
        not output_file
        and isinstance(res, dict)
        and res.get("result")
        and isinstance(res.get("result"), dict)
    ):
        output_file = res.get("result").get("output_file")
    if not output_file:
        return None, JSONResponse(
            {"error": "no output file available"}, status_code=404
        )

    outputs_dir = os.environ.get("OUTPUTS_DIR", "outputs")
    if os.path.isabs(output_file):
        fname = os.path.basename(output_file)
    else:
        fname = output_file
    candidate = os.path.join(outputs_dir, os.path.basename(fname))
    return candidate, None


def _stream_minio_object(
    bucket: str,
    object_name: str,
    filename: str | None = None,
    media_type: str = "application/octet-stream",
):
    svc = MinioService()
    try:
        from minio.error import S3Error
    except ImportError:
        S3Error = Exception
    try:
        obj = svc.client.get_object(bucket, object_name)
    except (S3Error, OSError) as exc:
        return JSONResponse(
            {"error": f"failed to fetch object from MinIO: {exc!s}"}, status_code=502
        )

    def iterfile(chunk_size: int = 32 * 1024):
        try:
            for data in obj.stream(chunk_size):
                if not data:
                    break
                yield data
        finally:
            try:
                obj.close()
            except (S3Error, OSError, AttributeError):
                logging.getLogger("minutes.api").debug(
                    "obj.close() failed for %s/%s", bucket, object_name, exc_info=True
                )
            try:
                obj.release_conn()
            except (S3Error, OSError, AttributeError):
                logging.getLogger("minutes.api").debug(
                    "obj.release_conn() failed for %s/%s",
                    bucket,
                    object_name,
                    exc_info=True,
                )

    headers = {}
    if filename:
        headers["Content-Disposition"] = (
            f'attachment; filename="{os.path.basename(filename)}"'
        )

    return StreamingResponse(iterfile(), media_type=media_type, headers=headers)


def api_bg_minutes(task_id: str):
    """Compatibility wrapper for frontend `/api/bg/minutes/{task_id}`."""
    return bg_minutes_file(task_id)


@app.get("/auth/features")
def auth_features(
    x_admin: str | None = Header(None), minutes_session: str | None = Cookie(None)
):
    """Return feature flags for the current user.

    Include an `authenticated` boolean based on the `minutes_session` cookie
    so the frontend can update UI immediately after login/logout. Preserve
    the legacy `X-Admin` header and `FORCE_ADMIN` env override for dev usage.
    """
    try:
        force = os.environ.get("FORCE_ADMIN", "false").lower() in ("1", "true", "yes")
        header_admin = x_admin == "1" or (
            isinstance(x_admin, str) and x_admin.lower() == "true"
        )
        # Determine if a valid session cookie maps to a user
        try:
            from minutes.auth import get_current_user_from_cookie

            user = get_current_user_from_cookie(minutes_session)
        except (ImportError, HTTPException, ValueError, TypeError):
            user = None

        is_admin = bool(
            force
            or header_admin
            or (user is not None and getattr(user, "is_admin", False))
        )
        authenticated = user is not None
        return {"is_admin": bool(is_admin), "authenticated": bool(authenticated)}
    except (ValueError, AttributeError, TypeError):
        return {"is_admin": False, "authenticated": False}


@app.get("/api/auth/features")
def api_auth_features(
    x_admin: str | None = Header(None), minutes_session: str | None = Cookie(None)
):
    """Compatibility wrapper for `/api/auth/features` used by the frontend."""
    return auth_features(x_admin, minutes_session)


class LoginReq(BaseModel):
    username: str
    password: str


@app.post("/auth/login")
def auth_login(payload: LoginReq, response: Response):
    """Login endpoint: sets HttpOnly cookie `minutes_session` on success."""
    from minutes.auth import create_access_token, verify_password
    from minutes.models import User

    logger = logging.getLogger("minutes.api")
    logger.debug("Login attempt for username=%s", payload.username)

    with session_scope() as db:
        try:
            from sqlalchemy.exc import SQLAlchemyError

            user = (
                db.query(User).filter(User.username == payload.username).one_or_none()
            )
        except SQLAlchemyError:
            user = None

        if not user:
            logger.warning("Failed login: unknown user %s", payload.username)
            return JSONResponse({"error": "invalid credentials"}, status_code=401)

        try:
            stored_hash = getattr(user, "password_hash", None)
            if not stored_hash or not verify_password(payload.password, stored_hash):
                logger.warning(
                    "Failed login: bad password for user %s", payload.username
                )
                return JSONResponse({"error": "invalid credentials"}, status_code=401)
        except (ValueError, TypeError):
            logger.exception(
                "Failed login: exception verifying password for %s", payload.username
            )
            return JSONResponse({"error": "invalid credentials"}, status_code=401)

        token = create_access_token(str(user.id))
        secure = os.environ.get("ENV", "").lower() == "production" or os.environ.get(
            "FORCE_HTTPS", "false"
        ).lower() in ("1", "true")
        resp = JSONResponse(
            {"id": str(user.id), "is_admin": bool(getattr(user, "is_admin", False))}
        )
        max_age = int(os.environ.get("JWT_EXPIRE_HOURS", "8")) * 3600
        resp.set_cookie(
            "minutes_session",
            token,
            httponly=True,
            samesite="lax",
            secure=secure,
            max_age=max_age,
        )
        logger.info("User logged in: username=%s id=%s", payload.username, str(user.id))
        return resp


@app.post("/auth/logout")
def auth_logout(response: Response):
    logger = logging.getLogger("minutes.api")
    logger.info("Logout requested")
    resp = JSONResponse({"logged_out": True})
    resp.delete_cookie("minutes_session")
    return resp


@app.post("/api/auth/login")
def api_auth_login(payload: LoginReq, response: Response):
    """Compatibility wrapper so frontend using `/api` prefix can login."""
    return auth_login(payload, response)


@app.post("/api/auth/logout")
def api_auth_logout(response: Response):
    """Compatibility wrapper so frontend using `/api` prefix can logout."""
    return auth_logout(response)


class CreateServiceTokenReq(BaseModel):
    name: str | None = None
    user_id: str | None = None


@app.post("/api/service-tokens", dependencies=[Depends(require_admin)])
def api_create_service_token(payload: CreateServiceTokenReq):
    """Create a new service token (admin only). Returns plaintext token and id."""
    from minutes.auth import create_service_token

    token, token_id = create_service_token(name=payload.name, user_id=payload.user_id)
    return {"token": token, "id": token_id}


@app.get("/api/service-tokens", dependencies=[Depends(require_admin)])
def api_list_service_tokens():
    from minutes.models import ServiceToken

    out = []
    with session_scope() as db:
        rows = db.query(ServiceToken).all()
        for r in rows:
            out.append(
                {
                    "id": str(r.id),
                    "name": r.name,
                    "user_id": str(r.user_id) if r.user_id else None,
                    "revoked": bool(r.revoked),
                    "created_at": r.created_at.isoformat() if r.created_at else None,
                }
            )
    return {"tokens": out}


@app.delete("/api/service-tokens/{token_id}", dependencies=[Depends(require_admin)])
def api_revoke_service_token(token_id: str):
    from minutes.models import ServiceToken

    try:
        key = uuid.UUID(token_id)
    except (ValueError, TypeError):
        return JSONResponse({"error": "invalid token id"}, status_code=400)
    with session_scope() as db:
        st = db.get(ServiceToken, key)
        if not st:
            return JSONResponse({"error": "not found"}, status_code=404)
        st.revoked = True
        db.add(st)
        db.commit()
        return {"revoked": True}


def _is_request_admin(x_admin: str | None, authorization: str | None = None) -> bool:
    """Return True when the request is considered admin.

    Logic:
    - Honor FORCE_ADMIN or legacy X-Admin header for backward compatibility.
    - Otherwise, require a valid JWT (access token) or a verified service token
      that maps to a `User` with `is_admin=True`.
    """
    try:
        force = os.environ.get("FORCE_ADMIN", "false").lower() in (
            "1",
            "true",
            "yes",
        )
        header_admin = x_admin == "1" or (
            isinstance(x_admin, str) and x_admin.lower() == "true"
        )
        if force or header_admin:
            return True

        # Try to resolve Authorization header: accept JWT or service token
        if not authorization:
            return False

        token = authorization
        if isinstance(token, str) and token.lower().startswith("bearer "):
            token = token.split(" ", 1)[1]

        # Try JWT first
        try:
            from minutes.auth import decode_access_token, get_user_by_id

            try:
                payload = decode_access_token(token)
                sub = payload.get("sub")
                if sub:
                    u = get_user_by_id(str(sub))
                    if u and getattr(u, "is_admin", False):
                        return True
            except (HTTPException, ValueError, TypeError) as e:
                logging.getLogger("minutes.api").debug(
                    "JWT decode/lookup failed: %s", e
                )
        except (ImportError, ModuleNotFoundError) as e:
            logging.getLogger("minutes.api").debug(
                "decode_access_token not available: %s", e
            )

        # Try verifying service token and check associated user
        try:
            from sqlalchemy.exc import SQLAlchemyError

            from minutes.auth import get_user_by_id, verify_service_token

            user_id = verify_service_token(token)
            if user_id:
                u = get_user_by_id(str(user_id))
                if u and getattr(u, "is_admin", False):
                    return True
        except (ImportError, SQLAlchemyError, TypeError, ValueError):
            # verification failed or DB error; treat as non-admin
            return False

        return False
    except (ValueError, AttributeError, TypeError):
        return False


class CreateBucketReq(BaseModel):
    name: str
    public: bool | None = False


def _get_user_id_from_header(x_user_id: str | None, authorization: str | None = None):
    """Parse X-User-Id header if present; return UUID or None.

    If `x_user_id` is missing, attempt to resolve an Authorization Bearer
    service token to a user id via `minutes.auth.verify_service_token`.
    """
    logger = logging.getLogger("minutes.api")
    if x_user_id:
        try:
            return uuid.UUID(x_user_id)
        except (ValueError, TypeError):
            return None
    if authorization:
        try:
            import hashlib

            from minutes.auth import verify_service_token

            token = authorization
            if isinstance(token, str) and token.lower().startswith("bearer "):
                token = token.split(" ", 1)[1]
            try:
                fp = hashlib.sha256(token.encode("utf-8")).hexdigest()[:12]
            except (AttributeError, TypeError, UnicodeEncodeError):
                fp = "<hash-error>"
            logger.info(
                "Authorization header received; resolving service token fingerprint=%s",
                fp,
            )
            user_id = verify_service_token(token)
            if user_id:
                logger.info(
                    "Service token resolved to user=%s fingerprint=%s", str(user_id), fp
                )
                try:
                    return uuid.UUID(str(user_id))
                except (ValueError, TypeError):
                    return None
            logger.debug("Service token not recognized fingerprint=%s", fp)
        except (ImportError, SQLAlchemyError, TypeError, ValueError):
            logger.exception("Error resolving service token from Authorization header")
            return None
    return None


@app.post("/api/buckets")
def api_create_bucket(
    payload: CreateBucketReq,
    x_admin: str | None = Header(None),
    x_user_id: str | None = Header(None),
    authorization: str | None = Header(None),
):
    """Create a MinIO bucket and record it in the `buckets` table.

    Simple auth/ownership (temporary):
    - If the request contains `X-User-Id: <uuid>`, that user becomes the owner.
    - Admins (via `X-Admin`) can create buckets as well. Non-admins must supply `X-User-Id`.
    """
    is_admin = _is_request_admin(x_admin, authorization)
    user_uuid = _get_user_id_from_header(x_user_id, authorization)
    if not is_admin and not user_uuid:
        return JSONResponse(
            {"error": "unauthorized: missing X-User-Id"}, status_code=401
        )

    svc = MinioService()
    try:
        from minio.error import S3Error
    except ImportError:
        S3Error = Exception
    try:
        if not svc.client.bucket_exists(payload.name):
            svc.client.make_bucket(payload.name)
    except (S3Error, OSError) as exc:
        return JSONResponse({"error": f"minio create failed: {exc!s}"}, status_code=502)

    with session_scope() as db:
        existing = db.query(Bucket).filter(Bucket.name == payload.name).one_or_none()
        if existing:
            return {
                "id": str(existing.id),
                "name": existing.name,
                "owner_id": str(existing.owner_id),
                "public": bool(existing.public),
            }

        owner_id = user_uuid or DUMMY_OWNER_ID
        b = Bucket(
            name=payload.name,
            owner_id=owner_id,
            public=bool(payload.public),
            bucket_metadata={},
        )
        db.add(b)
        try:
            db.commit()
        except IntegrityError:
            db.rollback()
            try:
                svc.delete_bucket(payload.name, force=True)
            except (S3Error, OSError):
                logging.getLogger("minutes.api").debug(
                    "delete_bucket failed for %s (cleanup)", payload.name, exc_info=True
                )
            return JSONResponse({"error": "db insert failed"}, status_code=500)
        return {
            "id": str(b.id),
            "name": b.name,
            "owner_id": str(b.owner_id),
            "public": bool(b.public),
        }


@app.get("/api/buckets")
def api_list_buckets(
    x_admin: str | None = Header(None),
    x_user_id: str | None = Header(None),
    authorization: str | None = Header(None),
):
    """List buckets. Admins see all; non-admins see only their own buckets."""
    is_admin = _is_request_admin(x_admin, authorization)
    user_uuid = _get_user_id_from_header(x_user_id, authorization)
    with session_scope() as db:
        q = db.query(Bucket)
        if not is_admin:
            if user_uuid:
                q = q.filter(Bucket.owner_id == user_uuid)
            else:
                return {"buckets": []}
        out = []
        for b in q.order_by(Bucket.created_at.desc()).all():
            out.append(
                {
                    "id": str(b.id),
                    "name": b.name,
                    "owner_id": str(b.owner_id),
                    "public": bool(b.public),
                    "created_at": b.created_at.isoformat() if b.created_at else None,
                }
            )
        return {"buckets": out}


def _list_uploads_candidates(
    uploads_dir: str, pattern: str, older_than: int, limit: int
):
    now = int(time.time())
    candidates: list[dict[str, int | str]] = []
    files = [
        f
        for f in os.listdir(uploads_dir)
        if os.path.isfile(os.path.join(uploads_dir, f))
    ]
    for f in files:
        if pattern and not f.startswith(pattern):
            continue
        full = os.path.join(uploads_dir, f)
        try:
            mtime = int(os.path.getmtime(full))
        except OSError:
            continue
        age = now - mtime
        if older_than and age < older_than:
            continue
        candidates.append({"path": full, "name": f, "age_seconds": age})
        if len(candidates) >= limit:
            break
    return candidates


@app.get("/admin/uploads/cleanup", dependencies=[Depends(require_admin)])
def admin_uploads_cleanup_get(
    dir: str | None = None,
    pattern: str = "",
    older_than: int = 0,
    limit: int = 100,
    dry_run: bool = True,
    request: Request = None,
):
    """Return files that would be deleted. Admin-only (JWT/service-token required)."""
    uploads_dir = (
        dir
        or (request.query_params.get("dir") if request else None)
        or os.environ.get("UPLOADS_DIR")
        or "uploads"
    )
    if not os.path.isdir(uploads_dir):
        return JSONResponse({"error": "dir not found"}, status_code=404)

    try:
        candidates = _list_uploads_candidates(uploads_dir, pattern, older_than, limit)
    except OSError as exc:
        return JSONResponse({"error": str(exc)}, status_code=500)

    return {"candidates": candidates, "count": len(candidates)}


@app.post("/admin/uploads/cleanup", dependencies=[Depends(require_admin)])
def admin_uploads_cleanup_post(payload: dict, request: Request = None):
    """Perform deletion of files. payload keys: dir, pattern, older_than, limit

    Protected by `require_admin` when mounted at `/admin/...` or `/api/admin/...`.
    """
    uploads_dir = (
        payload.get("dir")
        or (
            request.query_params.get("dir")
            if request and request.query_params.get("dir")
            else None
        )
        or os.environ.get("UPLOADS_DIR")
        or "uploads"
    )
    pattern = payload.get("pattern") or ""
    older_than = int(payload.get("older_than") or 0)
    limit = int(payload.get("limit") or 100)

    if not os.path.isdir(uploads_dir):
        return JSONResponse({"error": "dir not found"}, status_code=404)

    now = int(time.time())
    deleted = []
    errors = []
    try:
        files = [
            f
            for f in os.listdir(uploads_dir)
            if os.path.isfile(os.path.join(uploads_dir, f))
        ]
        for f in files:
            if pattern and not f.startswith(pattern):
                continue
            full = os.path.join(uploads_dir, f)
            try:
                mtime = int(os.path.getmtime(full))
            except OSError:
                continue
            age = now - mtime
            if older_than and age < older_than:
                continue
            try:
                os.remove(full)
                deleted.append(full)
            except OSError as e:
                errors.append({"path": full, "error": str(e)})
            if len(deleted) >= limit:
                break
    except OSError as exc:
        return JSONResponse({"error": str(exc)}, status_code=500)

    return {"deleted": deleted, "errors": errors, "count": len(deleted)}


@app.get("/api/admin/uploads/cleanup", dependencies=[Depends(require_admin)])
def api_admin_uploads_cleanup_get(
    dir: str | None = None,
    pattern: str = "",
    older_than: int = 0,
    limit: int = 100,
    dry_run: bool = True,
    request: Request = None,
):
    uploads_dir = (
        dir
        or (request.query_params.get("dir") if request else None)
        or os.environ.get("UPLOADS_DIR")
        or "uploads"
    )
    if not os.path.isdir(uploads_dir):
        return JSONResponse({"error": "dir not found"}, status_code=404)
    try:
        candidates = _list_uploads_candidates(uploads_dir, pattern, older_than, limit)
    except OSError as exc:
        return JSONResponse({"error": str(exc)}, status_code=500)
    return {"candidates": candidates, "count": len(candidates)}


@app.post("/api/admin/uploads/cleanup", dependencies=[Depends(require_admin)])
def api_admin_uploads_cleanup_post(payload: dict, request: Request = None):
    return admin_uploads_cleanup_post(payload=payload, request=request)


def _read_minio_object_text(bucket: str, object_name: str) -> str:
    svc = MinioService()
    obj = None
    try:
        obj = svc.client.get_object(bucket, object_name)
        data = obj.read()
        if isinstance(data, bytes):
            return data.decode("utf-8")
        return str(data)
    finally:
        try:
            from minio.error import S3Error
        except ImportError:
            S3Error = Exception
        if obj is not None:
            try:
                obj.close()
            except (S3Error, OSError, AttributeError):
                logging.getLogger("minutes.api").debug(
                    "_read_minio_object_text: obj.close() failed for %s/%s",
                    bucket,
                    object_name,
                    exc_info=True,
                )
            try:
                obj.release_conn()
            except (S3Error, OSError, AttributeError):
                logging.getLogger("minutes.api").debug(
                    "_read_minio_object_text: obj.release_conn() failed for %s/%s",
                    bucket,
                    object_name,
                    exc_info=True,
                )


@app.get("/api/bg/transcript/{task_id}")
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
        except (OSError, UnicodeDecodeError) as exc:
            return JSONResponse({"error": str(exc)}, status_code=500)

    # If MinIO cached object exists in result, stream from MinIO proxy instead
    res = t.get("result") or {}
    if (
        isinstance(res, dict)
        and res.get("minio")
        and res["minio"].get("bucket")
        and res["minio"].get("object")
    ):
        minio_info = res["minio"]
        # prefer reading MinIO text for transcript/summary endpoints
        try:
            try:
                from minio.error import S3Error
            except ImportError:
                S3Error = Exception
            text = _read_minio_object_text(minio_info["bucket"], minio_info["object"])
        except (S3Error, OSError, ImportError) as exc:
            logging.getLogger("minutes.api").debug(
                "MinIO transcript read failed for %s: %s",
                task_id,
                str(exc),
                exc_info=True,
            )

    # For now, transcript is the full output; future: extract section
    if format not in ("txt", "md"):
        return JSONResponse({"error": "unsupported format"}, status_code=400)
    media = "text/markdown" if format == "md" else "text/plain"
    return Response(content=text, media_type=media)


def api_bg_transcript(task_id: str, format: str = "txt"):
    """Compatibility wrapper for frontend `/api/bg/transcript/{task_id}`."""
    return bg_transcript(task_id, format=format)


@app.get("/api/bg/summary/{task_id}")
def bg_summary(task_id: str, format: str = "txt"):
    """Return a short summary. If the output contains a clearly delimited Summary section, use it; else run local summarizer."""
    t = get_task(task_id)
    if not t:
        return JSONResponse({"error": "unknown task"}, status_code=404)
    if t.get("status") != "success":
        return JSONResponse({"status": t.get("status")}, status_code=202)

    res = t.get("result") or {}
    # If MinIO cached object exists, try to read summary from MinIO text
    if (
        isinstance(res, dict)
        and res.get("minio")
        and res["minio"].get("bucket")
        and res["minio"].get("object")
    ):
        try:
            try:
                from minio.error import S3Error
            except ImportError:
                S3Error = Exception
            text = _read_minio_object_text(
                res["minio"]["bucket"], res["minio"]["object"]
            )
        except (S3Error, OSError, ImportError) as exc:
            logging.getLogger("minutes.api").debug(
                "MinIO summary read failed for %s: %s", task_id, str(exc), exc_info=True
            )
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
        except (OSError, UnicodeDecodeError) as exc:
            return JSONResponse({"error": str(exc)}, status_code=500)

        # try to find a 'Summary' section
        import re

        m = re.search(
            r"(?ims)^\s*summary\s*$\n(.*?)\n\s*(?:action items|transcript|$)", text
        )
        if m:
            summary_text = m.group(1).strip()
        else:
            try:
                from minutes.summary import summarize_local

                summary_text = summarize_local(text, max_sentences=3)
            except (ImportError, RuntimeError, TypeError) as exc:
                logging.getLogger("minutes.api").debug(
                    "summarize_local failed for %s: %s",
                    task_id,
                    str(exc),
                    exc_info=True,
                )
                summary_text = ""

    if format not in ("txt", "md"):
        return JSONResponse({"error": "unsupported format"}, status_code=400)
    media = "text/markdown" if format == "md" else "text/plain"
    return Response(content=summary_text, media_type=media)


@app.get("/api/bg/action-items/{task_id}")
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
        except (OSError, UnicodeDecodeError) as exc:
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
                if re.search(r"\b(Action|TODO|Action Item)[:\-]", l, re.IGNORECASE):
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
        import csv
        import io

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
