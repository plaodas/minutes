from fastapi.responses import JSONResponse

from minutes.schemas import ErrorResponse


def error_json(message: str, status_code: int) -> JSONResponse:
    return JSONResponse(
        ErrorResponse(error=message).model_dump(),
        status_code=status_code,
    )
