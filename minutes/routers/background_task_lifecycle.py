import logging
import os

from celery.exceptions import CeleryError
from fastapi import APIRouter, Request
from kombu.exceptions import KombuError
from sqlalchemy.exc import SQLAlchemyError

from minutes.bg_store import update_task_cancelled
from minutes.celery_app import celery
from minutes.http_errors import error_json
from minutes.schemas import (
    JSON_ERROR_RESPONSES,
    TaskCancelledResponse,
    TaskDeletedResponse,
    TaskHardDeleteResponse,
    TaskUndeletedResponse,
)
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


@router.post("/cancel/{task_id}", response_model=TaskCancelledResponse)
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


@router.post(
    "/delete/{task_id}",
    response_model=TaskDeletedResponse,
    responses={
        404: JSON_ERROR_RESPONSES[404],
        409: JSON_ERROR_RESPONSES[409],
        500: JSON_ERROR_RESPONSES[500],
    },
)
def bg_delete(task_id: str):
    try:
        if not mark_task_deleted(task_id):
            return error_json("unknown task", 404)
    except ValueError as exc:
        return error_json(str(exc), 409)
    except SQLAlchemyError as exc:
        logging.getLogger(__name__).exception("soft delete failed for %s", task_id)
        return error_json(str(exc), 500)

    return {"task_id": task_id, "deleted": True}


@router.post(
    "/force-delete/{task_id}",
    response_model=TaskDeletedResponse,
    responses={404: JSON_ERROR_RESPONSES[404], 500: JSON_ERROR_RESPONSES[500]},
)
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
            return error_json("unknown task", 404)
        return {"task_id": task_id, "deleted": True}
    except (SQLAlchemyError, OSError, RuntimeError) as exc:
        return error_json(str(exc), 500)


@router.post(
    "/undelete/{task_id}",
    response_model=TaskUndeletedResponse,
    responses={
        404: JSON_ERROR_RESPONSES[404],
        409: JSON_ERROR_RESPONSES[409],
        500: JSON_ERROR_RESPONSES[500],
    },
)
def bg_undelete(task_id: str):
    try:
        if not restore_task(task_id):
            return error_json("unknown task", 404)
    except ValueError as exc:
        return error_json(str(exc), 409)
    except SQLAlchemyError as exc:
        logging.getLogger(__name__).exception("undelete failed for %s", task_id)
        return error_json(str(exc), 500)

    return {"task_id": task_id, "undeleted": True}


@router.post(
    "/hard-delete/{task_id}",
    response_model=TaskHardDeleteResponse,
    response_model_exclude_none=True,
    responses={
        403: JSON_ERROR_RESPONSES[403],
        404: JSON_ERROR_RESPONSES[404],
        500: JSON_ERROR_RESPONSES[500],
    },
)
def bg_hard_delete(task_id: str, request: Request = None):
    if ADMIN_API_TOKEN and _get_admin_token(request) != ADMIN_API_TOKEN:
        return error_json("forbidden", 403)
    try:
        try:
            from minutes.tasks import hard_delete_task

            job = hard_delete_task.delay(task_id, None)
            return {"task_id": task_id, "enqueued": True, "job_id": str(job)}
        except (ImportError, AttributeError, CeleryError, KombuError):
            return bg_force_delete(task_id)
    except (SQLAlchemyError, OSError, RuntimeError, CeleryError) as exc:
        return error_json(str(exc), 500)
