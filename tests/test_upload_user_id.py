import io
import uuid
import wave

from fastapi.testclient import TestClient

from backend.app import app
from minutes import tasks
from minutes.auth import create_service_token
from tests.auth_helpers import create_user, logged_in_client


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


def _capture_create(monkeypatch):
    called = {}
    import minutes.bg_store as bg

    def fake_create(task_id, metadata=None, user_id=None, db=None):
        called["task_id"] = task_id
        called["metadata"] = metadata
        called["user_id"] = user_id

    monkeypatch.setattr(bg, "create_task", fake_create)
    if hasattr(tasks.process_audio, "delay"):
        monkeypatch.setattr(
            tasks.process_audio, "delay", lambda path: DummyTask("fake-user-id-1234")
        )
    else:
        monkeypatch.setattr(
            tasks, "process_audio", lambda path: DummyTask("fake-user-id-1234")
        )
    return called


def test_upload_requires_login():
    client = TestClient(app)
    wav = make_wav_bytes()
    files = {"file": ("test.wav", io.BytesIO(wav), "audio/wav")}
    response = client.post("/api/transcribe-upload-bg", files=files)
    assert response.status_code == 401
    assert response.json() == {"error": "Not authenticated"}


def test_upload_ignores_x_user_id(monkeypatch):
    client, user_id = logged_in_client(app)
    called = _capture_create(monkeypatch)
    wav = make_wav_bytes()
    files = {"file": ("test.wav", io.BytesIO(wav), "audio/wav")}
    headers = {"X-User-Id": "11111111-1111-1111-1111-111111111111"}

    response = client.post("/api/transcribe-upload-bg", files=files, headers=headers)

    assert response.status_code == 200
    assert called["user_id"] == str(user_id)
    assert called["user_id"] != headers["X-User-Id"]


def test_upload_owner_comes_from_service_token(monkeypatch):
    user_id = create_user()
    token, _token_id = create_service_token(name="upload", user_id=str(user_id))
    called = _capture_create(monkeypatch)
    wav = make_wav_bytes()
    files = {"file": ("test.wav", io.BytesIO(wav), "audio/wav")}

    response = TestClient(app).post(
        "/api/transcribe-upload-bg",
        files=files,
        headers={
            "Authorization": f"Bearer {token}",
            "X-User-Id": str(uuid.uuid4()),
        },
    )

    assert response.status_code == 200
    assert called["user_id"] == str(user_id)
