import logging
import os
from datetime import datetime, timezone

from minio.error import S3Error
from requests.exceptions import RequestException
from sqlalchemy.exc import SQLAlchemyError

from minutes.bg_store import _parse_key, emit_task_event
from minutes.db import session_scope
from minutes.minio_client import MinioService
from minutes.models import Bucket, Task, TaskHistory

logger = logging.getLogger(__name__)


def delete_task_permanently(
    task_id: str,
    requester: str | None = None,
    *,
    artifact_errors_fatal: bool = True,
) -> dict[str, object]:
    key = _parse_key(task_id)

    with session_scope() as db:
        task = db.get(Task, key)
        if not task:
            return {"deleted": False, "reason": "unknown task"}

        result = task.result or {}
        try:
            if isinstance(result, dict):
                minio_info = (
                    result.get("minio")
                    if isinstance(result.get("minio"), dict)
                    else None
                )
                if minio_info and minio_info.get("bucket"):
                    service = MinioService()
                    bucket = minio_info["bucket"]
                    if minio_info.get("object"):
                        service.delete_object(
                            bucket, minio_info["object"], ignore_missing=True
                        )
                    else:
                        service.delete_objects_with_prefix(
                            bucket,
                            f"minutes/{task_id}/",
                            ignore_missing=True,
                        )
        except (S3Error, RequestException, OSError, RuntimeError):
            logger.exception("MinIO deletion failed for task %s", task_id)
            if artifact_errors_fatal:
                raise

        try:
            if isinstance(result, dict):
                nested_result = result.get("result")
                output_file = result.get("output_file") or (
                    nested_result.get("output_file")
                    if isinstance(nested_result, dict)
                    else None
                )
                if output_file:
                    candidate = os.path.join(
                        os.environ.get("OUTPUTS_DIR", "outputs"),
                        os.path.basename(output_file),
                    )
                    if os.path.exists(candidate):
                        os.remove(candidate)
        except OSError:
            logger.exception("Local output deletion failed for task %s", task_id)

        db.query(TaskHistory).filter(TaskHistory.task_id == key).delete()
        db.delete(task)

        try:
            if isinstance(result, dict):
                minio_info = result.get("minio")
                bucket_name = (
                    minio_info.get("bucket") if isinstance(minio_info, dict) else None
                )
                if bucket_name:
                    other_tasks = (
                        db.query(Task)
                        .filter(
                            Task.result["minio"]["bucket"].as_string() == bucket_name
                        )
                        .count()
                    )
                    if other_tasks == 0:
                        bucket = (
                            db.query(Bucket)
                            .filter(Bucket.name == bucket_name)
                            .one_or_none()
                        )
                        if bucket:
                            db.delete(bucket)
        except SQLAlchemyError:
            logger.exception("Bucket cleanup failed for task %s", task_id)

    emit_task_event(
        task_id,
        "deleted_hard",
        {
            "requester": requester or None,
            "deleted_at": datetime.now(tz=timezone.utc).isoformat(),
        },
    )
    return {"deleted": True}
