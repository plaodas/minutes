import asyncio
import logging
import os
import shutil
import time
import typing
import uuid

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
    JSONResponse,
    Response,
)
from pydantic import BaseModel
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from minutes import tasks
from minutes.audio import preprocess
from minutes.bg_store import (
    _parse_key,
    create_task,
    update_task_failure,
    update_task_status,
    update_task_success,
)
from minutes.celery_app import celery
from minutes.db import session_scope
from minutes.minio_client import MinioService
from minutes.models import DUMMY_OWNER_ID, Bucket
from minutes.ollama import format_minutes_from_raw
from minutes.reconcile_bg_tasks import reconcile_once
from minutes.routers.background_tasks import (
    router as background_tasks_router,
)
from minutes.schemas import (
    CreateTaskResponse,
    FormatRawRequest,
    FormatRawResponse,
    TaskStage,
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
