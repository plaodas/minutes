import logging
import os
from datetime import datetime, timezone

from sqlalchemy.exc import SQLAlchemyError

from minutes.db import session_scope
from minutes.models import Task
from minutes.schemas import TaskStage

logger = logging.getLogger("minutes.upload_retention")

_ACTIVE_STAGES = {
    TaskStage.PENDING.value,
    TaskStage.PREPROCESS.value,
    TaskStage.TRANSCRIBING.value,
    TaskStage.FORMATTING.value,
}
_RETAINED_STAGES = {TaskStage.FAILED.value, TaskStage.CANCELLED.value}
_SCAN_STAGES = _ACTIVE_STAGES | _RETAINED_STAGES
_DERIVED_SUFFIXES = ("_mono", "_norm", "_clean")


def retained_upload_result(result: object) -> dict[str, str] | None:
    """Keep only the upload path when a task fails or is cancelled."""
    if not isinstance(result, dict):
        return None
    path = result.get("upload_path")
    if isinstance(path, str) and path:
        return {"upload_path": path}
    return None


def remove_upload_family(upload_path: str) -> None:
    """Delete an upload and its derived wavs when they live under UPLOADS_DIR."""
    root = os.path.abspath(os.environ.get("UPLOADS_DIR", "uploads"))
    if not _is_managed_upload(upload_path, root):
        return
    for path in _family(upload_path):
        if not _is_managed_upload(path, root):
            continue
        try:
            if os.path.isfile(path):
                os.remove(path)
                logger.info("Removed upload file %s", path)
        except OSError:
            logger.exception("Failed to remove upload file %s", path)


def sweep_expired_uploads(now: datetime | None = None) -> None:
    """Delete failed uploads past retention, plus old files no task still needs."""
    moment = now or datetime.now(tz=timezone.utc)
    root = os.environ.get("UPLOADS_DIR", "uploads")
    if not os.path.isdir(root):
        return
    retention = int(os.environ.get("UPLOAD_RETENTION_SECONDS", "86400"))
    classified = _classified_uploads(moment, retention)
    if classified is None:
        return
    protected, expired = classified
    for path in expired:
        remove_upload_family(path)

    cutoff = moment.timestamp() - retention
    for name in os.listdir(root):
        path = os.path.join(root, name)
        if not os.path.isfile(path):
            continue
        absolute = os.path.abspath(path)
        if _belongs_to(absolute, protected):
            continue
        try:
            if os.path.getmtime(absolute) <= cutoff:
                os.remove(absolute)
                logger.info("Removed expired upload %s", absolute)
        except OSError:
            logger.exception("Failed to remove expired upload %s", absolute)


def _classified_uploads(
    now: datetime,
    retention: int,
) -> tuple[set[str], list[str]] | None:
    protected: set[str] = set()
    expired: list[str] = []
    try:
        with session_scope() as session:
            upload_path = Task.result["upload_path"].as_string()
            rows = (
                session.query(
                    Task.status,
                    Task.result,
                    Task.last_failure_ts,
                    Task.updated_at,
                )
                .filter(Task.status.in_(tuple(_SCAN_STAGES)))
                .filter(upload_path.isnot(None))
                .filter(upload_path != "")
                .all()
            )
    except (SQLAlchemyError, LookupError, ValueError):
        logger.exception("Failed to read tasks for upload retention")
        return None
    for status, result, last_failure_ts, updated_at in rows:
        path = _upload_path(result)
        if path is None:
            continue
        status_value = _status_value(status)
        if status_value in _ACTIVE_STAGES:
            protected.add(path)
            continue
        if status_value not in _RETAINED_STAGES:
            continue
        stamp = _retention_stamp(status_value, last_failure_ts, updated_at)
        if stamp is None or (now - stamp).total_seconds() < retention:
            protected.add(path)
            continue
        expired.append(path)
    return protected, expired


def _upload_path(result: object) -> str | None:
    if not isinstance(result, dict):
        return None
    path = result.get("upload_path")
    if isinstance(path, str) and path:
        return os.path.abspath(path)
    return None


def _status_value(status: object) -> str:
    value = getattr(status, "value", status)
    return str(value)


def _retention_stamp(
    status: str,
    last_failure_ts: datetime | None,
    updated_at: datetime | None,
) -> datetime | None:
    if status == TaskStage.FAILED.value:
        stamp = last_failure_ts or updated_at
    else:
        stamp = updated_at or last_failure_ts
    if stamp is None:
        return None
    if stamp.tzinfo is None:
        return stamp.replace(tzinfo=timezone.utc)
    return stamp


def _family(upload_path: str) -> tuple[str, ...]:
    base = os.path.splitext(upload_path)[0]
    return (
        upload_path,
        f"{base}_mono.wav",
        f"{base}_norm.wav",
        f"{base}_clean.wav",
    )


def _stem(path: str) -> str:
    base = os.path.splitext(os.path.abspath(path))[0]
    for suffix in _DERIVED_SUFFIXES:
        if base.endswith(suffix):
            return base[: -len(suffix)]
    return base


def _belongs_to(path: str, protected: set[str]) -> bool:
    stem = _stem(path)
    return any(_stem(upload) == stem for upload in protected)


def _is_managed_upload(path: str, root: str) -> bool:
    absolute = os.path.abspath(path)
    if absolute == root:
        return False
    try:
        return os.path.commonpath((root, absolute)) == root
    except ValueError:
        return False
