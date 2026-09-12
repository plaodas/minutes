import os
import threading
from typing import Any

_lock = threading.Lock()

import logging

# Always use DB-backed store. `minutes/db.py` already falls back to a
# local sqlite file when `DATABASE_URL` is not set, so drop the file
# JSON fallback to avoid split-brain between file and DB stores.
import uuid

from .db import engine, session_scope

logger = logging.getLogger("minutes.bg_store")
from sqlalchemy import inspect as sa_inspect
from sqlalchemy.exc import OperationalError, SQLAlchemyError

from .models import Task, TaskHistory, User
from .schemas import TaskEventType, TaskStage, build_task_event
from .task_state import parse_task_key as _parse_key
from .task_state import (
    update_cancelled,
    update_failure,
    update_progress,
    update_status,
    update_success,
)

try:
    from sqlalchemy.dialects.postgresql import insert as pg_insert
except ImportError:
    pg_insert = None
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
    try:
        publish_event(build_task_event(str(task_id), event_type, payload))
    except (RuntimeError, OSError):
        logger.exception("publish_event failed for %s", task_id)


def _persist_task_creation(
    task_id: str,
    task_key: uuid.UUID,
    metadata: dict | None,
    owner_id: uuid.UUID | None,
    *,
    use_pg_upsert: bool,
) -> None:
    with session_scope() as session:
        persisted_owner_id = owner_id
        dialect_name = getattr(session.get_bind().dialect, "name", "").lower()
        if (
            persisted_owner_id is not None
            and dialect_name == "postgresql"
            and sa_inspect(session.get_bind()).has_table("users")
            and session.get(User, persisted_owner_id) is None
        ):
            logger.warning(
                "create_task: provided user_id %s not found; clearing owner for task %s",
                persisted_owner_id,
                task_id,
            )
            persisted_owner_id = None

        if use_pg_upsert:
            statement = (
                pg_insert(Task.__table__)
                .values(
                    id=task_key,
                    status="pending",
                    progress=None,
                    result=metadata or None,
                    fail_count=0,
                    user_id=persisted_owner_id,
                )
                .on_conflict_do_nothing(index_elements=["id"])
            )
            session.execute(statement)
        else:
            task = session.get(Task, task_key)
            if not task:
                task = Task(
                    id=task_key,
                    status="pending",
                    progress=None,
                    result=metadata or None,
                    fail_count=0,
                    user_id=persisted_owner_id,
                )
                session.add(task)
            else:
                if metadata:
                    task.result = metadata
                if persisted_owner_id and not task.user_id:
                    task.user_id = persisted_owner_id

        session.add(
            TaskHistory(
                task_id=task_key,
                event_type="created",
                payload={"status": "pending"},
            )
        )


def create_task(
    task_id: str,
    metadata: dict | None = None,
    user_id: str | None = None,
) -> None:
    with _lock:
        try:
            parsed_task_id = _parse_key(task_id)
            if isinstance(parsed_task_id, uuid.UUID):
                task_key = parsed_task_id
            else:
                task_key = uuid.uuid4()
                metadata = dict(metadata or {})
                metadata.setdefault("external_task_id", task_id)

            parsed_owner = _parse_key(user_id) if user_id else None
            owner_id = parsed_owner if isinstance(parsed_owner, uuid.UUID) else None
            if user_id and owner_id is None:
                logger.debug(
                    "create_task: ignoring non-UUID user_id=%r for task %s",
                    user_id,
                    task_id,
                )

            use_pg_upsert = bool(
                pg_insert is not None
                and getattr(getattr(engine, "dialect", None), "name", "").lower()
                == "postgresql"
            )
            try:
                _persist_task_creation(
                    task_id,
                    task_key,
                    metadata,
                    owner_id,
                    use_pg_upsert=use_pg_upsert,
                )
            except OperationalError:
                logger.exception(
                    "Task creation failed for %s; retrying with a fresh session",
                    task_id,
                )
                _persist_task_creation(
                    task_id,
                    task_key,
                    metadata,
                    owner_id,
                    use_pg_upsert=use_pg_upsert,
                )
            except (SQLAlchemyError, AttributeError, TypeError):
                if not use_pg_upsert:
                    raise
                logger.exception(
                    "PostgreSQL upsert failed for %s; using generic persistence",
                    task_id,
                )
                _persist_task_creation(
                    task_id,
                    task_key,
                    metadata,
                    owner_id,
                    use_pg_upsert=False,
                )
        except (SQLAlchemyError, OperationalError, OSError, RuntimeError):
            logger.exception("create_task failed for %s", task_id)
            return

    emit_task_event(task_id, "created", {"status": "pending"})


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
