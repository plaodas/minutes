import io
import wave

from backend.app import app
from minutes import tasks
from tests.auth_helpers import logged_in_client


def make_wav_bytes(duration_seconds: float = 0.02) -> bytes:
    import io

    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(16000)
        frames = int(16000 * duration_seconds)
        w.writeframes(b"\x00\x00" * frames)
    buf.seek(0)
    return buf.read()


def test_upload_passes_language_and_include_actions(monkeypatch):
    client, user_id = logged_in_client(app)

    # make process_audio.delay return a DummyTask
    class Dummy:
        def __init__(self, id):
            self.id = id

    called = {}
    import minutes.bg_store as bg

    def fake_apply_async(args, task_id=None):
        called.setdefault("order", []).append("enqueue")
        called["enqueued_id"] = task_id
        return Dummy(task_id)

    if hasattr(tasks.process_audio, "apply_async"):
        monkeypatch.setattr(tasks.process_audio, "apply_async", fake_apply_async)
    else:
        monkeypatch.setattr(tasks, "process_audio", lambda path: Dummy("fake-id-xyz"))

    def fake_create(task_id, metadata=None, user_id=None, db=None):
        called.setdefault("order", []).append("create")
        called["task_id"] = task_id
        called["metadata"] = metadata
        called["user_id"] = user_id

    monkeypatch.setattr(bg, "create_task", fake_create)

    def files():
        return {"file": ("test.wav", io.BytesIO(make_wav_bytes()), "audio/wav")}

    data = {"language": "Japanese", "include_actions": "0", "engine": "hayamimi"}

    r = client.post("/api/transcribe-upload-bg", files=files(), data=data)
    assert r.status_code == 200
    assert called.get("metadata")
    assert called["metadata"].get("language") == "Japanese"
    assert called["metadata"].get("include_actions") is False
    assert called["metadata"].get("engine") == "hayamimi"
    assert "transcript_only" not in called["metadata"]
    assert called["metadata"]["upload_path"].endswith(".wav")
    assert called["user_id"] == str(user_id)
    assert called["order"] == ["create", "enqueue"]
    assert called["enqueued_id"] == called["task_id"]

    called.clear()
    data["transcript_only"] = "1"
    enabled = client.post("/api/transcribe-upload", files=files(), data=data)
    assert enabled.status_code == 200
    assert called["metadata"].get("transcript_only") is True

    called.clear()
    data["transcript_only"] = "0"
    disabled = client.post("/api/transcribe-upload-bg", files=files(), data=data)
    assert disabled.status_code == 200
    assert "transcript_only" not in called["metadata"]
