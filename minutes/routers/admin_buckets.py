from typing import Any

from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse
from sqlalchemy.exc import SQLAlchemyError

from minutes.db import session_scope
from minutes.minio_client import MinioService
from minutes.models import Bucket

router = APIRouter(prefix="/api/admin", tags=["admin"])


@router.get("/buckets")
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
        raise HTTPException(status_code=500, detail=str(exc))


@router.post("/buckets")
def create_bucket(payload: dict[str, Any]):
    name = (payload or {}).get("name")
    if not name:
        return JSONResponse({"error": "missing name"}, status_code=400)
    public = bool((payload or {}).get("public", False))
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
        return JSONResponse({"error": "already exists"}, status_code=409)
    except (S3Error, OSError, SQLAlchemyError) as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@router.delete("/buckets/{name}")
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
        raise HTTPException(status_code=500, detail=str(exc))
