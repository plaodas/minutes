import asyncio
import logging
import os

from celery.result import AsyncResult
from fastapi import (
    Depends,
    FastAPI,
    HTTPException,
)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import (
    JSONResponse,
)
from sqlalchemy.exc import SQLAlchemyError

from minutes.celery_app import celery
from minutes.ollama import format_minutes_from_raw
from minutes.reconcile_bg_tasks import reconcile_once
from minutes.request_auth import require_admin
from minutes.routers.admin_buckets import router as admin_buckets_router
from minutes.routers.authentication import router as authentication_router
from minutes.routers.background_tasks import (
    router as background_tasks_router,
)
from minutes.routers.service_tokens import router as service_tokens_router
from minutes.routers.upload_cleanup import router as upload_cleanup_router
from minutes.routers.uploads import router as uploads_router
from minutes.routers.user_buckets import router as user_buckets_router
from minutes.schemas import FormatRawRequest, FormatRawResponse

app = FastAPI(title="Minutes Service (prototype)")
app.include_router(background_tasks_router)

app.include_router(admin_buckets_router, dependencies=[Depends(require_admin)])
app.include_router(service_tokens_router, dependencies=[Depends(require_admin)])
app.include_router(upload_cleanup_router, dependencies=[Depends(require_admin)])
app.include_router(uploads_router)
app.include_router(user_buckets_router)
app.include_router(authentication_router)


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
