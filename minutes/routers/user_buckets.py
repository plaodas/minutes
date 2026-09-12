import logging
from typing import Any

from fastapi import APIRouter, Header
from pydantic import BaseModel
from sqlalchemy.exc import IntegrityError

from minutes.db import session_scope
from minutes.http_errors import error_json
from minutes.minio_client import MinioService
from minutes.models import DUMMY_OWNER_ID, Bucket
from minutes.request_auth import is_request_admin, parse_header_user_id
from minutes.schemas import (
    JSON_ERROR_RESPONSES,
    UserBucketListResponse,
    UserBucketResponse,
)

logger = logging.getLogger("minutes.routers.user_buckets")
router = APIRouter(prefix="/api/buckets", tags=["buckets"])


class CreateBucketRequest(BaseModel):
    name: str
    public: bool | None = False


def _bucket_data(bucket: Bucket) -> dict[str, Any]:
    return {
        "id": str(bucket.id),
        "name": bucket.name,
        "owner_id": str(bucket.owner_id),
        "public": bool(bucket.public),
    }


@router.post(
    "",
    response_model=UserBucketResponse,
    responses={
        401: JSON_ERROR_RESPONSES[401],
        500: JSON_ERROR_RESPONSES[500],
        502: JSON_ERROR_RESPONSES[502],
    },
)
def create_bucket(
    payload: CreateBucketRequest,
    x_admin: str | None = Header(None),
    x_user_id: str | None = Header(None),
    authorization: str | None = Header(None),
):
    admin = is_request_admin(x_admin, authorization)
    user_id = parse_header_user_id(x_user_id, authorization)
    if not admin and not user_id:
        return error_json("unauthorized: missing X-User-Id", 401)

    service = MinioService()
    try:
        from minio.error import S3Error
    except ImportError:
        S3Error = Exception

    created_in_minio = False
    try:
        if not service.client.bucket_exists(payload.name):
            service.client.make_bucket(payload.name)
            created_in_minio = True
    except (S3Error, OSError) as exc:
        return error_json(f"minio create failed: {exc!s}", 502)

    try:
        with session_scope() as session:
            existing = (
                session.query(Bucket).filter(Bucket.name == payload.name).one_or_none()
            )
            if existing:
                return _bucket_data(existing)

            bucket = Bucket(
                name=payload.name,
                owner_id=user_id or DUMMY_OWNER_ID,
                public=bool(payload.public),
                bucket_metadata={},
            )
            session.add(bucket)
            session.flush()
            response = _bucket_data(bucket)
    except IntegrityError:
        if created_in_minio:
            try:
                service.delete_bucket(payload.name, force=True)
            except (S3Error, OSError):
                logger.debug(
                    "delete_bucket failed for %s after DB error",
                    payload.name,
                    exc_info=True,
                )
        return error_json("db insert failed", 500)
    return response


@router.get("", response_model=UserBucketListResponse)
def list_buckets(
    x_admin: str | None = Header(None),
    x_user_id: str | None = Header(None),
    authorization: str | None = Header(None),
):
    admin = is_request_admin(x_admin, authorization)
    user_id = parse_header_user_id(x_user_id, authorization)
    with session_scope() as session:
        query = session.query(Bucket)
        if not admin:
            if not user_id:
                return {"buckets": []}
            query = query.filter(Bucket.owner_id == user_id)
        return {
            "buckets": [
                {
                    **_bucket_data(bucket),
                    "created_at": (
                        bucket.created_at.isoformat() if bucket.created_at else None
                    ),
                }
                for bucket in query.order_by(Bucket.created_at.desc()).all()
            ]
        }
