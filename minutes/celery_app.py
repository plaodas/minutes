import logging
import os

from celery import Celery
from celery.signals import worker_process_init, worker_process_shutdown

try:
    # import engine disposal helper; if import fails, ignore (tests may not set DB)
    from minutes.db import dispose_engine
except ImportError:
    dispose_engine = None

from sqlalchemy.exc import SQLAlchemyError

REDIS_URL = os.environ.get("REDIS_URL", "redis://redis:6379/0")

logger = logging.getLogger("minutes.celery")

celery = Celery("minutes", broker=REDIS_URL, backend=REDIS_URL)

celery.conf.update(
    include=["minutes.tasks"],
    task_routes={"minutes.tasks.*": {"queue": "minutes"}},
)


@worker_process_init.connect
def _celery_worker_init(**kwargs):
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
