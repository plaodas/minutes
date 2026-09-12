import os
import shutil
import time
import uuid
from collections.abc import Callable
from typing import Any

from fastapi import HTTPException, UploadFile
from fastapi.responses import JSONResponse
from sqlalchemy.exc import SQLAlchemyError

from . import tasks
from .request_auth import parse_header_user_id

CreateTask = Callable[..., None]

ALLOWED_EXTENSIONS = {".wav", ".mp3", ".m4a", ".flac", ".ogg", ".opus"}


def _is_allowed_upload(file: UploadFile) -> tuple[bool, str]:
    filename = file.filename or ""
    extension = os.path.splitext(filename)[1].lower()
    content_type = file.content_type or ""
    if extension not in ALLOWED_EXTENSIONS and not content_type.startswith("audio/"):
        return False, f"invalid file type: ext={extension!r} mime={content_type!r}"

    stream = getattr(file, "file", None)
    if not stream:
        return False, "missing upload stream"
    try:
        position = stream.tell()
    except (OSError, AttributeError):
        position = None
    header = stream.read(4096) or b""
    try:
        stream.seek(position if position is not None else 0)
    except (OSError, ValueError):
        pass

    try:
        import magic

        try:
            mime = magic.Magic(mime=True).from_buffer(header)
        except (AttributeError, TypeError):
            mime = magic.from_buffer(header)
        if isinstance(mime, str) and mime.startswith("audio/"):
            return True, ""
        return (
            False,
            (
                f"invalid mime detected: {mime!r} ext={extension!r} "
                f"orig_mime={content_type!r}"
            ),
        )
    except ImportError:
        value = (
            header
            if isinstance(header, (bytes, bytearray))
            else str(header).encode("latin1", errors="ignore")
        )
        is_audio = (
            (value.startswith(b"RIFF") and value[8:12] == b"WAVE")
            or value.startswith((b"OggS", b"fLaC", b"ID3"))
            or (len(value) >= 2 and value[0] == 0xFF and (value[1] & 0xE0) == 0xE0)
            or (len(value) >= 12 and value[4:8] == b"ftyp")
        )
        if is_audio:
            return True, ""
        return (
            False,
            (
                "file signature did not match audio formats: "
                f"ext={extension!r} mime={content_type!r}"
            ),
        )


def _metadata(
    filename: str,
    language: str | None,
    include_actions: str | None,
) -> dict[str, Any]:
    metadata: dict[str, Any] = {"upload_filename": filename}
    if language:
        metadata["language"] = language
    if include_actions is not None:
        try:
            metadata["include_actions"] = bool(int(include_actions))
        except (ValueError, TypeError):
            metadata["include_actions"] = include_actions in {"1", "true", "True"}
    return metadata


def handle_audio_upload(
    file: UploadFile,
    *,
    x_user_id: str | None,
    authorization: str | None,
    language: str | None,
    include_actions: str | None,
    create_task_record: CreateTask,
    include_filename: bool,
) -> dict[str, Any] | JSONResponse:
    allowed, reason = _is_allowed_upload(file)
    if not allowed:
        return JSONResponse({"error": reason}, status_code=400)

    uploads_dir = os.environ.get("UPLOADS_DIR", "uploads")
    os.makedirs(uploads_dir, exist_ok=True)
    filename = os.path.basename(file.filename) or "upload.wav"
    unique_name = (
        f"{int(time.time())}-{uuid.uuid4().hex}{os.path.splitext(filename)[1]}"
    )
    destination = os.path.join(uploads_dir, unique_name)

    try:
        with open(destination, "wb") as output:
            shutil.copyfileobj(file.file, output)

        processor = tasks.process_audio
        task = (
            processor.delay(destination)
            if hasattr(processor, "delay")
            else processor(destination)
        )
        owner = parse_header_user_id(x_user_id, authorization)
        create_task_record(
            task.id,
            metadata=_metadata(filename, language, include_actions),
            user_id=str(owner) if owner else None,
        )
    except (OSError, AttributeError, RuntimeError, ValueError, SQLAlchemyError) as exc:
        raise HTTPException(status_code=500, detail=str(exc))

    response: dict[str, Any] = {"task_id": task.id}
    if include_filename:
        response["upload_filename"] = filename
    return response
