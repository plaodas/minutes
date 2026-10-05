import logging
import os

from celery import Celery
from celery.signals import (
    setup_logging,
    task_postrun,
    task_prerun,
    worker_process_init,
    worker_process_shutdown,
)

try:
    # import engine disposal helper; if import fails, ignore (tests may not set DB)
    from minutes.db import dispose_engine
except ImportError:
    dispose_engine = None

from sqlalchemy.exc import SQLAlchemyError

from minutes.log_context import configure_logging, task_id_var

REDIS_URL = os.environ.get("REDIS_URL", "redis://redis:6379/0")

logger = logging.getLogger("minutes.celery")

celery = Celery("minutes", broker=REDIS_URL, backend=REDIS_URL)

celery.conf.update(
    include=["minutes.tasks"],
    task_routes={"minutes.tasks.*": {"queue": "minutes"}},
    worker_prefetch_multiplier=1,
    broker_transport_options={
        # Redis redelivers an unacked message after this many seconds.
        # Audio processing can run longer than the 1 hour default.
        "visibility_timeout": int(os.environ.get("CELERY_VISIBILITY_TIMEOUT", "86400")),
    },
)


@setup_logging.connect
def _configure_worker_logging(**kwargs):
    configure_logging()


@task_prerun.connect
def _bind_task_id(task_id=None, **kwargs):
    task_id_var.set(None if task_id is None else str(task_id))


@task_postrun.connect
def _clear_task_id(**kwargs):
    task_id_var.set(None)


@worker_process_init.connect
def _celery_worker_init(**kwargs):
    configure_logging()
    # Dispose any inherited connections from the parent process so the child
    # process creates fresh connections from the pool.
    if dispose_engine:
        try:
            dispose_engine()
        except (SQLAlchemyError, OSError):
            logger.exception("dispose_engine failed during worker init")


@worker_process_shutdown.connect
def _celery_worker_shutdown(**kwargs):
    # Ensure engine is disposed on shutdown as well.
    if dispose_engine:
        try:
            dispose_engine()
        except (SQLAlchemyError, OSError):
            logger.exception("dispose_engine failed during worker shutdown")
