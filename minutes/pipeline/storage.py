import logging
import os
from collections.abc import Callable
from datetime import datetime, timedelta, timezone
from typing import Any, TypedDict

from minio.error import S3Error

from minutes.minio_client import MinioService

logger = logging.getLogger("minutes.pipeline.storage")


class MinioArtifact(TypedDict):
    bucket: str
    object: str
    url: str | None
    expires: int | None
    expires_at: str | None


def cache_minutes_artifact(
    task_id: str | None,
    timestamp: str,
    output_file: str,
    *,
    service_factory: Callable[[], Any] = MinioService,
    now: Callable[[], datetime] | None = None,
) -> MinioArtifact | None:
    bucket = os.environ.get("MINIO_DEFAULT_BUCKET") or os.environ.get("MINIO_BUCKET")
    if not bucket:
        return None

    try:
        service = service_factory()
    except (S3Error, ValueError, OSError, RuntimeError):
        logger.exception("Failed initializing MinIO client for task %s", task_id)
        return None

    try:
        service.ensure_bucket(bucket)
    except (S3Error, ValueError):
        logger.debug("Failed ensuring MinIO bucket %s", bucket, exc_info=True)

    object_name = f"minutes/{task_id}/minutes_{timestamp}.txt"
    try:
        service.client.fput_object(bucket, object_name, output_file)
    except (S3Error, OSError):
        logger.exception("MinIO upload failed for task %s", task_id)
        return None

    try:
        expires_seconds = int(os.environ.get("MINIO_PRESIGNED_EXPIRES", "3600"))
        expires = timedelta(seconds=expires_seconds)
        url = service.presigned_get(bucket, object_name, expires=expires)
        current_time = now() if now else datetime.now(tz=timezone.utc)
        expires_at = (current_time + expires).isoformat() + "Z"
    except (ValueError, S3Error, OSError):
        url = None
        expires_seconds = None
        expires_at = None

    return {
        "bucket": bucket,
        "object": object_name,
        "url": url,
        "expires": expires_seconds,
        "expires_at": expires_at,
    }
