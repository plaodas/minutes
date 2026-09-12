from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse

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
