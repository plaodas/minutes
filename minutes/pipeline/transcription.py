import json
import logging
import os
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from requests.exceptions import ChunkedEncodingError, RequestException
from sqlalchemy.exc import SQLAlchemyError

Transcriber = Callable[..., tuple[str, object]]
StatusUpdater = Callable[[str], None]
ProgressUpdater = Callable[[float], None]
HttpPost = Callable[..., Any]
Sleeper = Callable[[float], None]
logger = logging.getLogger("minutes.pipeline.transcription")


@dataclass(frozen=True)
class TranscriptionResult:
    raw_text: str
    segments: list[Any]


def _report_progress(
    end: object,
    duration_seconds: float | None,
    update_status: StatusUpdater,
    update_progress: ProgressUpdater,
) -> None:
    try:
        end_seconds = float(end or 0.0)
        update_status(f"transcribing:{end_seconds:.1f}s")
        if duration_seconds and duration_seconds > 0:
            update_progress(min(100.0, (end_seconds / duration_seconds) * 100.0))
    except (ValueError, TypeError, SQLAlchemyError):
        pass


def _parse_events(
    lines: object,
    duration_seconds: float | None,
    update_status: StatusUpdater,
    update_progress: ProgressUpdater,
) -> TranscriptionResult:
    raw_text = ""
    segments: list[Any] = []
    for line in lines:
        if not line:
            continue
        try:
            event = json.loads(line)
        except (json.JSONDecodeError, TypeError):
            logger.debug("Ignoring invalid inference event: %r", str(line)[:200])
            continue

        event_type = event.get("type")
        if event_type == "heartbeat":
            continue
        if event_type == "segment":
            _report_progress(
                event.get("end"),
                duration_seconds,
                update_status,
                update_progress,
            )
            segments.append(event)
        elif event_type == "final":
            raw_text = event.get("raw_text") or ""
            if isinstance(event.get("segments"), list):
                segments = event["segments"]
            update_progress(100.0)
        elif event_type == "error":
            raise RuntimeError(event.get("error"))
    return TranscriptionResult(raw_text=raw_text, segments=segments)


def transcribe_locally(
    audio_path: str,
    *,
    duration_seconds: float | None,
    transcriber: Transcriber,
    update_status: StatusUpdater,
    update_progress: ProgressUpdater,
) -> TranscriptionResult:
    def report_progress(segment: object) -> None:
        _report_progress(
            getattr(segment, "end", 0.0),
            duration_seconds,
            update_status,
            update_progress,
        )

    raw_text, segments = transcriber(
        audio_path,
        model_size="small",
        prompt=None,
        progress_callback=report_progress,
    )
    update_progress(100.0)
    return TranscriptionResult(
        raw_text=raw_text,
        segments=segments if isinstance(segments, list) else list(segments),
    )


def transcribe_remotely(
    audio_path: str,
    *,
    inference_url: str,
    duration_seconds: float | None,
    post: HttpPost,
    update_status: StatusUpdater,
    update_progress: ProgressUpdater,
    sleep: Sleeper = time.sleep,
    max_attempts: int = 3,
) -> TranscriptionResult:
    backoff = 1.0
    last_error: Exception | None = None
    for attempt in range(1, max_attempts + 1):
        try:
            with open(audio_path, "rb") as audio:
                response = post(
                    inference_url,
                    files={"file": (os.path.basename(audio_path), audio, "audio/wav")},
                    stream=True,
                    timeout=(5, 360),
                    headers={"Connection": "keep-alive"},
                )
                response.raise_for_status()
                return _parse_events(
                    response.iter_lines(decode_unicode=True, chunk_size=1024),
                    duration_seconds,
                    update_status,
                    update_progress,
                )
        except (ChunkedEncodingError, RequestException, OSError) as exc:
            last_error = exc
            logger.exception("Streaming inference failed on attempt %s", attempt)

        try:
            with open(audio_path, "rb") as audio:
                response = post(
                    inference_url,
                    files={"file": (os.path.basename(audio_path), audio, "audio/wav")},
                    timeout=(5, 300),
                    headers={"Connection": "keep-alive"},
                )
                response.raise_for_status()
                return _parse_events(
                    (response.text or "").splitlines(),
                    duration_seconds,
                    update_status,
                    update_progress,
                )
        except (ChunkedEncodingError, RequestException, OSError) as exc:
            last_error = exc
            logger.exception("Fallback inference failed on attempt %s", attempt)

        if attempt < max_attempts:
            sleep(backoff)
            backoff = min(60.0, backoff * 2)

    if last_error:
        raise last_error
    raise RuntimeError("Inference failed without a response")
