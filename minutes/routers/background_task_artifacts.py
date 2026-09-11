import csv
import io
import logging
import os
import re

from fastapi import APIRouter
from fastapi.responses import FileResponse, JSONResponse, Response, StreamingResponse
from sqlalchemy.exc import SQLAlchemyError

from minutes.bg_store import get_task
from minutes.minio_client import MinioService
from minutes.summary import summarize_local

router = APIRouter()


def _resolve_output_file_from_task(task_id: str):
    try:
        task = get_task(task_id)
    except SQLAlchemyError:
        logging.getLogger(__name__).exception("get_task failed for %s", task_id)
        task = None
    if not task:
        return None, JSONResponse({"error": "unknown task"}, status_code=404)
    if task.get("status") != "success":
        return None, JSONResponse({"status": task.get("status")}, status_code=202)
    result = task.get("result") or {}
    output_file = None
    if isinstance(result, dict):
        output_file = result.get("output_file")
        nested = result.get("result")
        if not output_file and isinstance(nested, dict):
            output_file = nested.get("output_file")
    if not output_file:
        return None, JSONResponse(
            {"error": "no output file available"}, status_code=404
        )
    outputs_dir = os.environ.get("OUTPUTS_DIR", "outputs")
    return os.path.join(outputs_dir, os.path.basename(output_file)), None


def _stream_minio_object(
    bucket: str,
    object_name: str,
    filename: str | None = None,
    media_type: str = "application/octet-stream",
):
    service = MinioService()
    try:
        from minio.error import S3Error
    except ImportError:
        S3Error = Exception
    try:
        obj = service.client.get_object(bucket, object_name)
    except (S3Error, OSError) as exc:
        return JSONResponse(
            {"error": f"failed to fetch object from MinIO: {exc!s}"}, status_code=502
        )

    def iterfile(chunk_size: int = 32 * 1024):
        try:
            for data in obj.stream(chunk_size):
                if not data:
                    break
                yield data
        finally:
            try:
                obj.close()
            except (S3Error, OSError, AttributeError):
                logging.getLogger(__name__).debug(
                    "obj.close() failed for %s/%s", bucket, object_name, exc_info=True
                )
            try:
                obj.release_conn()
            except (S3Error, OSError, AttributeError):
                logging.getLogger(__name__).debug(
                    "obj.release_conn() failed for %s/%s",
                    bucket,
                    object_name,
                    exc_info=True,
                )

    headers = {}
    if filename:
        headers["Content-Disposition"] = (
            f'attachment; filename="{os.path.basename(filename)}"'
        )
    return StreamingResponse(iterfile(), media_type=media_type, headers=headers)


def _read_minio_object_text(bucket: str, object_name: str) -> str:
    service = MinioService()
    obj = None
    try:
        obj = service.client.get_object(bucket, object_name)
        data = obj.read()
        return data.decode("utf-8") if isinstance(data, bytes) else str(data)
    finally:
        try:
            from minio.error import S3Error
        except ImportError:
            S3Error = Exception
        if obj is not None:
            try:
                obj.close()
            except (S3Error, OSError, AttributeError):
                logging.getLogger(__name__).debug(
                    "object close failed for %s/%s", bucket, object_name, exc_info=True
                )
            try:
                obj.release_conn()
            except (S3Error, OSError, AttributeError):
                logging.getLogger(__name__).debug(
                    "object release failed for %s/%s",
                    bucket,
                    object_name,
                    exc_info=True,
                )


@router.get("/minutes/{task_id}")
def bg_minutes_file(task_id: str):
    try:
        task = get_task(task_id)
    except SQLAlchemyError:
        logging.getLogger(__name__).debug(
            "get_task failed for %s", task_id, exc_info=True
        )
        task = None
    if not task:
        return JSONResponse({"error": "unknown task"}, status_code=404)
    if task.get("status") != "success":
        return JSONResponse({"status": task.get("status")}, status_code=202)
    result = task.get("result") or {}
    output_file = None
    if isinstance(result, dict):
        output_file = result.get("output_file")
        nested = result.get("result")
        if not output_file and isinstance(nested, dict):
            output_file = nested.get("output_file")
    if not output_file:
        return JSONResponse({"error": "no output file available"}, status_code=404)

    filename = os.path.basename(output_file)
    candidate = os.path.join(os.environ.get("OUTPUTS_DIR", "outputs"), filename)
    try:
        if (
            isinstance(result, dict)
            and isinstance(result.get("minio"), dict)
            and result["minio"].get("bucket")
            and result["minio"].get("object")
        ):
            return _stream_minio_object(
                result["minio"]["bucket"],
                result["minio"]["object"],
                filename=filename,
                media_type="text/plain",
            )
        return FileResponse(path=candidate, media_type="text/plain", filename=filename)
    except FileNotFoundError:
        return JSONResponse({"error": "output file not found"}, status_code=404)
    except OSError as exc:
        return JSONResponse({"error": str(exc)}, status_code=500)


