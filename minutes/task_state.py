import logging
import re
import threading
import uuid
from collections.abc import Callable
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.exc import IntegrityError, OperationalError, SQLAlchemyError

from .models import DUMMY_OWNER_ID, Bucket, Task, TaskHistory
from .schemas import (
    TaskEventType,
    TaskStage,
    is_task_stage_transition_allowed,
    normalize_task_status,
    task_stage_from_status,
)
from .summary import summarize_local
from .task_event_service import TaskEventService
from .task_ids import parse_task_key
from .task_result import MissingOutputFileError, read_local_output_text, result_minio_info

logger = logging.getLogger("minutes.task_state")
_lock = threading.Lock()

EventEmitter = Callable[[str, TaskEventType | str, dict[str, Any]], None]


def _now_utc() -> datetime:
    return datetime.now(tz=timezone.utc)


def _ensure_aware(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value


def _make_task_title(text: str, max_chars: int = 20) -> str:
    if not text:
        return ""
    value = str(text)
    value = re.sub(r"```.*?```", "", value, flags=re.DOTALL)
    value = re.sub(r"`([^`]+)`", r"\1", value)
    value = re.sub(r"\*\*(.*?)\*\*", r"\1", value)
    value = re.sub(r"\*(.*?)\*", r"\1", value)
    value = re.sub(r"__(.*?)__", r"\1", value)
    value = re.sub(r"_(.*?)_", r"\1", value)
    value = re.sub(r"!\[(.*?)\]\([^\)]*\)", r"\1", value)
    value = re.sub(r"\[(.*?)\]\([^\)]*\)", r"\1", value)
    value = re.sub(r"^[>#\-\+\*]+\s*", "", value, flags=re.MULTILINE)
    value = re.sub(r">\s*", "", value)
    value = re.sub(r"[\r\n]+", " ", value)
    value = re.sub(r"\s+", " ", value).strip()
    if not value:
        return ""

    first = re.split(r"[\.。!?！]\s+", value, maxsplit=1)[0].strip()
    if len(first) <= max_chars:
        return first
    trimmed = first[: max_chars + 1].rstrip()
    if " " in trimmed:
        trimmed = trimmed[: trimmed.rfind(" ")].strip()
    if not trimmed:
        trimmed = first[:max_chars]
    return (
        trimmed[:max_chars].rstrip() + "..." if len(trimmed) >= max_chars else trimmed
    )


def _get_or_create_task(session, task_id: str) -> tuple[uuid.UUID, Task] | None:
    key = parse_task_key(task_id)
    if not isinstance(key, uuid.UUID):
        logger.error("Cannot create task for non-UUID id %s", task_id)
        return None

    task = session.get(Task, key)
    if task:
        return key, task

    task = Task(id=key, status="pending", progress=None, fail_count=0)
    session.add(task)
    return key, task


def set_task_stage(task: Task, target: TaskStage) -> None:
    current = task_stage_from_status(task.status)
    if current is None:
        raise ValueError(f"unknown current task stage: {task.status!r}")
    if not is_task_stage_transition_allowed(current, target):
        raise ValueError(
            f"task stage transition is not allowed: {current.value} -> {target.value}"
        )
    task.status = target.value


def _ensure_result_bucket(session, task: Task, result: Any, task_id: str) -> None:
    minio_info = result_minio_info(result)
    if minio_info is None:
        return

    bucket_name = str(minio_info["bucket"])
    existing = session.query(Bucket).filter(Bucket.name == bucket_name).one_or_none()
    if existing:
        return

    try:
        with session.begin_nested():
            session.add(
                Bucket(
                    name=bucket_name,
                    owner_id=getattr(task, "user_id", None) or DUMMY_OWNER_ID,
                    bucket_metadata=minio_info.get("metadata") or {},
                )
            )
            session.flush()
    except IntegrityError:
        logger.debug("Bucket row already exists for %s", bucket_name)
    except SQLAlchemyError:
        logger.exception(
            "failed to ensure bucket row for %s (task %s)", bucket_name, task_id
        )


def update_success(task_id: str, result: Any, emit_event: EventEmitter) -> None:
    def mark_success(session, _key):
        resolved = _get_or_create_task(session, task_id)
        if not resolved:
            return
        _, task = resolved
        set_task_stage(task, TaskStage.SUCCESS)
        task.result = result
        task.progress = 100.0
        task.fail_count = 0
        task.last_success_ts = _now_utc()

        if not task.name:
            try:
                text = read_local_output_text(result)
                summary = summarize_local(text, max_sentences=1).strip()
                if summary:
                    task.name = _make_task_title(summary, max_chars=20)
            except (
                MissingOutputFileError,
                OSError,
                UnicodeDecodeError,
                ValueError,
            ) as exc:
                logger.debug(
                    "update_success: failed to read/parse output for %s: %s",
                    task_id,
                    exc,
                )

        _ensure_result_bucket(session, task, result, task_id)

    with _lock:
        try:
            TaskEventService(emit_event).record_and_publish(
                task_id,
                TaskEventType.SUCCESS,
                {"result": result},
                mutate=mark_success,
            )
        except (SQLAlchemyError, OperationalError, OSError, RuntimeError):
            logger.exception("update_success failed for %s", task_id)
            return

def update_failure(task_id: str, error_msg: str, emit_event: EventEmitter) -> None:
    def mark_failure(session, _key):
        resolved = _get_or_create_task(session, task_id)
        if not resolved:
            return
        _, task = resolved
        set_task_stage(task, TaskStage.FAILED)
        task.result = None
        task.fail_count = (task.fail_count or 0) + 1
        task.last_failure_ts = _now_utc()

    with _lock:
        try:
            TaskEventService(emit_event).record_and_publish(
                task_id,
                TaskEventType.FAILURE,
                {"error": error_msg},
                mutate=mark_failure,
            )
        except (SQLAlchemyError, OperationalError, OSError, RuntimeError):
            logger.exception("update_failure failed for %s", task_id)
            return

def update_cancelled(task_id: str, emit_event: EventEmitter) -> None:
    def mark_cancelled(session, _key):
        resolved = _get_or_create_task(session, task_id)
        if not resolved:
            return
        _, task = resolved
        set_task_stage(task, TaskStage.CANCELLED)
        task.result = None

    with _lock:
        try:
            TaskEventService(emit_event).record_and_publish(
                task_id,
                TaskEventType.CANCELLED,
                mutate=mark_cancelled,
            )
        except (SQLAlchemyError, OperationalError, OSError, RuntimeError):
            logger.exception("update_cancelled failed for %s", task_id)
            return

def update_status(
    task_id: str,
    status: TaskStage | str,
    emit_event: EventEmitter,
    detail: str | None = None,
) -> None:
    stage, status_detail = normalize_task_status(status, detail)
    payload: dict[str, Any] = {"status": stage.value}
    if status_detail is not None:
        payload["detail"] = status_detail

    def mark_status(session, _key):
        resolved = _get_or_create_task(session, task_id)
        if not resolved:
            return
        _, task = resolved
        set_task_stage(task, stage)

    with _lock:
        try:
            TaskEventService(emit_event).record_and_publish(
                task_id,
                TaskEventType.STATUS,
                payload,
                mutate=mark_status,
            )
        except (SQLAlchemyError, OperationalError, OSError, RuntimeError):
            logger.exception("update_status failed for %s", task_id)
            return


def update_progress(task_id: str, progress: float, emit_event: EventEmitter) -> None:
    progress_value = float(progress)

    def store_progress(session, _key):
        resolved = _get_or_create_task(session, task_id)
        if not resolved:
            return
        key, task = resolved
        task.progress = progress_value
        last = (
            session.query(TaskHistory)
            .filter(
                TaskHistory.task_id == key,
                TaskHistory.event_type == "progress",
            )
            .order_by(TaskHistory.event_ts.desc())
            .limit(1)
            .one_or_none()
        )
        should_record = True
        if last and isinstance(last.payload, dict):
            try:
                last_progress = float(last.payload.get("progress", 0.0))
            except (TypeError, ValueError):
                last_progress = None
            if last_progress is not None:
                now = _now_utc()
                last_event = _ensure_aware(last.event_ts) or now
                if (
                    abs(progress_value - last_progress) < 5.0
                    and (now - last_event).total_seconds() < 5.0
                ):
                    should_record = False
        if should_record:
            now = _now_utc()
            last_event = _ensure_aware(last.event_ts) if last else None
            if last and last_event and (now - last_event).total_seconds() < 86400:
                last.payload = {"progress": progress_value}
                last.event_ts = now
            else:
                session.add(
                    TaskHistory(
                        task_id=key,
                        event_type="progress",
                        payload={"progress": progress_value},
                    )
                )

    with _lock:
        try:
            TaskEventService(emit_event).record_and_publish(
                task_id,
                TaskEventType.PROGRESS,
                {"progress": progress_value},
                mutate=store_progress,
                record_history=False,
            )
        except (SQLAlchemyError, OperationalError, OSError, RuntimeError):
            logger.exception("update_progress failed for %s", task_id)
            return
