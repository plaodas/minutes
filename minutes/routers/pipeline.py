from celery.result import AsyncResult
from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse

from minutes.celery_app import celery
from minutes.ollama import format_minutes_from_raw
from minutes.schemas import FormatRawRequest, FormatRawResponse

router = APIRouter(prefix="/api", tags=["pipeline"])


@router.get("/health")
def health():
    return {"status": "ok"}


@router.post("/format-raw", response_model=FormatRawResponse)
def format_raw(payload: FormatRawRequest):
    if not payload.raw:
        return JSONResponse({"error": "missing 'raw' field"}, status_code=400)

    try:
        return {"minutes": format_minutes_from_raw(payload.raw)}
    except (RuntimeError, ValueError, TypeError) as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/status/{task_id}")
def task_status(task_id: str):
    result = AsyncResult(task_id, app=celery)
    return {
        "task_id": task_id,
        "status": result.status,
        "info": str(result.info),
    }


@router.get("/result/{task_id}")
def task_result(task_id: str):
    result = AsyncResult(task_id, app=celery)
    if not result.ready():
        return JSONResponse({"status": result.status}, status_code=202)
    if result.failed():
        return JSONResponse(
            {"status": "failed", "info": str(result.info)},
            status_code=500,
        )
    return JSONResponse({"status": "success", "result": result.result})
