import logging
import os

from celery.exceptions import CeleryError
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from kombu.exceptions import KombuError
from sqlalchemy.exc import SQLAlchemyError

from minutes.bg_store import update_task_cancelled
from minutes.celery_app import celery
from minutes.task_deletion import delete_task_permanently
from minutes.task_lifecycle import mark_task_deleted, restore_task

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
    except (CeleryError, KombuError):
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
        if not mark_task_deleted(task_id):
            return JSONResponse({"error": "unknown task"}, status_code=404)
    except SQLAlchemyError as exc:
        logging.getLogger(__name__).exception("soft delete failed for %s", task_id)
        return JSONResponse({"error": str(exc)}, status_code=500)

    return {"task_id": task_id, "deleted": True}


@router.post("/force-delete/{task_id}")
def bg_force_delete(task_id: str):
    try:
        celery.control.revoke(task_id, terminate=True, signal="SIGTERM")
    except (CeleryError, KombuError):
        pass

    try:
        result = delete_task_permanently(
            task_id,
            artifact_errors_fatal=False,
        )
        if not result["deleted"]:
            return JSONResponse({"error": "unknown task"}, status_code=404)
        return {"task_id": task_id, "deleted": True}
    except (SQLAlchemyError, OSError, RuntimeError) as exc:
        return JSONResponse({"error": str(exc)}, status_code=500)


@router.post("/undelete/{task_id}")
def bg_undelete(task_id: str):
    try:
        if not restore_task(task_id):
            return JSONResponse({"error": "unknown task"}, status_code=404)
    except SQLAlchemyError as exc:
        logging.getLogger(__name__).exception("undelete failed for %s", task_id)
        return JSONResponse({"error": str(exc)}, status_code=500)

    return {"task_id": task_id, "undeleted": True}


@router.post("/hard-delete/{task_id}")
def bg_hard_delete(task_id: str, request: Request = None):
    if ADMIN_API_TOKEN and _get_admin_token(request) != ADMIN_API_TOKEN:
        return JSONResponse({"error": "forbidden"}, status_code=403)
    try:
        try:
            from minutes.tasks import hard_delete_task

            job = hard_delete_task.delay(task_id, None)
            return {"task_id": task_id, "enqueued": True, "job_id": str(job)}
        except (ImportError, AttributeError, CeleryError, KombuError):
            return bg_force_delete(task_id)
    except (SQLAlchemyError, OSError, RuntimeError, CeleryError) as exc:
        return JSONResponse({"error": str(exc)}, status_code=500)
