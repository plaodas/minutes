from fastapi import APIRouter
from sqlalchemy.exc import SQLAlchemyError

from minutes.db import session_scope
from minutes.http_errors import error_json
from minutes.minio_client import MinioService
from minutes.models import Bucket
from minutes.schemas import (
    JSON_ERROR_RESPONSES,
    AdminBucketListResponse,
    AdminCreateBucketRequest,
    BucketNameResponse,
    DeletedFlagResponse,
)

router = APIRouter(prefix="/api/admin", tags=["admin"])


@router.get(
    "/buckets",
    response_model=AdminBucketListResponse,
    responses={500: JSON_ERROR_RESPONSES[500]},
)
def list_buckets():
    try:
        service = MinioService()
        with session_scope() as session:
            db_buckets = {bucket.name: bucket for bucket in session.query(Bucket).all()}

        try:
            from minio.error import S3Error
        except ImportError:
            S3Error = Exception
        try:
            minio_buckets = service.list_buckets()
        except (S3Error, OSError):
            minio_buckets = []

        buckets = []
        seen = set()
        for bucket in minio_buckets:
            name = bucket.name
            created = getattr(bucket, "creation_date", None)
            record = db_buckets.get(name)
            buckets.append(
                {
                    "name": name,
                    "created_at": (
                        record.created_at.isoformat() + "Z"
                        if record and record.created_at
                        else (created.isoformat() if created else None)
                    ),
                    "public": bool(record.public) if record is not None else None,
                    "owner_id": str(record.owner_id) if record is not None else None,
                    "in_db": record is not None,
                }
            )
            seen.add(name)

        for name, record in db_buckets.items():
            if name in seen:
                continue
            buckets.append(
                {
                    "name": name,
                    "created_at": (
                        record.created_at.isoformat() + "Z"
                        if record.created_at
                        else None
                    ),
                    "public": bool(record.public),
                    "owner_id": str(record.owner_id),
                    "in_db": True,
                }
            )

        return {"buckets": buckets}
    except (SQLAlchemyError, OSError, RuntimeError) as exc:
        return error_json(str(exc), 500)


@router.post(
    "/buckets",
    response_model=BucketNameResponse,
    responses={
        400: JSON_ERROR_RESPONSES[400],
        409: JSON_ERROR_RESPONSES[409],
        500: JSON_ERROR_RESPONSES[500],
    },
)
def create_bucket(payload: AdminCreateBucketRequest):
    name = payload.name.strip()
    if not name:
        return error_json("missing name", 400)
    public = bool(payload.public)
    try:
        from minio.error import S3Error
    except ImportError:
        S3Error = Exception
    try:
        service = MinioService()
        service.create_bucket(name, public=public)
        with session_scope() as session:
            existing = session.query(Bucket).filter(Bucket.name == name).one_or_none()
            if not existing:
                session.add(Bucket(name=name, public=public))
        return {"name": name}
    except ValueError:
        return error_json("already exists", 409)
    except (S3Error, OSError, SQLAlchemyError) as exc:
        return error_json(str(exc), 500)


@router.delete(
    "/buckets/{name}",
    response_model=DeletedFlagResponse,
    responses={500: JSON_ERROR_RESPONSES[500]},
)
def delete_bucket(name: str, force: bool = False):
    try:
        from minio.error import S3Error
    except ImportError:
        S3Error = Exception
    try:
        service = MinioService()
        service.delete_bucket(name, force=force)
        with session_scope() as session:
            session.query(Bucket).filter(Bucket.name == name).delete()
        return {"deleted": True}
    except (S3Error, OSError, SQLAlchemyError) as exc:
        return error_json(str(exc), 500)
