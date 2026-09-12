from enum import Enum
from typing import Any, Literal, TypedDict, cast

from pydantic import BaseModel, ConfigDict, model_validator
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

    @model_validator(mode="before")
    @classmethod
    def normalize_legacy_status(cls, value):
        if not isinstance(value, dict) or not isinstance(value.get("status"), str):
            return value
        stage = task_stage_from_status(value["status"])
        if stage is None:
            return value
        normalized = dict(value)
        stage, detail = normalize_task_status(
            value["status"],
            value.get("detail"),
        )
        normalized["status"] = stage
        if detail is not None:
            normalized["detail"] = detail
        return normalized


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


def task_status_value(status: TaskStage | str | None) -> str:
    if isinstance(status, TaskStage):
        return status.value
    return "" if status is None else str(status)


def task_stage_from_status(status: TaskStage | str | None) -> TaskStage | None:
    if isinstance(status, TaskStage):
        return status
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


class TaskHistoryRecord(BaseModel):
    event_ts: str | None = None
    event_type: TaskEventType
    payload: TaskEventPayload


class TaskEventsResponse(BaseModel):
    task_id: str
    events: list[TaskHistoryRecord]


class TaskHistoryResponse(BaseModel):
    task_id: str
    history: list[TaskHistoryRecord]


class TaskListItemResponse(BaseModel):
    id: str
    name: str | None = None
    status: str
    stage: TaskStage | None = None
    progress: float | None = None
    result: Any = None
    created_at: str | None = None
    last_success_ts: str | None = None
    preview_events: list[TaskHistoryRecord]
    event_count: int


class TaskListResponse(BaseModel):
    tasks: list[TaskListItemResponse]


class BulkTaskHistoriesResponse(BaseModel):
    histories: dict[str, list[TaskHistoryRecord]]
    warnings: list[str] | None = None


class ErrorResponse(BaseModel):
    error: str


JSON_ERROR_RESPONSES = {
    400: {"model": ErrorResponse, "description": "Invalid request"},
    401: {"model": ErrorResponse, "description": "Unauthorized"},
    403: {"model": ErrorResponse, "description": "Forbidden"},
    404: {"model": ErrorResponse, "description": "Not found"},
    409: {"model": ErrorResponse, "description": "Conflict"},
    413: {"model": ErrorResponse, "description": "Payload too large"},
    500: {"model": ErrorResponse, "description": "Server error"},
    502: {"model": ErrorResponse, "description": "Upstream error"},
}


class ResultSuccess(BaseModel):
    status: str
    result: dict[str, Any]


class ResultPendingResponse(BaseModel):
    status: str
    error: str | None = None


class ActionItem(BaseModel):
    model_config = ConfigDict(extra="allow")

    text: str | None = None


class ActionItemsResponse(BaseModel):
    task_id: str
    items: list[ActionItem]


class TaskCancelledResponse(BaseModel):
    task_id: str
    cancelled: bool


class TaskDeletedResponse(BaseModel):
    task_id: str
    deleted: bool


class TaskUndeletedResponse(BaseModel):
    task_id: str
    undeleted: bool


class TaskHardDeleteResponse(BaseModel):
    task_id: str
    deleted: bool | None = None
    enqueued: bool | None = None
    job_id: str | None = None


class RenameTaskRequest(BaseModel):
    name: str


class TaskNameResponse(BaseModel):
    task_id: str
    name: str


class AuthLoginRequest(BaseModel):
    username: str
    password: str


class AuthFeaturesResponse(BaseModel):
    is_admin: bool
    authenticated: bool


class AuthLoginResponse(BaseModel):
    id: str
    is_admin: bool


class AuthLogoutResponse(BaseModel):
    logged_out: bool


class HealthResponse(BaseModel):
    status: str


class FormatRawRequest(BaseModel):
    raw: str


class FormatRawResponse(BaseModel):
    minutes: str


class AdminCreateBucketRequest(BaseModel):
    name: str
    public: bool = False


class AdminBucketItem(BaseModel):
    name: str
    created_at: str | None = None
    public: bool | None = None
    owner_id: str | None = None
    in_db: bool


class AdminBucketListResponse(BaseModel):
    buckets: list[AdminBucketItem]


class BucketNameResponse(BaseModel):
    name: str


class DeletedFlagResponse(BaseModel):
    deleted: bool


class ServiceTokenCreatedResponse(BaseModel):
    token: str
    id: str


class ServiceTokenItem(BaseModel):
    id: str
    name: str | None = None
    user_id: str | None = None
    revoked: bool
    created_at: str | None = None


class ServiceTokenListResponse(BaseModel):
    tokens: list[ServiceTokenItem]


class RevokedResponse(BaseModel):
    revoked: bool


class UserBucketResponse(BaseModel):
    id: str
    name: str
    owner_id: str
    public: bool


class UserBucketListItem(UserBucketResponse):
    created_at: str | None = None


class UserBucketListResponse(BaseModel):
    buckets: list[UserBucketListItem]


class UploadCleanupCandidate(BaseModel):
    path: str
    name: str
    age_seconds: int


class UploadCleanupListResponse(BaseModel):
    candidates: list[UploadCleanupCandidate]
    count: int


class UploadCleanupError(BaseModel):
    path: str
    error: str


class UploadCleanupDeleteRequest(BaseModel):
    dir: str | None = None
    pattern: str | None = None
    older_than: int | None = None
    limit: int | None = None


class UploadCleanupDeleteResponse(BaseModel):
    deleted: list[str]
    errors: list[UploadCleanupError]
    count: int
