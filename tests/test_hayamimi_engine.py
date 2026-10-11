import pytest
from fastapi.testclient import TestClient

from minutes import hayamimi_engine
from minutes.api import app
from minutes.hayamimi_engine import collect_vad_segments, transcribe_with_hayamimi
from minutes.transcribe import transcribe


class _Segment:
    def __init__(self, start: int, samples: list[float], text: str):
        self.start = start
        self.samples = samples
        self.text = text


class _Vad:
    def __init__(self, ready: list[_Segment]):
        self._ready = ready
        self._queue: list[_Segment] = []
        self.accepted: list[object] = []

    def accept_waveform(self, chunk: object) -> None:
        self.accepted.append(chunk)
        if self._ready:
            self._queue.append(self._ready.pop(0))

    def flush(self) -> None:
        self._queue.extend(self._ready)
        self._ready = []

    def empty(self) -> bool:
        return not self._queue

    @property
    def front(self) -> _Segment:
        return self._queue[0]

    def pop(self) -> None:
        self._queue.pop(0)


class _Asr:
    def transcribe(self, audio: object, sample_rate: int) -> dict[str, str]:
        del sample_rate
        if len(audio) == 4:
            return {"text": "こんにちは"}
        return {"text": "  "}


def test_collect_vad_segments_uses_sample_times():
    speech = _Segment(16000, [0.1, 0.2, 0.3, 0.4], "こんにちは")
    blank = _Segment(32000, [0.0], "  ")
    vad = _Vad([speech, blank])
    seen = []
    segments = collect_vad_segments(
        vad,
        _Asr(),
        [0.0] * 8,
        16000,
        4,
        progress_callback=seen.append,
    )

    assert [(item.start, item.end, item.text) for item in segments] == [
        (1.0, 1.0 + 4 / 16000, "こんにちは")
    ]
    assert seen == segments
    assert len(vad.accepted) == 2


def test_hayamimi_disabled_fails_without_whisper(monkeypatch):
    monkeypatch.delenv("HAYAMIMI_ENABLED", raising=False)
    with pytest.raises(RuntimeError, match="hayamimi is not enabled"):
        transcribe("meeting.wav", language="Japanese", engine="hayamimi")


def test_hayamimi_missing_install_fails(monkeypatch, tmp_path):
    monkeypatch.setenv("HAYAMIMI_ENABLED", "1")
    monkeypatch.setenv("HAYAMIMI_ROOT", str(tmp_path / "missing"))
    hayamimi_engine._RUNTIME = None
    with pytest.raises(RuntimeError, match="not installed"):
        transcribe_with_hayamimi("meeting.wav")


def test_hayamimi_resets_session_between_files(monkeypatch):
    monkeypatch.setenv("HAYAMIMI_ENABLED", "1")
    hayamimi_engine._RUNTIME = None

    class Session:
        def __init__(self):
            self.resets = 0

        def reset_session(self):
            self.resets += 1

        def transcribe(self, audio, sample_rate):
            del audio, sample_rate
            return {"text": ""}

    class EmptyVad:
        def accept_waveform(self, chunk):
            del chunk

        def empty(self):
            return True

        def flush(self):
            return None

    session = Session()
    monkeypatch.setattr(
        hayamimi_engine,
        "_load_runtime",
        lambda: (session, EmptyVad, lambda path, rate: ([0.0] * 4, 16000), 16000, 4),
    )

    transcribe_with_hayamimi("a.wav")
    transcribe_with_hayamimi("b.wav")
    assert session.resets == 2


def test_health_reports_hayamimi_flag(monkeypatch):
    monkeypatch.delenv("HAYAMIMI_ENABLED", raising=False)
    client = TestClient(app)
    assert client.get("/api/health").json() == {"status": "ok", "hayamimi": False}

    monkeypatch.setenv("HAYAMIMI_ENABLED", "yes")
    assert client.get("/api/health").json() == {"status": "ok", "hayamimi": True}
