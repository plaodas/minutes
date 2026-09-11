import logging
import os

from celery.exceptions import CeleryError
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from sqlalchemy.exc import SQLAlchemyError

from minutes.bg_store import (
    _parse_key,
    get_task,
    record_history,
    update_task_cancelled,
    update_task_success,
)
from minutes.celery_app import celery
from minutes.db import session_scope
from minutes.minio_client import MinioService
from minutes.models import Task, TaskHistory

router = APIRouter()
ADMIN_API_TOKEN = os.environ.get("ADMIN_API_TOKEN")


def _get_admin_token(request: Request | None) -> str | None:
    if request is None:
        return None
    token = request.headers.get("X-Admin-Token") or request.headers.get("Authorization")
    if token and token.lower().startswith("bearer "):
        return token.split(" ", 1)[1]
    return token


@router.post("/cancel/{task_id}")
def bg_cancel(task_id: str):
    try:
        celery.control.revoke(task_id, terminate=True, signal="SIGTERM")
    except CeleryError:
        logging.getLogger(__name__).debug(
            "celery.revoke failed for %s", task_id, exc_info=True
        )
    try:
        update_task_cancelled(task_id)
    except SQLAlchemyError:
        logging.getLogger(__name__).exception(
            "update_task_cancelled failed for %s", task_id
        )
    return {"task_id": task_id, "cancelled": True}


@router.post("/delete/{task_id}")
def bg_delete(task_id: str):
    try:
        task = get_task(task_id)
    except SQLAlchemyError:
        logging.getLogger(__name__).exception("get_task failed for %s", task_id)
        task = None
    if not task:
        return JSONResponse({"error": "unknown task"}, status_code=404)
    try:
        try:
            with session_scope() as db:
                key = _parse_key(task_id)
                obj = db.get(Task, key)
                if not obj:
                    return JSONResponse({"error": "unknown task"}, status_code=404)
                previous = obj.status
                obj.status = "deleted"
                try:
                    from datetime import datetime, timezone

                    obj.deleted = True
                    obj.deleted_at = datetime.now(tz=timezone.utc)
                except (AttributeError, SQLAlchemyError):
                    logging.getLogger(__name__).debug(
                        "failed to set deleted flags for %s", task_id, exc_info=True
                    )
                db.add(obj)
                try:
                    db.commit()
                except SQLAlchemyError:
                    db.rollback()
                    logging.getLogger(__name__).exception(
                        "commit failed while deleting task %s", task_id
                    )
                try:
                    record_history(task_id, "deleted", {"previous": previous}, db=db)
                except SQLAlchemyError:
                    logging.getLogger(__name__).exception(
                        "record_history failed while deleting task %s", task_id
                    )
        except SQLAlchemyError:
            try:
                task = get_task(task_id)
                task["status"] = "deleted"
                try:
                    update_task_success(task_id, task.get("result") or {})
                except SQLAlchemyError:
                    logging.getLogger(__name__).exception(
                        "update_task_success failed in fallback for %s", task_id
                    )
            except SQLAlchemyError:
                logging.getLogger(__name__).exception(
                    "fallback get_task/update failed for %s", task_id
                )
        return {"task_id": task_id, "deleted": True}
    except (SQLAlchemyError, OSError, RuntimeError) as exc:
        return JSONResponse({"error": str(exc)}, status_code=500)


