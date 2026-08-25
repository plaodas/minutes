from typing import Optional, Tuple
from faster_whisper import WhisperModel


def transcribe(
    audio_path: str,
    model_size: str = "medium",
    prompt: Optional[str] = None,
    device: str = "cpu",
    raw_out: Optional[str] = None,
) -> Tuple[str, object]:
    """Transcribe audio using faster-whisper and optionally save raw transcript.

    Returns: (raw_text, segments)
    """
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