@router.get("/transcript/{task_id}")
def bg_transcript(task_id: str, format: str = "txt"):
    task = get_task(task_id)
    if not task:
        return JSONResponse({"error": "unknown task"}, status_code=404)
    if task.get("status") != "success":
        return JSONResponse({"status": task.get("status")}, status_code=202)
    result = task.get("result") or {}
    if isinstance(result, dict) and result.get("transcript"):
        text = result["transcript"]
    else:
        candidate, error = _resolve_output_file_from_task(task_id)
        if error:
            return error
        try:
            with open(candidate, "r", encoding="utf-8") as input_file:
                text = input_file.read()
        except FileNotFoundError:
            return JSONResponse({"error": "output file not found"}, status_code=404)
        except (OSError, UnicodeDecodeError) as exc:
            return JSONResponse({"error": str(exc)}, status_code=500)
    if (
        isinstance(result, dict)
        and isinstance(result.get("minio"), dict)
        and result["minio"].get("bucket")
        and result["minio"].get("object")
    ):
        try:
            text = _read_minio_object_text(
                result["minio"]["bucket"], result["minio"]["object"]
            )
        except (OSError, ImportError) as exc:
            logging.getLogger(__name__).debug(
                "MinIO transcript read failed for %s: %s",
                task_id,
                str(exc),
                exc_info=True,
            )
    if format not in ("txt", "md"):
        return JSONResponse({"error": "unsupported format"}, status_code=400)
    return Response(
        content=text, media_type="text/markdown" if format == "md" else "text/plain"
    )


@router.get("/summary/{task_id}")
def bg_summary(task_id: str, format: str = "txt"):
    task = get_task(task_id)
    if not task:
        return JSONResponse({"error": "unknown task"}, status_code=404)
    if task.get("status") != "success":
        return JSONResponse({"status": task.get("status")}, status_code=202)
    result = task.get("result") or {}
    if isinstance(result, dict) and result.get("summary"):
        summary_text = result["summary"]
    else:
        candidate, error = _resolve_output_file_from_task(task_id)
        if error:
            return error
        try:
            with open(candidate, "r", encoding="utf-8") as input_file:
                text = input_file.read()
        except FileNotFoundError:
            return JSONResponse({"error": "output file not found"}, status_code=404)
        except (OSError, UnicodeDecodeError) as exc:
            return JSONResponse({"error": str(exc)}, status_code=500)
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
    if format not in ("txt", "md"):
        return JSONResponse({"error": "unsupported format"}, status_code=400)
    return Response(
        content=summary_text,
        media_type="text/markdown" if format == "md" else "text/plain",
    )


@router.get("/action-items/{task_id}")
def bg_action_items(task_id: str, format: str = "json"):
    task = get_task(task_id)
    if not task:
        return JSONResponse({"error": "unknown task"}, status_code=404)
    if task.get("status") != "success":
        return JSONResponse({"status": task.get("status")}, status_code=202)
    result = task.get("result") or {}
    if isinstance(result, dict) and isinstance(result.get("action_items"), list):
        items = result["action_items"]
    else:
        candidate, error = _resolve_output_file_from_task(task_id)
        if error:
            return error
        try:
            with open(candidate, "r", encoding="utf-8") as input_file:
                text = input_file.read()
        except FileNotFoundError:
            return JSONResponse({"error": "output file not found"}, status_code=404)
        except (OSError, UnicodeDecodeError) as exc:
            return JSONResponse({"error": str(exc)}, status_code=500)
        items = []
        match = re.search(r"(?ims)^\s*action items\s*$\n(.*)$", text)
        section = match.group(1) if match else None
        if not section:
            for line in (line.strip() for line in text.splitlines() if line.strip()):
                if re.search(r"\b(Action|TODO|Action Item)[:\-]", line, re.IGNORECASE):
                    items.append({"text": line})
        else:
            for line in section.splitlines():
                item = line.strip().lstrip("-•* ")
                if item and not re.match(r"^[A-Z][a-z]+:$", item):
                    items.append({"text": item})
    if not items:
        items = []
    if format == "json":
        return JSONResponse({"task_id": task_id, "items": items})
    if format == "csv":
        buffer = io.StringIO()
        writer = csv.writer(buffer)
        writer.writerow(["id", "text"])
        for index, item in enumerate(items, start=1):
            writer.writerow([index, item.get("text")])
        return Response(content=buffer.getvalue(), media_type="text/csv")
    if format == "txt":
        text = "\n".join([f"- {item.get('text')}" for item in items])
        return Response(content=text, media_type="text/plain")
    return JSONResponse({"error": "unsupported format"}, status_code=400)
