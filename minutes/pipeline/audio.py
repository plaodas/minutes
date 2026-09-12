import contextlib
import logging
import os
import subprocess
import time
import wave
from collections.abc import Callable
from dataclasses import dataclass

Preprocessor = Callable[[str], tuple[str, str, str]]
logger = logging.getLogger("minutes.pipeline.audio")


@dataclass(frozen=True)
class PreparedAudio:
    mono: str
    normalized: str
    clean: str
    sample_rate: int
    duration_seconds: float | None


def _wav_duration(path: str) -> float | None:
    try:
        with contextlib.closing(wave.open(path, "rb")) as audio:
            return audio.getnframes() / float(audio.getframerate())
    except (EOFError, wave.Error, OSError, ZeroDivisionError) as exc:
        logger.debug("wave.open failed for %s: %s", path, exc)
        try:
            output = subprocess.check_output(
                [
                    "ffprobe",
                    "-v",
                    "error",
                    "-show_entries",
                    "format=duration",
                    "-of",
                    "default=noprint_wrappers=1:nokey=1",
                    path,
                ],
                stderr=subprocess.DEVNULL,
            )
            return float(output.strip())
        except (subprocess.CalledProcessError, OSError, ValueError, TypeError):
            logger.debug("ffprobe fallback failed for %s", path, exc_info=True)
            return None


def prepare_audio(input_path: str, preprocessor: Preprocessor) -> PreparedAudio:
    try:
        input_exists = os.path.exists(input_path)
        input_size = os.path.getsize(input_path) if input_exists else None
    except OSError:
        input_exists = False
        input_size = None
    logger.info(
        "preprocess start input=%s exists=%s size=%s cwd=%s",
        input_path,
        input_exists,
        input_size,
        os.getcwd(),
    )

    started_at = time.monotonic()
    mono, normalized, clean = preprocessor(input_path)
    logger.info(
        "preprocess completed in %.2fs -> mono=%s normalized=%s clean=%s",
        time.monotonic() - started_at,
        mono,
        normalized,
        clean,
    )
    for path in (mono, normalized, clean):
        try:
            size = os.path.getsize(path) if path and os.path.exists(path) else None
        except OSError:
            size = None
        logger.debug(
            "preprocess output %s exists=%s size=%s",
            path,
            bool(path and os.path.exists(path)),
            size,
        )

    try:
        if not clean or not os.path.exists(clean) or os.path.getsize(clean) == 0:
            raise RuntimeError(f"Invalid data found when processing input: '{clean}'")
        with contextlib.closing(wave.open(clean, "rb")) as audio:
            sample_rate = audio.getframerate()
    except (EOFError, wave.Error, OSError) as exc:
        raise RuntimeError(
            f"Invalid data found when processing input: '{clean}'"
        ) from exc

    if sample_rate and sample_rate != 16000:
        logger.warning("Unexpected sample rate %s Hz for %s", sample_rate, clean)
    duration = _wav_duration(clean)
    logger.info("Determined audio_duration=%s for %s", duration, clean)
    return PreparedAudio(
        mono=mono,
        normalized=normalized,
        clean=clean,
        sample_rate=sample_rate,
        duration_seconds=duration,
    )
