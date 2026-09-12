import logging
import uuid
from typing import Any, TypedDict

from sqlalchemy.exc import SQLAlchemyError

from .db import engine, session_scope
from .models import Task, TaskHistory
from .schemas import TaskEventType
from .task_state import EventEmitter, parse_task_key

logger = logging.getLogger("minutes.task_repository")


class TaskSnapshot(TypedDict):
    status: str
    result: Any
    error: str | None
    progress: float | None
    fail_count: int
    last_failure_ts: str | None
    last_failure_error: str | None
    last_success_ts: str | None
    created_at: str | None
    name: str | None


def record_task_history(
    task_id: str,
    event_type: TaskEventType | str,
    payload: dict[str, Any] | None = None,
    *,
    emit_event: EventEmitter | None = None,
) -> None:
    logger.debug(
        "record_task_history start: task_id=%s event=%s engine=%s",
        task_id,
        event_type,
        getattr(engine, "url", None),
    )
    key = parse_task_key(task_id)
    if not isinstance(key, uuid.UUID):
        logger.debug("record_task_history skipping non-UUID task_id=%s", task_id)
        return

    try:
        with session_scope() as session:
            session.add(
                TaskHistory(
                    task_id=key,
                    event_type=(
                        event_type.value
                        if isinstance(event_type, TaskEventType)
                        else event_type
                    ),
                    payload=payload or {},
                )
            )
    except SQLAlchemyError:
        logger.exception("record_task_history DB error for %s", task_id)
        return

    if emit_event:
        emit_event(task_id, event_type, payload or {})


def get_task_snapshot(task_id: str) -> TaskSnapshot | None:
    with session_scope() as session:
        key = parse_task_key(task_id)
        task = session.get(Task, key)
        if not task:
            return None
        return {
            "status": task.status,
            "result": task.result,
            "error": None,
            "progress": (float(task.progress) if task.progress is not None else None),
            "fail_count": int(task.fail_count) if task.fail_count is not None else 0,
            "last_failure_ts": (
                task.last_failure_ts.isoformat() + "Z" if task.last_failure_ts else None
            ),
            "last_failure_error": None,
            "last_success_ts": (
                task.last_success_ts.isoformat() + "Z" if task.last_success_ts else None
            ),
            "created_at": (
                task.created_at.isoformat() + "Z"
                if getattr(task, "created_at", None)
                else None
            ),
            "name": task.name,
        }
