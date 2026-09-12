from fastapi import APIRouter

from minutes.http_errors import error_json
from minutes.ollama import format_minutes_from_raw
from minutes.schemas import (
    JSON_ERROR_RESPONSES,
    FormatRawRequest,
    FormatRawResponse,
    HealthResponse,
)

router = APIRouter(prefix="/api", tags=["pipeline"])


@router.get("/health", response_model=HealthResponse)
def health():
    return {"status": "ok"}


@router.post(
    "/format-raw",
    response_model=FormatRawResponse,
    responses={
        400: JSON_ERROR_RESPONSES[400],
        500: JSON_ERROR_RESPONSES[500],
    },
)
def format_raw(payload: FormatRawRequest):
    if not payload.raw:
        return error_json("missing 'raw' field", 400)

    try:
        return {"minutes": format_minutes_from_raw(payload.raw)}
    except (RuntimeError, ValueError, TypeError) as exc:
        return error_json(str(exc), 500)
