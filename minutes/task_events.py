import logging
from collections.abc import Callable
from typing import Any

from .schemas import TaskEventType, build_task_event
from .sse import publish_event

logger = logging.getLogger("minutes.task_events")

EventPublisher = Callable[[dict[str, Any]], None]


def emit_task_event(
    task_id: str,
    event_type: TaskEventType | str,
    payload: dict[str, Any] | None = None,
    *,
    publisher: EventPublisher | None = None,
) -> None:
    try:
        (publisher or publish_event)(
            build_task_event(str(task_id), event_type, payload)
        )
    except (RuntimeError, OSError):
        logger.exception("publish_event failed for %s", task_id)
