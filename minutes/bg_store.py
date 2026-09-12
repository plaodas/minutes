import logging
import os
import uuid
from typing import Any

# Always use DB-backed store. `minutes/db.py` already falls back to a
# local sqlite file when `DATABASE_URL` is not set, so drop the file
# JSON fallback to avoid split-brain between file and DB stores.
from .db import engine, session_scope

logger = logging.getLogger("minutes.bg_store")
from sqlalchemy.exc import SQLAlchemyError

from .models import Task, TaskHistory
from .schemas import TaskEventType, TaskStage
from .task_creation import create_task as create_task_record
from .task_events import emit_task_event as publish_task_event
from .task_state import parse_task_key as _parse_key
from .task_state import (
    update_cancelled,
    update_failure,
    update_progress,
    update_status,
    update_success,
)

# SSE publisher (minimal): publish events when history rows are recorded
try:
    from .sse import publish_event
except ImportError:

    def publish_event(_):
        return


# Compatibility: some modules import `DB_PATH` when file-backed fallbacks
# were used. Keep a benign default value for backward compatibility.
DB_PATH = os.environ.get("BG_TASK_DB", "data/bg_tasks.json")


def record_history(
    task_id: str,
    event_type: str,
    payload: dict | None = None,
    emit_event: bool = True,
):
    logger.debug(
        "record_history start: task_id=%s event=%s engine=%s",
        task_id,
        event_type,
        getattr(engine, "url", None),
    )
    key = _parse_key(task_id)
    # if external id isn't a UUID, _parse_key returns original string; ensure we store a UUID
    if not isinstance(key, uuid.UUID):
        # best-effort: try to find a Task row by external id in payload or skip
        # fallback: do not create history row tied to a non-UUID id
        logger.debug("record_history skipping non-UUID task_id=%s", task_id)
        return
    try:
        with session_scope() as session:
            session.add(
                TaskHistory(
                    task_id=key,
                    event_type=event_type,
                    payload=payload or {},
                )
            )
    except SQLAlchemyError:
        logger.exception("record_history DB error for %s", task_id)
        return

    if not emit_event:
        return

    emit_task_event(task_id, event_type, payload)


def emit_task_event(
    task_id: str,
    event_type: TaskEventType | str,
    payload: dict[str, Any] | None = None,
) -> None:
    """Publish a typed task event without requiring a history row."""
    publish_task_event(task_id, event_type, payload, publisher=publish_event)


def create_task(
    task_id: str,
    metadata: dict | None = None,
    user_id: str | None = None,
) -> None:
    create_task_record(task_id, metadata, user_id, emit_task_event)


def update_task_success(task_id: str, result: Any):
    update_success(task_id, result, emit_task_event)


def update_task_failure(task_id: str, error_msg: str):
    update_failure(task_id, error_msg, emit_task_event)


def update_task_cancelled(task_id: str):
    update_cancelled(task_id, emit_task_event)


def update_task_status(task_id: str, status: TaskStage | str):
    update_status(task_id, status, emit_task_event)


def update_task_progress(task_id: str, progress: float):
    update_progress(task_id, progress, emit_task_event)


def get_task(task_id: str) -> dict[str, Any] | None:
    with session_scope() as s:
        key = _parse_key(task_id)
        t = s.get(Task, key)
        if not t:
            return None
        return {
            "status": t.status,
            "result": t.result,
            "error": None,
            "progress": float(t.progress) if t.progress is not None else None,
            "fail_count": int(t.fail_count) if t.fail_count is not None else 0,
            "last_failure_ts": (
                t.last_failure_ts.isoformat() + "Z" if t.last_failure_ts else None
            ),
            "last_failure_error": None,
            "last_success_ts": (
                t.last_success_ts.isoformat() + "Z" if t.last_success_ts else None
            ),
            "created_at": (
                t.created_at.isoformat() + "Z"
                if getattr(t, "created_at", None)
                else None
            ),
            "name": t.name,
        }
