import csv
import io
import logging
import os
import re

from fastapi import APIRouter
from fastapi.responses import FileResponse, JSONResponse, Response, StreamingResponse
from sqlalchemy.exc import SQLAlchemyError

from minutes.bg_store import get_task
from minutes.http_errors import error_json
from minutes.minio_client import MinioService, S3Error
from minutes.pipeline.formatting import extract_action_items
from minutes.schemas import ActionItemsResponse, JSON_ERROR_RESPONSES, ResultPendingResponse
from minutes.summary import summarize_local
from minutes.task_result import (
    MissingOutputFileError,
    local_output_path,
    read_local_output_text,
    result_minio_object,
    result_output_file,
)

router = APIRouter()

_TEXT_SCHEMA = {"schema": {"type": "string"}}
_ARTIFACT_ERROR_RESPONSES = {
    202: {
        "model": ResultPendingResponse,
        "description": "Task has not completed successfully",
    },
    404: JSON_ERROR_RESPONSES[404],
    500: JSON_ERROR_RESPONSES[500],
}
_ARTIFACT_DOWNLOAD_RESPONSES = {
    **_ARTIFACT_ERROR_RESPONSES,
    502: JSON_ERROR_RESPONSES[502],
}
_ARTIFACT_FORMAT_RESPONSES = {
    **_ARTIFACT_ERROR_RESPONSES,
    400: JSON_ERROR_RESPONSES[400],
}
_ARTIFACT_TEXT_RESPONSES = {
    200: {
        "description": "Artifact text",
        "content": {
            "text/plain": _TEXT_SCHEMA,
            "text/markdown": _TEXT_SCHEMA,
        },
    },
    **_ARTIFACT_FORMAT_RESPONSES,
}


def _pending_response(task: dict[str, object]) -> JSONResponse:
    return JSONResponse(
        ResultPendingResponse(
            status=str(task.get("status") or "pending"),
            error=task.get("error") if isinstance(task.get("error"), str) else None,
        ).model_dump(),
        status_code=202,
    )


def _successful_task_or_response(task_id: str):
    try:
        task = get_task(task_id)
    except SQLAlchemyError:
        logging.getLogger(__name__).exception("get_task failed for %s", task_id)
        task = None
    if not task:
        return None, error_json("unknown task", 404)
    if task.get("status") != "success":
        return None, _pending_response(task)
    return task, None


def _local_output_text_or_response(result: object):
    try:
        return read_local_output_text(result), None
    except MissingOutputFileError:
        return None, error_json("no output file available", 404)
    except FileNotFoundError:
        return None, error_json("output file not found", 404)
    except (OSError, UnicodeDecodeError) as exc:
        return None, error_json(str(exc), 500)


def _formatted_text_response(text: str, format: str):
    if format not in ("txt", "md"):
        return error_json("unsupported format", 400)
    return Response(
        content=text,
        media_type="text/markdown" if format == "md" else "text/plain",
    )


def _stream_minio_object(
    bucket: str,
    object_name: str,
    filename: str | None = None,
    media_type: str = "application/octet-stream",
):
    try:
        body = MinioService().iter_object(bucket, object_name)
    except (S3Error, OSError) as exc:
        return error_json(f"failed to fetch object from MinIO: {exc!s}", 502)

    headers = {}
    if filename:
        headers["Content-Disposition"] = (
            f'attachment; filename="{os.path.basename(filename)}"'
        )
    return StreamingResponse(body, media_type=media_type, headers=headers)


def _read_minio_object_text(bucket: str, object_name: str) -> str:
    return MinioService().read_object_text(bucket, object_name)


@router.get(
    "/minutes/{task_id}",
    response_class=Response,
    responses={
        200: {
            "description": "Minutes text",
            "content": {"text/plain": _TEXT_SCHEMA},
        },
        **_ARTIFACT_DOWNLOAD_RESPONSES,
    },
)
def bg_minutes_file(task_id: str):
    task, error = _successful_task_or_response(task_id)
    if error:
        return error
    result = task.get("result") or {}
    output_file = result_output_file(result)
    if not output_file:
        return error_json("no output file available", 404)

    filename = os.path.basename(output_file)
    candidate = local_output_path(output_file)
    minio_object = result_minio_object(result)
    try:
        if minio_object:
            return _stream_minio_object(
                minio_object[0],
                minio_object[1],
                filename=filename,
                media_type="text/plain",
            )
        return FileResponse(path=candidate, media_type="text/plain", filename=filename)
    except FileNotFoundError:
        return error_json("output file not found", 404)
    except OSError as exc:
        return error_json(str(exc), 500)


