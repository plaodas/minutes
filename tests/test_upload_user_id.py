import io
import wave

import pytest
from fastapi.testclient import TestClient

from backend.app import app
from minutes import tasks


def make_wav_bytes(duration_seconds: float = 0.05) -> bytes:
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


@pytest.mark.usefixtures("monkeypatch")
def test_upload_sets_user_id(monkeypatch):
    client = TestClient(app)

    # mock background task enqueue to be synchronous and return a known id
    if hasattr(tasks.process_audio, "delay"):
        monkeypatch.setattr(
            tasks.process_audio, "delay", lambda path: DummyTask("fake-user-id-1234")
        )
    else:
        monkeypatch.setattr(
            tasks, "process_audio", lambda path: DummyTask("fake-user-id-1234")
        )

    wav = make_wav_bytes()
    files = {"file": ("test.wav", io.BytesIO(wav), "audio/wav")}
    headers = {"X-User-Id": "11111111-1111-1111-1111-111111111111"}
    r = client.post("/transcribe-upload-bg", files=files, headers=headers)
    assert r.status_code == 200
    data = r.json()
    assert "task_id" in data

    # Instead of querying DB (SQLite UUID handling differs), assert that
    # create_task was called with the expected user_id by monkeypatching it.
    called = {}

    import minutes.api as api_mod
    import minutes.bg_store as bg

    def fake_create(task_id, metadata=None, user_id=None, db=None):
        called["task_id"] = task_id
        called["metadata"] = metadata
        called["user_id"] = user_id

    # Patch both the bg_store and the imported reference in the API module
    monkeypatch.setattr(bg, "create_task", fake_create)
    monkeypatch.setattr(api_mod, "create_task", fake_create)

    # Trigger upload again to hit our fake
    r2 = client.post("/transcribe-upload-bg", files=files, headers=headers)
    assert r2.status_code == 200
    assert called.get("user_id") == "11111111-1111-1111-1111-111111111111"
