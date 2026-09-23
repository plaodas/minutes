import sys

from minutes.transcribe import transcribe, whisper_language


def test_whisper_language_maps_upload_labels():
    assert whisper_language("Japanese") == "ja"
    assert whisper_language("ja") == "ja"
    assert whisper_language("English") == "en"
    assert whisper_language("en") == "en"
    assert whisper_language("Auto-detect") is None
    assert whisper_language(None) == "ja"
    assert whisper_language("") == "ja"


def test_transcribe_passes_resolved_language(monkeypatch):
    captured = {}

    class FakeModel:
        def __init__(self, model_size, device):
            captured["model_size"] = model_size
            captured["device"] = device

        def transcribe(self, audio_path, **kwargs):
            captured["audio_path"] = audio_path
            captured.update(kwargs)
            return [], None

    class FakeFasterWhisper:
        WhisperModel = FakeModel

    monkeypatch.setitem(sys.modules, "faster_whisper", FakeFasterWhisper)

    raw_text, segments = transcribe("meeting.wav", language="English")

    assert raw_text == ""
    assert segments == []
    assert captured["language"] == "en"
    assert captured["beam_size"] == 5
    assert captured["vad_filter"] is True


def test_transcribe_defaults_to_japanese(monkeypatch):
    captured = {}

    class FakeModel:
        def __init__(self, model_size, device):
            del model_size, device

        def transcribe(self, audio_path, **kwargs):
            captured.update(kwargs)
            return [], None

    class FakeFasterWhisper:
        WhisperModel = FakeModel

    monkeypatch.setitem(sys.modules, "faster_whisper", FakeFasterWhisper)

    transcribe("meeting.wav", language="Auto-detect")
    assert captured["language"] is None

    transcribe("meeting.wav")
    assert captured["language"] == "ja"