@router.get(
    "/transcript/{task_id}",
    response_class=Response,
    responses=_ARTIFACT_TEXT_RESPONSES,
)
def bg_transcript(task_id: str, format: str = "txt"):
    task, error = _successful_task_or_response(task_id)
    if error:
        return error
    result = task.get("result") or {}
    if isinstance(result, dict) and result.get("transcript"):
        text = result["transcript"]
    else:
        text, error = _local_output_text_or_response(result)
        if error:
            return error
    minio_object = result_minio_object(result)
    if minio_object:
        try:
            text = _read_minio_object_text(minio_object[0], minio_object[1])
        except (S3Error, OSError) as exc:
            logging.getLogger(__name__).debug(
                "MinIO transcript read failed for %s: %s",
                task_id,
                str(exc),
                exc_info=True,
            )
    return _formatted_text_response(text, format)


@router.get(
    "/summary/{task_id}",
    response_class=Response,
    responses=_ARTIFACT_TEXT_RESPONSES,
)
def bg_summary(task_id: str, format: str = "txt"):
    task, error = _successful_task_or_response(task_id)
    if error:
        return error
    result = task.get("result") or {}
    if isinstance(result, dict) and result.get("summary"):
        summary_text = result["summary"]
    else:
        text, error = _local_output_text_or_response(result)
        if error:
            return error
        match = re.search(
            r"(?ims)^\s*summary\s*$\n(.*?)\n\s*(?:action items|transcript|$)", text
        )
        if match:
            summary_text = match.group(1).strip()
        else:
            try:
                summary_text = summarize_local(text, max_sentences=3)
            except (RuntimeError, TypeError) as exc:
                logging.getLogger(__name__).debug(
                    "summarize_local failed for %s: %s",
                    task_id,
                    str(exc),
                    exc_info=True,
                )
                summary_text = ""
    return _formatted_text_response(summary_text, format)


def _minutes_text_for_actions(result: object):
    if isinstance(result, dict):
        minutes = result.get("minutes")
        if isinstance(minutes, str) and minutes.strip():
            return minutes, None
    return _local_output_text_or_response(result)


@router.get(
    "/action-items/{task_id}",
    response_model=ActionItemsResponse,
    responses={
        200: {
            "description": "Action items as JSON, CSV, or plain text",
            "content": {
                "text/csv": _TEXT_SCHEMA,
                "text/plain": _TEXT_SCHEMA,
            },
        },
        **_ARTIFACT_FORMAT_RESPONSES,
    },
)
def bg_action_items(task_id: str, format: str = "json"):
    task, error = _successful_task_or_response(task_id)
    if error:
        return error
    result = task.get("result") or {}
    items = []
    if isinstance(result, dict) and isinstance(result.get("action_items"), list):
        items = [item for item in result["action_items"] if item]
    if not items:
        text, error = _minutes_text_for_actions(result)
        if error:
            return error
        items = extract_action_items(text)
    if not items:
        items = []
    if format == "json":
        return {"task_id": task_id, "items": items}
    if format == "csv":
        buffer = io.StringIO()
        writer = csv.writer(buffer)
        writer.writerow(["id", "who", "what", "due", "text"])
        for index, item in enumerate(items, start=1):
            row = item if isinstance(item, dict) else {"text": str(item)}
            writer.writerow(
                [
                    index,
                    row.get("who", ""),
                    row.get("what", ""),
                    row.get("due", ""),
                    row.get("text", ""),
                ]
            )
        return Response(content=buffer.getvalue(), media_type="text/csv")
    if format == "txt":
        lines = []
        for item in items:
            if isinstance(item, dict):
                lines.append(f"- {item.get('text') or ''}")
            else:
                lines.append(f"- {item}")
        return Response(content="\n".join(lines), media_type="text/plain")
    return error_json("unsupported format", 400)
