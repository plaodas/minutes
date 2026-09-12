import logging
import os
from datetime import datetime, timezone

from minio.error import S3Error
from requests.exceptions import RequestException
from sqlalchemy.exc import SQLAlchemyError

from minutes.minio_client import MinioService
from minutes.models import Bucket, Task, TaskHistory
from minutes.task_event_service import TaskEventService
from minutes.task_events import emit_task_event

logger = logging.getLogger(__name__)


class _TaskNotFoundError(Exception):
    pass


def delete_task_permanently(
    task_id: str,
    requester: str | None = None,
    *,
    artifact_errors_fatal: bool = True,
) -> dict[str, object]:
    def delete_task(db, key):
        task = db.get(Task, key)
        if not task:
            raise _TaskNotFoundError

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

    try:
        TaskEventService(emit_task_event).record_and_publish(
            task_id,
            "deleted_hard",
            {
                "requester": requester or None,
                "deleted_at": datetime.now(tz=timezone.utc).isoformat(),
            },
            mutate=delete_task,
            record_history=False,
        )
    except _TaskNotFoundError:
        return {"deleted": False, "reason": "unknown task"}

    return {"deleted": True}
