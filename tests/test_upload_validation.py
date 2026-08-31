import io
import wave

from fastapi.testclient import TestClient

from backend.app import app


def make_wav_bytes(duration_seconds: float = 0.1) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(16000)
        frames = int(16000 * duration_seconds)
        w.writeframes(b"\x00\x00" * frames)
    buf.seek(0)
    return buf.read()


class DummyTask:
    def __init__(self, id):
        self.id = id


def test_reject_non_audio(monkeypatch):
    client = TestClient(app)
    # ensure background enqueue is mocked so test is fast and doesn't hit workers
    from minutes import tasks

    monkeypatch.setattr(tasks, "process_audio", lambda path: DummyTask("fake-id"))

    files = {"file": ("test.md", io.BytesIO(b"not audio"), "text/plain")}
    r = client.post("/transcribe-upload-bg", files=files)
    assert r.status_code == 400


def test_accept_wav_bg(monkeypatch):
    client = TestClient(app)
    from minutes import tasks

    # mock process_audio.delay or process_audio depending on implementation
    def fake_delay(path):
        return DummyTask("bg-fake-id")

    # some code paths call process_audio.delay (celery) or process_audio directly
    if hasattr(tasks.process_audio, "delay"):
        monkeypatch.setattr(tasks.process_audio, "delay", fake_delay)
    else:
        monkeypatch.setattr(tasks, "process_audio", lambda path: DummyTask("bg-fake-id"))

    wav = make_wav_bytes()
    files = {"file": ("test.wav", io.BytesIO(wav), "audio/wav")}
    r = client.post("/transcribe-upload-bg", files=files)
    assert r.status_code == 200
    assert "task_id" in r.json()


def test_accept_wav_sync(monkeypatch):
    client = TestClient(app)
    from minutes import tasks

    monkeypatch.setattr(tasks, "process_audio", lambda path: DummyTask("sync-fake-id"))

    wav = make_wav_bytes()
    files = {"file": ("test.wav", io.BytesIO(wav), "audio/wav")}
    r = client.post("/transcribe-upload", files=files)
    assert r.status_code == 200
    assert "task_id" in r.json()
