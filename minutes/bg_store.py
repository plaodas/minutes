import logging
import os
import uuid
from collections.abc import Callable
from typing import Any

from sqlalchemy.orm import Session

logger = logging.getLogger("minutes.bg_store")

from .schemas import TaskEventType, TaskStage
from .task_creation import create_task as create_task_record
from .task_event_service import TaskEventService
from .task_events import emit_task_event as publish_task_event
from .task_repository import TaskSnapshot, get_task_snapshot, record_task_history
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
    record_task_history(
        task_id,
        event_type,
        payload,
        emit_event=emit_task_event if emit_event else None,
    )


def emit_task_event(
    task_id: str,
    event_type: TaskEventType | str,
    payload: dict[str, Any] | None = None,
) -> None:
    """Publish a typed task event without requiring a history row."""
    publish_task_event(task_id, event_type, payload, publisher=publish_event)


def record_and_publish(
    task_id: str,
    event_type: TaskEventType | str,
    payload: dict[str, Any] | Callable[[Any], dict[str, Any]] | None = None,
    *,
    mutate: Callable[[Session, uuid.UUID], Any] | None = None,
) -> Any:
    return TaskEventService(emit_task_event).record_and_publish(
        task_id,
        event_type,
        payload,
        mutate=mutate,
    )


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


def update_task_status(
    task_id: str,
    status: TaskStage | str,
    detail: str | None = None,
):
    update_status(task_id, status, emit_task_event, detail)


def update_task_progress(task_id: str, progress: float):
    update_progress(task_id, progress, emit_task_event)


def get_task(task_id: str) -> TaskSnapshot | None:
    return get_task_snapshot(task_id)
