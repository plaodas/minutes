from enum import Enum
from typing import Any, Literal, TypedDict, cast

from pydantic import BaseModel, ConfigDict
from typing_extensions import NotRequired


class TaskStage(str, Enum):
    PENDING = "pending"
    PREPROCESS = "preprocess"
    TRANSCRIBING = "transcribing"
    FORMATTING = "formatting"
    SUCCESS = "success"
    FAILED = "failed"
    CANCELLED = "cancelled"
    DELETED = "deleted"


TERMINAL_TASK_STAGES = frozenset(
    {
        TaskStage.SUCCESS,
        TaskStage.FAILED,
        TaskStage.CANCELLED,
        TaskStage.DELETED,
    }
)

# A transition may skip intermediate processing stages because workers can
# recover after an event was missed. Backward transitions are reserved for
# explicit retry/restore flows.
ALLOWED_TASK_STAGE_TRANSITIONS: dict[TaskStage, frozenset[TaskStage]] = {
    TaskStage.PENDING: frozenset(
        {
            TaskStage.PREPROCESS,
            TaskStage.TRANSCRIBING,
            TaskStage.FORMATTING,
            TaskStage.SUCCESS,
            TaskStage.FAILED,
            TaskStage.CANCELLED,
            TaskStage.DELETED,
        }
    ),
    TaskStage.PREPROCESS: frozenset(
        {
            TaskStage.TRANSCRIBING,
            TaskStage.FORMATTING,
            TaskStage.SUCCESS,
            TaskStage.FAILED,
            TaskStage.CANCELLED,
            TaskStage.DELETED,
        }
    ),
    TaskStage.TRANSCRIBING: frozenset(
        {
            TaskStage.FORMATTING,
            TaskStage.SUCCESS,
            TaskStage.FAILED,
            TaskStage.CANCELLED,
            TaskStage.DELETED,
        }
    ),
    TaskStage.FORMATTING: frozenset(
        {
            TaskStage.SUCCESS,
            TaskStage.FAILED,
            TaskStage.CANCELLED,
            TaskStage.DELETED,
        }
    ),
    TaskStage.SUCCESS: frozenset({TaskStage.DELETED}),
    TaskStage.FAILED: frozenset(
        {
            TaskStage.PENDING,
            TaskStage.PREPROCESS,
            TaskStage.TRANSCRIBING,
            TaskStage.DELETED,
        }
    ),
    TaskStage.CANCELLED: frozenset(
        {TaskStage.PENDING, TaskStage.PREPROCESS, TaskStage.DELETED}
    ),
    TaskStage.DELETED: frozenset({TaskStage.PENDING, TaskStage.SUCCESS}),
}


class TaskEventType(str, Enum):
    CREATED = "created"
    STATUS = "status"
    PROGRESS = "progress"
    SUCCESS = "success"
    FAILURE = "failure"
    CANCELLED = "cancelled"
    RENAME = "rename"
    DELETED = "deleted"
    UNDELETED = "undeleted"
    DELETED_HARD = "deleted_hard"


class TaskEventPayload(BaseModel):
    model_config = ConfigDict(extra="allow")

    status: TaskStage | None = None
    detail: str | None = None
    progress: float | None = None
    result: Any = None
    error: str | None = None
    name: str | None = None
    previous: str | None = None


class TaskEvent(BaseModel):
    type: Literal["task.event"] = "task.event"
    task_id: str
    event_type: TaskEventType
    stage: TaskStage | None = None
    payload: TaskEventPayload


class TaskEventData(TypedDict):
    type: Literal["task.event"]
    task_id: str
    event_type: TaskEventType
    stage: NotRequired[TaskStage]
    payload: dict[str, Any]


_STATUS_STAGE_ALIASES = {
    "created": TaskStage.PENDING,
    "queued": TaskStage.PENDING,
    "upload": TaskStage.PENDING,
    "uploading": TaskStage.PENDING,
    "pre": TaskStage.PREPROCESS,
    "pre-processing": TaskStage.PREPROCESS,
    "recognize": TaskStage.TRANSCRIBING,
    "recognizing": TaskStage.TRANSCRIBING,
    "format": TaskStage.FORMATTING,
    "done": TaskStage.SUCCESS,
    "finished": TaskStage.SUCCESS,
    "completed": TaskStage.SUCCESS,
    "failure": TaskStage.FAILED,
}


def task_stage_from_status(status: str | None) -> TaskStage | None:
    if not status:
        return None
    normalized = status.strip().lower().split(":", 1)[0]
    try:
        return TaskStage(normalized)
    except ValueError:
        return _STATUS_STAGE_ALIASES.get(normalized)


def normalize_task_status(
    status: TaskStage | str,
    detail: str | None = None,
) -> tuple[TaskStage, str | None]:
    raw_status = status.value if isinstance(status, TaskStage) else str(status).strip()
    stage = task_stage_from_status(raw_status)
    if stage is None:
        raise ValueError(f"unknown task stage: {status!r}")
    legacy_detail = raw_status.partition(":")[2].strip() or None
    return stage, detail if detail is not None else legacy_detail


def is_task_stage_transition_allowed(
    current: TaskStage | str,
    target: TaskStage | str,
) -> bool:
    current_stage = task_stage_from_status(
        current.value if isinstance(current, TaskStage) else current
    )
    target_stage = task_stage_from_status(
        target.value if isinstance(target, TaskStage) else target
    )
    if current_stage is None or target_stage is None:
        return False
    return (
        current_stage == target_stage
        or target_stage in ALLOWED_TASK_STAGE_TRANSITIONS[current_stage]
    )


def build_task_event(
    task_id: str,
    event_type: TaskEventType | str,
    payload: dict[str, Any] | None = None,
) -> TaskEventData:
    typed_event_type = TaskEventType(event_type)
    event_payload = dict(payload or {})
    raw_status = event_payload.get("status")
    stage = task_stage_from_status(raw_status)
    if raw_status is not None and stage is not None:
        stage, detail = normalize_task_status(raw_status, event_payload.get("detail"))
        event_payload["status"] = stage
        if detail is not None:
            event_payload["detail"] = detail
    if stage is None:
        stage = {
            TaskEventType.CREATED: TaskStage.PENDING,
            TaskEventType.SUCCESS: TaskStage.SUCCESS,
            TaskEventType.FAILURE: TaskStage.FAILED,
            TaskEventType.CANCELLED: TaskStage.CANCELLED,
            TaskEventType.DELETED: TaskStage.DELETED,
        }.get(typed_event_type)
    event = TaskEvent(
        task_id=str(task_id),
        event_type=typed_event_type,
        stage=stage,
        payload=TaskEventPayload(**event_payload),
    )
    return cast(TaskEventData, event.model_dump(exclude_none=True))


class TaskIdResponse(BaseModel):
    task_id: str


class CreateTaskResponse(BaseModel):
    task_id: str


class StatusResponse(BaseModel):
    task_id: str
    status: str
    stage: TaskStage | None = None
    detail: str | None = None
    error: str | None = None
    progress: float | None = None


class ResultSuccess(BaseModel):
    status: str
    result: dict[str, Any]


class FormatRawRequest(BaseModel):
    raw: str


class FormatRawResponse(BaseModel):
    minutes: str
