import wave

import pytest

from minutes.pipeline.audio import PreparedAudio, prepare_audio


def _write_wav(path, duration_seconds=0.02):
    with wave.open(str(path), "wb") as output:
        output.setnchannels(1)
        output.setsampwidth(2)
        output.setframerate(16000)
        output.writeframes(b"\x00\x00" * int(16000 * duration_seconds))


def test_prepare_audio_returns_validated_paths_and_duration(tmp_path):
    mono = tmp_path / "mono.wav"
    normalized = tmp_path / "normalized.wav"
    clean = tmp_path / "clean.wav"
    for path in (mono, normalized, clean):
        _write_wav(path)

    result = prepare_audio(
        "input.wav",
        lambda _path: (str(mono), str(normalized), str(clean)),
    )

    assert result == PreparedAudio(
        mono=str(mono),
        normalized=str(normalized),
        clean=str(clean),
        sample_rate=16000,
        duration_seconds=pytest.approx(0.02),
    )


def test_prepare_audio_rejects_invalid_clean_wav(tmp_path):
    clean = tmp_path / "clean.wav"
    clean.write_text("not wav", encoding="utf-8")

    with pytest.raises(RuntimeError, match="Invalid data found"):
        prepare_audio(
            "input.wav",
            lambda _path: ("mono.wav", "normalized.wav", str(clean)),
        )
