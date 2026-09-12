import asyncio
import logging
import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from sqlalchemy.exc import SQLAlchemyError

from minutes.reconcile_bg_tasks import reconcile_once

logger = logging.getLogger("minutes.app_lifecycle")


async def _reconcile_loop(interval: int) -> None:
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


async def _start_services(app: FastAPI) -> None:
    try:
        await asyncio.to_thread(reconcile_once)
        logger.info("Initial bg task reconciliation completed")
    except (SQLAlchemyError, RuntimeError, OSError):
        logger.exception("Initial reconciliation failed")

    interval = int(os.environ.get("RECONCILE_INTERVAL_SECONDS", "3600"))
    app.state.reconcile_task = asyncio.create_task(_reconcile_loop(interval))

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


async def _stop_services(app: FastAPI) -> None:
    task = getattr(app.state, "reconcile_task", None)
    if task and not task.done():
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

    try:
        from minutes.sse import stop_redis_listener

        stop_redis_listener()
    except (ImportError, RuntimeError, OSError):
        logger.exception("failed to stop redis listener")


@asynccontextmanager
async def app_lifespan(app: FastAPI) -> AsyncIterator[None]:
    await _start_services(app)
    try:
        yield
    finally:
        await _stop_services(app)
