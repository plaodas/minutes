from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.requests import Request

from minutes.schemas import ErrorResponse


def error_json(message: str, status_code: int) -> JSONResponse:
    return JSONResponse(
        ErrorResponse(error=message).model_dump(),
        status_code=status_code,
    )


def error_message_from_detail(detail: object) -> str:
    if isinstance(detail, str) and detail.strip():
        return detail
    if isinstance(detail, dict):
        nested = detail.get("error") or detail.get("detail")
        if isinstance(nested, str) and nested.strip():
            return nested
    return str(detail) if detail else "request failed"


def http_exception_handler(
    _request: Request, exc: StarletteHTTPException
) -> JSONResponse:
    return error_json(error_message_from_detail(exc.detail), exc.status_code)
