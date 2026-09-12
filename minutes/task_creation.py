import logging
import threading
import uuid
from collections.abc import Callable
from typing import Any

from sqlalchemy import inspect as sa_inspect
from sqlalchemy.exc import OperationalError, SQLAlchemyError

from .db import engine, session_scope
from .models import Task, TaskHistory, User
from .schemas import TaskEventType
from .task_state import parse_task_key

try:
    from sqlalchemy.dialects.postgresql import insert as pg_insert
except ImportError:
    pg_insert = None

logger = logging.getLogger("minutes.task_creation")
_lock = threading.Lock()

EventEmitter = Callable[[str, TaskEventType | str, dict[str, Any]], None]


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
                session.add(
                    Task(
                        id=task_key,
                        status="pending",
                        progress=None,
                        result=metadata or None,
                        fail_count=0,
                        user_id=persisted_owner_id,
                    )
                )
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
    metadata: dict | None,
    user_id: str | None,
    emit_event: EventEmitter,
) -> None:
    with _lock:
        try:
            parsed_task_id = parse_task_key(task_id)
            if isinstance(parsed_task_id, uuid.UUID):
                task_key = parsed_task_id
            else:
                task_key = uuid.uuid4()
                metadata = dict(metadata or {})
                metadata.setdefault("external_task_id", task_id)

            parsed_owner = parse_task_key(user_id) if user_id else None
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

    emit_event(task_id, "created", {"status": "pending"})
