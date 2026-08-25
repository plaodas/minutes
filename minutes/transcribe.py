from typing import Optional, Tuple


def transcribe(
    audio_path: str,
    model_size: str = "medium",
    prompt: Optional[str] = None,
    device: str = "cpu",
    raw_out: Optional[str] = None,
) -> Tuple[str, object]:
    """Transcribe audio using faster-whisper and optionally save raw transcript.

    Delays importing `faster_whisper` so the API can start without heavy
    dependencies. If `faster_whisper` is not installed, a RuntimeError is raised
    at call time with instructions.
    """
    try:
        from faster_whisper import WhisperModel
    except Exception as e:
        raise RuntimeError(
            "faster_whisper is not installed in this environment. "
            "Install full dependencies or use the minimal API image. "
            "To install: pip install faster-whisper"
        ) from e

    model = WhisperModel(model_size, device=device)

    segments, info = model.transcribe(
        audio_path,
        language="ja",
        initial_prompt=prompt,
        beam_size=5,
        vad_filter=True,
    )

    raw_text = "\n".join([seg.text for seg in segments])

    if raw_out:
        with open(raw_out, "w", encoding="utf-8") as f:
            f.write(raw_text)

    return raw_text, segments
