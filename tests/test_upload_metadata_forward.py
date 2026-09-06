import io
import wave
from fastapi.testclient import TestClient
from backend.app import app

import minutes.tasks as tasks


def make_wav_bytes(duration_seconds: float = 0.02) -> bytes:
    import wave, io

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
    client = TestClient(app)

    # make process_audio.delay return a DummyTask
    class Dummy:
        def __init__(self, id):
            self.id = id

    if hasattr(tasks.process_audio, 'delay'):
        monkeypatch.setattr(tasks.process_audio, 'delay', lambda path: Dummy('fake-id-xyz'))
    else:
        monkeypatch.setattr(tasks, 'process_audio', lambda path: Dummy('fake-id-xyz'))

    called = {}
    import minutes.bg_store as bg
    import minutes.api as api_mod

    def fake_create(task_id, metadata=None, user_id=None, db=None):
        called['task_id'] = task_id
        called['metadata'] = metadata
        called['user_id'] = user_id

    monkeypatch.setattr(bg, 'create_task', fake_create)
    monkeypatch.setattr(api_mod, 'create_task', fake_create)

    wav = make_wav_bytes()
    files = {"file": ("test.wav", io.BytesIO(wav), "audio/wav")}
    data = {'language': 'Japanese', 'include_actions': '0'}

    r = client.post('/transcribe-upload-bg', files=files, data=data)
    assert r.status_code == 200
    assert called.get('metadata')
    assert called['metadata'].get('language') == 'Japanese'
    assert called['metadata'].get('include_actions') is False
