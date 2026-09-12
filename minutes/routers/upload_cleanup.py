import os
import time

from fastapi import APIRouter, Request

from minutes.http_errors import error_json
from minutes.schemas import (
    JSON_ERROR_RESPONSES,
    UploadCleanupDeleteRequest,
    UploadCleanupDeleteResponse,
    UploadCleanupListResponse,
)

router = APIRouter(tags=["admin"])


def _resolve_uploads_dir(
    configured_dir: str | None,
    request: Request | None,
) -> str:
    return (
        configured_dir
        or (request.query_params.get("dir") if request else None)
        or os.environ.get("UPLOADS_DIR")
        or "uploads"
    )


def _list_candidates(
    uploads_dir: str,
    pattern: str,
    older_than: int,
    limit: int,
) -> list[dict[str, int | str]]:
    now = int(time.time())
    candidates: list[dict[str, int | str]] = []
    files = [
        name
        for name in os.listdir(uploads_dir)
        if os.path.isfile(os.path.join(uploads_dir, name))
    ]
    for name in files:
        if pattern and not name.startswith(pattern):
            continue
        path = os.path.join(uploads_dir, name)
        try:
            age = now - int(os.path.getmtime(path))
        except OSError:
            continue
        if older_than and age < older_than:
            continue
        candidates.append({"path": path, "name": name, "age_seconds": age})
        if len(candidates) >= limit:
            break
    return candidates


@router.get(
    "/admin/uploads/cleanup",
    response_model=UploadCleanupListResponse,
    responses={
        404: JSON_ERROR_RESPONSES[404],
        500: JSON_ERROR_RESPONSES[500],
    },
)
@router.get(
    "/api/admin/uploads/cleanup",
    response_model=UploadCleanupListResponse,
    responses={
        404: JSON_ERROR_RESPONSES[404],
        500: JSON_ERROR_RESPONSES[500],
    },
)
def list_uploads_for_cleanup(
    dir: str | None = None,
    pattern: str = "",
    older_than: int = 0,
    limit: int = 100,
    dry_run: bool = True,
    request: Request = None,
):
    uploads_dir = _resolve_uploads_dir(dir, request)
    if not os.path.isdir(uploads_dir):
        return error_json("dir not found", 404)
    try:
        candidates = _list_candidates(uploads_dir, pattern, older_than, limit)
    except OSError as exc:
        return error_json(str(exc), 500)
    return {"candidates": candidates, "count": len(candidates)}


@router.post(
    "/admin/uploads/cleanup",
    response_model=UploadCleanupDeleteResponse,
    responses={
        404: JSON_ERROR_RESPONSES[404],
        500: JSON_ERROR_RESPONSES[500],
    },
)
@router.post(
    "/api/admin/uploads/cleanup",
    response_model=UploadCleanupDeleteResponse,
    responses={
        404: JSON_ERROR_RESPONSES[404],
        500: JSON_ERROR_RESPONSES[500],
    },
)
def delete_uploads(payload: UploadCleanupDeleteRequest, request: Request = None):
    uploads_dir = _resolve_uploads_dir(payload.dir, request)
    pattern = payload.pattern or ""
    older_than = int(payload.older_than or 0)
    limit = int(payload.limit or 100)

    if not os.path.isdir(uploads_dir):
        return error_json("dir not found", 404)

    deleted = []
    errors = []
    try:
        candidates = _list_candidates(uploads_dir, pattern, older_than, limit)
        for candidate in candidates:
            path = str(candidate["path"])
            try:
                os.remove(path)
                deleted.append(path)
            except OSError as exc:
                errors.append({"path": path, "error": str(exc)})
    except OSError as exc:
        return error_json(str(exc), 500)

    return {"deleted": deleted, "errors": errors, "count": len(deleted)}
