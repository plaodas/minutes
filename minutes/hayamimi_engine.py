"""Optional Japanese transcription through hayamimi.

The engine is loaded once per worker process. Tasks in that process run one
at a time so they do not share the recognizer. Session language state is
cleared before each file. Speaker labels, translation, and the refine pass
are not used: refine merges several utterances into one line, which would
collapse the segments a person labels by hand.
"""

import os
import sys
import threading
from types import SimpleNamespace
from typing import Any

_LOCK = threading.Lock()
_RUNTIME: tuple[Any, Any, Any, int, int] | None = None


def hayamimi_enabled() -> bool:
    """True when this process should offer or run hayamimi."""
    value = os.environ.get("HAYAMIMI_ENABLED", "")
    return value.strip().lower() in {"1", "true", "yes"}


def transcribe_with_hayamimi(
    audio_path: str,
    progress_callback: Any = None,
) -> tuple[str, list[Any]]:
    """Transcribe a 16 kHz WAV and return text plus timed segments.

    Raises RuntimeError when hayamimi is disabled, not installed, or its
    models cannot be loaded. Callers must not fall back to Whisper.
    """
    if not hayamimi_enabled():
        raise RuntimeError("hayamimi is not enabled")

    with _LOCK:
        asr, build_vad, read_wave, sample_rate, window = _load_runtime()
        reset = getattr(asr, "reset_session", None)
        if reset is not None:
            reset()
        samples, rate = read_wave(audio_path, sample_rate)
        vad = build_vad()
        segments = collect_vad_segments(
            vad,
            asr,
            samples,
            rate,
            window,
            progress_callback,
        )
    raw_text = "\n".join(segment.text for segment in segments)
    return raw_text, segments


def collect_vad_segments(
    vad: Any,
    asr: Any,
    samples: Any,
    sample_rate: int,
    window: int,
    progress_callback: Any = None,
) -> list[SimpleNamespace]:
    """Feed samples through a VAD and keep each non-empty final."""
    segments: list[SimpleNamespace] = []
    offset = 0
    total = len(samples)

    def consume() -> None:
        while not vad.empty():
            segment = vad.front
            audio = segment.samples
            start_sample = int(segment.start)
            count = len(audio)
            vad.pop()
            result = asr.transcribe(audio, sample_rate)
            text = _result_text(result)
            if not text:
                continue
            item = SimpleNamespace(
                start=start_sample / float(sample_rate),
                end=(start_sample + count) / float(sample_rate),
                text=text,
            )
            segments.append(item)
            if progress_callback is not None:
                progress_callback(item)

    while offset < total:
        chunk = samples[offset : offset + window]
        offset += len(chunk)
        if len(chunk) < window:
            chunk = _pad_chunk(chunk, window)
        vad.accept_waveform(chunk)
        consume()
    vad.flush()
    consume()
    return segments


def _result_text(result: object) -> str:
    if isinstance(result, dict):
        return str(result.get("text") or "").strip()
    if isinstance(result, str):
        return result.strip()
    return ""


def _pad_chunk(chunk: Any, window: int) -> Any:
    try:
        import numpy as np
    except ImportError:
        padded = list(chunk)
        padded.extend([0.0] * (window - len(padded)))
        return padded
    array = np.asarray(chunk, dtype=np.float32)
    if len(array) >= window:
        return array
    return np.pad(array, (0, window - len(array)))


def _load_runtime() -> tuple[Any, Any, Any, int, int]:
    global _RUNTIME
    if _RUNTIME is not None:
        return _RUNTIME

    root = os.environ.get("HAYAMIMI_ROOT", "/opt/hayamimi")
    scripts = os.path.join(root, "scripts")
    if not os.path.isdir(scripts):
        raise RuntimeError(f"hayamimi is not installed under {root}")
    if scripts not in sys.path:
        sys.path.insert(0, scripts)
    try:
        from asr_engine import RoutedASR
        from realtime_transcribe import (
            SAMPLE_RATE,
            WINDOW_SIZE,
            build_vad,
            read_wave,
        )
    except ImportError as exc:
        raise RuntimeError(f"hayamimi dependencies are missing: {exc}") from exc
    try:
        asr = RoutedASR(
            forced_lang="ja",
            punctuate=True,
            warmup=True,
            preload=False,
        )
    except Exception as exc:
        raise RuntimeError(f"hayamimi models are missing: {exc}") from exc
    _RUNTIME = (asr, build_vad, read_wave, SAMPLE_RATE, WINDOW_SIZE)
    return _RUNTIME
