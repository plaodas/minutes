import os
import subprocess


def _run_ffmpeg(command: list[str]) -> None:
    try:
        subprocess.run(command, check=True)
    except subprocess.CalledProcessError as exc:
        raise RuntimeError(
            f"ffmpeg failed with exit code {exc.returncode}: {exc.cmd}"
        ) from exc


def preprocess(input_file: str) -> tuple[str, str, str]:
    """Run ffmpeg-based preprocessing and return (mono_file, norm_file, clean_file)."""
    base = os.path.splitext(input_file)[0]
    mono_file = f"{base}_mono.wav"
    norm_file = f"{base}_norm.wav"
    clean_file = f"{base}_clean.wav"

    # Produce mono WAV at a controlled sample rate to avoid upsampling.
    _run_ffmpeg(
        ["ffmpeg", "-y", "-i", input_file, "-ac", "1", "-ar", "16000", mono_file]
    )
    # Normalize loudness and keep sample rate stable.
    _run_ffmpeg(
        ["ffmpeg", "-y", "-i", mono_file, "-ar", "16000", "-af", "loudnorm", norm_file]
    )
    # Apply a highpass filter and keep the output sample rate at 16kHz.
    _run_ffmpeg(
        [
            "ffmpeg",
            "-y",
            "-i",
            norm_file,
            "-ar",
            "16000",
            "-af",
            "highpass=f=120",
            clean_file,
        ]
    )

    return mono_file, norm_file, clean_file
