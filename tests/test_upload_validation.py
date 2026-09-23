import io
import wave

from backend.app import app
from tests.auth_helpers import logged_in_client


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
    client, _user_id = logged_in_client(app)
    # ensure background enqueue is mocked so test is fast and doesn't hit workers
    from minutes import tasks

    monkeypatch.setattr(tasks, "process_audio", lambda path: DummyTask("fake-id"))

    files = {"file": ("test.md", io.BytesIO(b"not audio"), "text/plain")}
    r = client.post("/api/transcribe-upload-bg", files=files)
    assert r.status_code == 400


def test_accept_wav_bg(monkeypatch):
    client, _user_id = logged_in_client(app)
    from minutes import tasks

    # mock process_audio.delay or process_audio depending on implementation
    def fake_delay(path):
        return DummyTask("bg-fake-id")

    # some code paths call process_audio.delay (celery) or process_audio directly
    if hasattr(tasks.process_audio, "delay"):
        monkeypatch.setattr(tasks.process_audio, "delay", fake_delay)
    else:
        monkeypatch.setattr(
            tasks, "process_audio", lambda path: DummyTask("bg-fake-id")
        )

    wav = make_wav_bytes()
    files = {"file": ("test.wav", io.BytesIO(wav), "audio/wav")}
    r = client.post("/api/transcribe-upload-bg", files=files)
    assert r.status_code == 200
    assert "task_id" in r.json()


def _mp3_with_large_id3() -> bytes:
    """ID3v2 tag larger than the 4096-byte sniff window, then an MPEG frame."""
    payload = b"\xff\xd8\xff\xe0" + b"JFIF" + b"\x00" * 20000
    size = len(payload)
    syncsafe = bytes(
        (
            (size >> 21) & 0x7F,
            (size >> 14) & 0x7F,
            (size >> 7) & 0x7F,
            size & 0x7F,
        )
    )
    return (
        b"ID3\x03\x00\x00"
        + syncsafe
        + payload
        + bytes((0xFF, 0xFB, 0x90, 0x64))
        + b"\x00" * 128
    )


def test_accept_mp3_with_id3_larger_than_sniff_window(monkeypatch):
    client, _user_id = logged_in_client(app)
    from minutes import tasks

    monkeypatch.setattr(tasks, "process_audio", lambda path: DummyTask("mp3-id"))

    files = {"file": ("meeting.mp3", io.BytesIO(_mp3_with_large_id3()), "audio/mpeg")}
    response = client.post("/api/transcribe-upload-bg", files=files)
    assert response.status_code == 200
    assert "task_id" in response.json()


def test_reject_mp3_extension_with_non_audio_bytes(monkeypatch):
    client, _user_id = logged_in_client(app)
    from minutes import tasks

    monkeypatch.setattr(tasks, "process_audio", lambda path: DummyTask("unused"))

    files = {"file": ("notes.mp3", io.BytesIO(b"this is text"), "audio/mpeg")}
    response = client.post("/api/transcribe-upload-bg", files=files)
    assert response.status_code == 400


def test_accept_wav_sync(monkeypatch):
    client, _user_id = logged_in_client(app)
    from minutes import tasks

    monkeypatch.setattr(tasks, "process_audio", lambda path: DummyTask("sync-fake-id"))

    wav = make_wav_bytes()
    files = {"file": ("test.wav", io.BytesIO(wav), "audio/wav")}
    r = client.post("/api/transcribe-upload", files=files)
    assert r.status_code == 200
    assert "task_id" in r.json()
