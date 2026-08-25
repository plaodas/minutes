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
    subprocess.run([
        "ffmpeg", "-y",
        "-i", input_file,
        "-ac", "1",
        mono_file
    ], check=True)

    # 2. 音量正規化（loudnorm）
    subprocess.run([
        "ffmpeg", "-y",
        "-i", mono_file,
        "-af", "loudnorm",
        norm_file
    ], check=True)

    # 3. ハイパスフィルタ
    subprocess.run([
        "ffmpeg", "-y",
        "-i", norm_file,
        "-af", "highpass=f=120",
        clean_file
    ], check=True)

    return mono_file, norm_file, clean_file
