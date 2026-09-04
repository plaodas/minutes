import os
import subprocess
from typing import Tuple


def preprocess(input_file: str) -> Tuple[str, str, str]:
    """Run ffmpeg-based preprocessing and return (mono_file, norm_file, clean_file).

    Keeps behavior compatible with the old `preprocess_audio.py` script.
    """
    base = os.path.splitext(input_file)[0]
    mono_file = f"{base}_mono.wav"
    norm_file = f"{base}_norm.wav"
    clean_file = f"{base}_clean.wav"

    # 1. モノラル化
    # Produce mono WAV at a controlled sample rate to avoid upsampling
    subprocess.run([
        "ffmpeg", "-y",
        "-i", input_file,
        "-ac", "1",
        "-ar", "16000",
        mono_file
    ], check=True)

    # 2. 音量正規化（loudnorm）
    # Normalize loudness and keep sample rate stable
    subprocess.run([
        "ffmpeg", "-y",
        "-i", mono_file,
        "-ar", "16000",
        "-af", "loudnorm",
        norm_file
    ], check=True)

    # 3. ハイパスフィルタ
    # Apply highpass filter and ensure output sample rate remains 16kHz
    subprocess.run([
        "ffmpeg", "-y",
        "-i", norm_file,
        "-ar", "16000",
        "-af", "highpass=f=120",
        clean_file
    ], check=True)

    return mono_file, norm_file, clean_file
