import uuid
from collections.abc import Callable
from typing import Any, TypeVar

from sqlalchemy.orm import Session

from .db import session_scope
from .models import TaskHistory
from .schemas import TaskEventType
from .task_state import EventEmitter, parse_task_key

MutationResult = TypeVar("MutationResult")
TaskMutation = Callable[[Session, uuid.UUID], MutationResult]
PayloadFactory = Callable[[MutationResult | None], dict[str, Any]]


class TaskEventService:
    """Persist a task mutation and history before publishing its event."""

    def __init__(self, emit_event: EventEmitter):
        self._emit_event = emit_event

    def record_and_publish(
        self,
        task_id: str,
        event_type: TaskEventType | str,
        payload: dict[str, Any] | PayloadFactory[MutationResult] | None = None,
        *,
        mutate: TaskMutation[MutationResult] | None = None,
    ) -> MutationResult | None:
        key = parse_task_key(task_id)
        if not isinstance(key, uuid.UUID):
            raise TypeError(f"invalid task id: {task_id!r}")

        with session_scope() as session:
            result = mutate(session, key) if mutate else None
            event_payload = dict(payload(result) if callable(payload) else payload or {})
            session.add(
                TaskHistory(
                    task_id=key,
                    event_type=(
                        event_type.value
                        if isinstance(event_type, TaskEventType)
                        else event_type
                    ),
                    payload=event_payload,
                )
            )

        self._emit_event(task_id, event_type, event_payload)
        return result
