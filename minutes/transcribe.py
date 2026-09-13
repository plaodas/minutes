from collections.abc import Callable, Iterable
from typing import Any


def jsonable_segment(segment: object) -> object:
    """Return a JSON-serializable form of a faster-whisper Segment or dict."""
    if isinstance(segment, dict):
        return segment
    start = getattr(segment, "start", None)
    end = getattr(segment, "end", None)
    text = getattr(segment, "text", None)
    if start is None and end is None and text is None:
        return str(segment)
    payload: dict[str, Any] = {}
    if start is not None:
        payload["start"] = start
    if end is not None:
        payload["end"] = end
    if text is not None:
        payload["text"] = text
    return payload


def jsonable_segments(segments: Iterable[object] | object) -> list[Any]:
    if isinstance(segments, list):
        items = segments
    elif segments is None:
        items = []
    else:
        items = list(segments)
    return [jsonable_segment(item) for item in items]


def transcribe(
    audio_path: str,
    model_size: str = "medium",
    prompt: str | None = None,
    device: str = "cpu",
    raw_out: str | None = None,
    progress_callback: Callable[[Any], None] | None = None,
) -> tuple[str, object]:
    """Transcribe audio using faster-whisper and optionally save raw transcript.

    Delays importing `faster_whisper` so the API can start without heavy
    dependencies. If `faster_whisper` is not installed, a RuntimeError is raised
    at call time with instructions.
    """
    try:
        from faster_whisper import WhisperModel
    except ImportError as e:
        raise RuntimeError(
            "faster_whisper is not installed in this environment. "
            "Install full dependencies or use the minimal API image. "
            "To install: pip install faster-whisper"
        ) from e

    model = WhisperModel(model_size, device=device)

    segments, _info = model.transcribe(
        audio_path,
        language="ja",
        initial_prompt=prompt,
        beam_size=5,
        vad_filter=True,
    )

    # `segments` may be a generator; iterate and optionally call progress callback
    seg_list = []
    for seg in segments:
        seg_list.append(seg)
        if progress_callback is not None:
            try:
                progress_callback(seg)
            except (TypeError, AttributeError, RuntimeError, ValueError):
                # ignore callback errors that can reasonably occur
                pass

    raw_text = "\n".join([seg.text for seg in seg_list])
    seg_list = jsonable_segments(seg_list)

    if raw_out:
        with open(raw_out, "w", encoding="utf-8") as f:
            f.write(raw_text)

    return raw_text, seg_list
