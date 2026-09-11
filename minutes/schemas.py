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

    status: str | None = None
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


def build_task_event(
    task_id: str,
    event_type: TaskEventType | str,
    payload: dict[str, Any] | None = None,
) -> TaskEventData:
    typed_event_type = TaskEventType(event_type)
    event_payload = payload or {}
    stage = task_stage_from_status(event_payload.get("status"))
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
    error: str | None = None


class ResultSuccess(BaseModel):
    status: str
    result: dict[str, Any]


class FormatRawRequest(BaseModel):
    raw: str


class FormatRawResponse(BaseModel):
    minutes: str
