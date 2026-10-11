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
    speaker = getattr(segment, "speaker", None)
    if isinstance(speaker, str) and speaker.strip():
        payload["speaker"] = speaker.strip()
    return payload


_AUTO_LANGUAGES = {"auto", "auto-detect", "auto detect"}


def whisper_language(language: object) -> str | None:
    """Map an upload language label to a faster-whisper language code.

    Japanese stays ``ja`` and English becomes ``en``. Auto-detect returns
    ``None`` so Whisper chooses the spoken language. A missing label keeps
    the historical Japanese default.
    """
    if not isinstance(language, str) or not language.strip():
        return "ja"
    normalized = language.strip().lower()
    if normalized in _AUTO_LANGUAGES:
        return None
    if normalized in {"en", "eng", "english"}:
        return "en"
    return "ja"


def jsonable_segments(segments: Iterable[object] | object) -> list[Any]:
    if isinstance(segments, list):
        items = segments
    elif segments is None:
        items = []
    else:
        items = list(segments)
    return [jsonable_segment(item) for item in items]


def use_hayamimi(engine: object, language: object) -> bool:
    """True only for an explicit hayamimi request whose language resolves to Japanese."""
    if not isinstance(engine, str) or engine.strip().lower() != "hayamimi":
        return False
    return whisper_language(language) == "ja"


def transcribe(
    audio_path: str,
    model_size: str = "medium",
    prompt: str | None = None,
    device: str = "cpu",
    raw_out: str | None = None,
    progress_callback: Callable[[Any], None] | None = None,
    language: str | None = None,
    engine: str | None = None,
) -> tuple[str, object]:
    """Transcribe audio and optionally save the raw transcript.

    Japanese audio can use hayamimi when ``engine`` is ``hayamimi``. Every
    other request uses faster-whisper. Import of either engine is delayed so
    the API can start without the worker dependencies.
    """
    if use_hayamimi(engine, language):
        from minutes.hayamimi_engine import transcribe_with_hayamimi

        raw_text, seg_list = transcribe_with_hayamimi(
            audio_path,
            progress_callback=progress_callback,
        )
    else:
        raw_text, seg_list = _transcribe_whisper(
            audio_path,
            model_size=model_size,
            prompt=prompt,
            device=device,
            progress_callback=progress_callback,
            language=language,
        )

    seg_list = jsonable_segments(seg_list)

    if raw_out:
        with open(raw_out, "w", encoding="utf-8") as f:
            f.write(raw_text)

    return raw_text, seg_list


def _transcribe_whisper(
    audio_path: str,
    *,
    model_size: str,
    prompt: str | None,
    device: str,
    progress_callback: Callable[[Any], None] | None,
    language: str | None,
) -> tuple[str, list[Any]]:
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
        language=whisper_language(language),
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
    return raw_text, seg_list
