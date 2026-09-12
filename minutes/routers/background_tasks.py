import asyncio
import json
import uuid

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, StreamingResponse

from minutes.bg_store import get_task
from minutes.db import session_scope
from minutes.models import TaskHistory
from minutes.routers.background_task_artifacts import router as artifacts_router
from minutes.routers.background_task_catalog import router as catalog_router
from minutes.routers.background_task_lifecycle import router as lifecycle_router
from minutes.schemas import (
    StatusResponse,
    TaskEventsResponse,
    normalize_task_status,
    task_stage_from_status,
)
from minutes.sse import register_queue, unregister_queue

router = APIRouter(prefix="/api/bg", tags=["background-tasks"])


@router.get("/status/{task_id}", response_model=StatusResponse)
def bg_status(task_id: str):
    task = get_task(task_id)
    if not task:
        return JSONResponse({"error": "unknown task"}, status_code=404)
    stage = task_stage_from_status(task["status"])
    status = task["status"]
    detail = task.get("detail")
    if stage is not None:
        stage, legacy_detail = normalize_task_status(status)
        status = stage.value
        detail = detail or legacy_detail
    return {
        "task_id": task_id,
        "status": status,
        "stage": stage,
        "detail": detail,
        "error": task.get("error"),
        "progress": task.get("progress"),
    }


@router.get(
    "/result/{task_id}",
    responses={
        200: {"description": "success", "content": {"application/json": {}}},
        202: {"description": "pending or failed"},
        404: {"description": "unknown task"},
    },
)
def bg_result(task_id: str):
    task = get_task(task_id)
    if not task:
        return JSONResponse({"error": "unknown task"}, status_code=404)
    if task["status"] != "success":
        return JSONResponse(
            {"status": task["status"], "error": task.get("error")}, status_code=202
        )
    return {"status": "success", "result": task.get("result")}


@router.get("/events")
async def bg_events(request: Request):
    """Stream task events to clients using server-sent events."""
    queue = register_queue()

    async def event_generator():
        try:
            while True:
                if await request.is_disconnected():
                    break
                try:
                    event = await queue.get()
                except asyncio.CancelledError:
                    break
                try:
                    payload = json.dumps(event, default=str)
                except (TypeError, ValueError):
                    payload = json.dumps(
                        {"type": "error", "error": "serialization_failed"}
                    )
                yield f"data: {payload}\n\n"
        finally:
            unregister_queue(queue)

    return StreamingResponse(event_generator(), media_type="text/event-stream")


@router.get(
    "/tasks/{task_id}/events",
    response_model=TaskEventsResponse,
    response_model_exclude_none=True,
)
def bg_task_events(task_id: str):
    """Return all stored events for a task, newest first."""
    try:
        key = uuid.UUID(task_id)
    except (ValueError, TypeError):
        return JSONResponse({"error": "invalid task id"}, status_code=400)

    with session_scope() as session:
        rows = (
            session.query(TaskHistory)
            .filter(TaskHistory.task_id == key)
            .order_by(TaskHistory.event_ts.desc())
            .all()
        )
        events = [
            {
                "event_ts": row.event_ts.isoformat() + "Z" if row.event_ts else None,
                "event_type": row.event_type,
                "payload": row.payload,
            }
            for row in rows
        ]
    return {"task_id": task_id, "events": events}


router.include_router(catalog_router)
router.include_router(lifecycle_router)
router.include_router(artifacts_router)