@router.post("/force-delete/{task_id}")
def bg_force_delete(task_id: str):
    try:
        celery.control.revoke(task_id, terminate=True, signal="SIGTERM")
    except CeleryError:
        pass

    try:
        key = _parse_key(task_id)
        with session_scope() as db:
            obj = db.get(Task, key)
            if not obj:
                return JSONResponse({"error": "unknown task"}, status_code=404)
            result = obj.result or {}

        try:
            if isinstance(result, dict):
                minio_info = (
                    result.get("minio")
                    if isinstance(result.get("minio"), dict)
                    else None
                )
                if minio_info and minio_info.get("bucket") and minio_info.get("object"):
                    try:
                        service = MinioService()
                        try:
                            from minio.error import S3Error
                        except ImportError:
                            S3Error = Exception
                        try:
                            service.client.remove_object(
                                minio_info["bucket"], minio_info["object"]
                            )
                        except (S3Error, OSError):
                            logging.getLogger(__name__).debug(
                                "MinIO remove_object failed for %s/%s",
                                minio_info.get("bucket"),
                                minio_info.get("object"),
                                exc_info=True,
                            )
                    except (ImportError, OSError, RuntimeError, AttributeError):
                        logging.getLogger(__name__).debug(
                            "MinIO client unavailable while removing object for %s",
                            task_id,
                            exc_info=True,
                        )

                output_file = result.get("output_file") or (
                    result.get("result") or {}
                ).get("output_file")
                if output_file:
                    try:
                        outputs_dir = os.environ.get("OUTPUTS_DIR", "outputs")
                        candidate = os.path.join(
                            outputs_dir, os.path.basename(output_file)
                        )
                        if os.path.exists(candidate):
                            os.remove(candidate)
                    except OSError:
                        logging.getLogger(__name__).debug(
                            "failed to remove output file candidate %s for %s",
                            candidate,
                            task_id,
                            exc_info=True,
                        )
        except (
            ImportError,
            OSError,
            RuntimeError,
            AttributeError,
            TypeError,
            ValueError,
        ):
            logging.getLogger(__name__).exception(
                "unexpected error while attempting MinIO/file cleanup for %s",
                task_id,
            )

        try:
            with session_scope() as db:
                try:
                    db.query(TaskHistory).filter(TaskHistory.task_id == key).delete()
                except SQLAlchemyError:
                    logging.getLogger(__name__).exception(
                        "failed to delete TaskHistory for %s", key
                    )
                try:
                    task = db.get(Task, key)
                    if task:
                        db.delete(task)
                        db.commit()
                except SQLAlchemyError:
                    db.rollback()
                    logging.getLogger(__name__).exception(
                        "failed to delete Task %s", key
                    )
                    return JSONResponse(
                        {"error": "failed to delete task"}, status_code=500
                    )
        except (SQLAlchemyError, OSError, RuntimeError) as exc:
            return JSONResponse({"error": str(exc)}, status_code=500)
        return {"task_id": task_id, "deleted": True}
    except (SQLAlchemyError, OSError, RuntimeError) as exc:
        return JSONResponse({"error": str(exc)}, status_code=500)


@router.post("/undelete/{task_id}")
def bg_undelete(task_id: str):
    try:
        task = get_task(task_id)
    except SQLAlchemyError:
        logging.getLogger(__name__).exception("get_task failed for %s", task_id)
        task = None
    if not task:
        return JSONResponse({"error": "unknown task"}, status_code=404)
    try:
        with session_scope() as db:
            obj = db.get(Task, _parse_key(task_id))
            if not obj:
                return JSONResponse({"error": "unknown task"}, status_code=404)
            previous = obj.status
            obj.status = "success" if obj.result else "pending"
            db.add(obj)
            db.commit()
            try:
                record_history(task_id, "undeleted", {"previous": previous}, db=db)
            except SQLAlchemyError:
                logging.getLogger(__name__).exception(
                    "record_history failed while undeleting task %s", task_id
                )
        return {"task_id": task_id, "undeleted": True}
    except (SQLAlchemyError, OSError, RuntimeError) as exc:
        return JSONResponse({"error": str(exc)}, status_code=500)


@router.post("/hard-delete/{task_id}")
def bg_hard_delete(task_id: str, request: Request = None):
    if ADMIN_API_TOKEN and _get_admin_token(request) != ADMIN_API_TOKEN:
        return JSONResponse({"error": "forbidden"}, status_code=403)
    try:
        try:
            from minutes.tasks import hard_delete_task

            job = hard_delete_task.delay(task_id, None)
            return {"task_id": task_id, "enqueued": True, "job_id": str(job)}
        except (ImportError, AttributeError, CeleryError):
            return bg_force_delete(task_id)
    except (SQLAlchemyError, OSError, RuntimeError, CeleryError) as exc:
        return JSONResponse({"error": str(exc)}, status_code=500)
