import logging
import os

from celery.exceptions import CeleryError
from kombu.exceptions import KombuError
from redis.exceptions import RedisError
from sqlalchemy.exc import SQLAlchemyError

from minutes.celery_app import REDIS_URL, celery
from minutes.db import session_scope
from minutes.models import Task
from minutes.pipeline.task_runner import INTERRUPTED_TASK_ERROR
from minutes.schemas import TaskStage

logger = logging.getLogger("minutes.task_reclaim")

_RECLAIM_STAGES = (
    TaskStage.PENDING.value,
    TaskStage.PREPROCESS.value,
    TaskStage.TRANSCRIBING.value,
    TaskStage.FORMATTING.value,
)
_RESTART_STAGES = {
    TaskStage.PREPROCESS.value,
    TaskStage.TRANSCRIBING.value,
    TaskStage.FORMATTING.value,
}
MISSING_UPLOAD_ERROR = "upload file is missing"
_QUEUE_KEY = "minutes"


def reclaim_interrupted_tasks() -> None:
    """Re-enqueue unfinished tasks whose broker message is gone.

    Redis being unreachable leaves every task as it is. A task whose id is
    still active, reserved, scheduled, or sitting in the queue is left alone.
    """
    if os.environ.get("RECLAIM_ON_START", "1") == "0":
        return
    broker = _broker_state()
    if broker is None:
        return

    try:
        tasks = _unfinished_tasks()
    except SQLAlchemyError:
        logger.exception("reclaim skipped; tasks were not loaded")
        return

    for task in tasks:
        task_id = task["id"]
        if _broker_holds(broker, task_id):
            continue
        upload_path = task["upload_path"]
        if not upload_path or not os.path.isfile(upload_path):
            _mark_missing(task_id)
            continue
        if task["status"] in _RESTART_STAGES:
            _mark_interrupted(task_id)
        if not _enqueue(task_id, upload_path):
            _return_to_pending(task_id)


def _unfinished_tasks() -> list[dict[str, str]]:
    with session_scope() as session:
        rows = (
            session.query(Task)
            .filter(Task.deleted.is_(False))
            .filter(Task.status.in_(_RECLAIM_STAGES))
            .all()
        )
        found: list[dict[str, str]] = []
        for task in rows:
            result = task.result if isinstance(task.result, dict) else {}
            upload_path = result.get("upload_path")
            status = (
                task.status.value if isinstance(task.status, TaskStage) else task.status
            )
            found.append(
                {
                    "id": str(task.id),
                    "status": str(status),
                    "upload_path": upload_path if isinstance(upload_path, str) else "",
                }
            )
        return found


def _broker_state() -> dict[str, object] | None:
    try:
        import redis

        client = redis.Redis.from_url(
            REDIS_URL,
            socket_connect_timeout=1,
            socket_timeout=1,
        )
        client.ping()
        queued = b"\n".join(client.lrange(_QUEUE_KEY, 0, -1))
        unacked = b"\n".join(client.hvals("unacked"))
    except (RedisError, OSError):
        logger.exception("reclaim skipped; redis unavailable")
        return None

    busy: set[str] = set()
    try:
        inspector = celery.control.inspect(timeout=1.0)
        for read in (inspector.active, inspector.reserved, inspector.scheduled):
            reply = read()
            if not reply:
                continue
            for entries in reply.values():
                for entry in entries:
                    request = (
                        entry.get("request", entry) if isinstance(entry, dict) else None
                    )
                    if isinstance(request, dict) and request.get("id"):
                        busy.add(str(request["id"]))
    except (CeleryError, KombuError, OSError, RuntimeError):
        logger.exception("reclaim skipped; celery inspect failed")
        return None
    return {"busy": busy, "blob": queued + b"\n" + unacked}


def _broker_holds(broker: dict[str, object], task_id: str) -> bool:
    busy = broker["busy"]
    blob = broker["blob"]
    if isinstance(busy, set) and task_id in busy:
        return True
    return isinstance(blob, bytes) and task_id.encode() in blob


def _mark_missing(task_id: str) -> None:
    from minutes.bg_store import update_task_failure

    try:
        update_task_failure(task_id, MISSING_UPLOAD_ERROR)
    except SQLAlchemyError:
        logger.exception("failed to mark missing upload for %s", task_id)


def _mark_interrupted(task_id: str) -> None:
    from minutes.bg_store import update_task_interrupted

    try:
        update_task_interrupted(task_id, INTERRUPTED_TASK_ERROR)
    except SQLAlchemyError:
        logger.exception("failed to mark interrupted task %s", task_id)


def _return_to_pending(task_id: str) -> None:
    from minutes.bg_store import update_task_status

    try:
        update_task_status(task_id, TaskStage.PENDING)
    except (SQLAlchemyError, ValueError):
        logger.exception("failed to return %s to pending after enqueue error", task_id)


def _enqueue(task_id: str, upload_path: str) -> bool:
    try:
        from minutes.tasks import process_audio

        process_audio.apply_async(args=[upload_path], task_id=task_id)
    except (CeleryError, KombuError, OSError, RuntimeError):
        logger.exception("failed to re-enqueue task %s", task_id)
        return False
    logger.info("re-enqueued interrupted task %s", task_id)
    return True
