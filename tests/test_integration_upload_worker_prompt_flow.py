import io
import uuid

from fastapi.testclient import TestClient

from backend.app import app
from minutes import tasks
from minutes.db import session_scope
from minutes.models import Task


def make_wav_bytes(duration_seconds: float = 0.02) -> bytes:
    import io
    import wave

    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(16000)
        frames = int(16000 * duration_seconds)
        w.writeframes(b"\x00\x00" * frames)
    buf.seek(0)
    return buf.read()


def test_upload_and_worker_prompt_flow(monkeypatch):
    client = TestClient(app, raise_server_exceptions=True)

    fake_id = uuid.uuid4()

    # stub process_audio.delay to return predictable id
    class DummyTask:
        def __init__(self, id):
            self.id = id

    monkeypatch.setattr(
        tasks.process_audio, "delay", lambda path: DummyTask(str(fake_id))
    )

    # ensure create_task writes a DB Task row with metadata so worker can read it
    import minutes.api as api_mod
    from minutes import bg_store

    def fake_create(task_id, metadata=None, user_id=None, db=None):
        if db is None:
            with session_scope() as session:
                key = uuid.UUID(str(task_id)) if isinstance(task_id, str) else task_id
                t = session.get(Task, key)
                if not t:
                    t = Task(id=key, status="pending", result=metadata or None)
                    session.add(t)
                else:
                    if metadata:
                        t.result = metadata
                        session.add(t)
        else:
            session = db
            try:
                key = uuid.UUID(str(task_id)) if isinstance(task_id, str) else task_id
                t = session.get(Task, key)
                if not t:
                    t = Task(id=key, status="pending", result=metadata or None)
                    session.add(t)
                else:
                    if metadata:
                        t.result = metadata
                        session.add(t)
                session.commit()
            except Exception:
                session.rollback()
                raise

    monkeypatch.setattr(bg_store, "create_task", fake_create)
    monkeypatch.setattr(api_mod, "create_task", fake_create)

    captured = {}

    def fake_format(raw_text, model=None, system_prompt=None, host=None):
        captured["prompt"] = system_prompt
        return "FORMATTED"

    monkeypatch.setattr(tasks, "format_minutes_from_raw", fake_format)

    wav = make_wav_bytes()
    files = {"file": ("test.wav", io.BytesIO(wav), "audio/wav")}
    data = {"language": "Japanese", "include_actions": "0"}

    r = client.post("/transcribe-upload-bg", files=files, data=data)
    assert r.status_code == 200
    resp = r.json()
    assert resp.get("task_id")

    # fetch Task row from DB and get metadata
    with session_scope() as session:
        t = session.get(Task, fake_id)
        assert t is not None
        meta = t.result or {}

    # build prompt and call the (monkeypatched) formatter to simulate worker using it
    prompt = tasks.build_system_prompt(meta)
    assert prompt is not None
    tasks.format_minutes_from_raw("raw transcript", system_prompt=prompt)
    assert "日本語" in (captured.get("prompt") or "") or "Japanese" in (
        captured.get("prompt") or ""
    )
    assert "Do not extract action items" in (captured.get("prompt") or "")
