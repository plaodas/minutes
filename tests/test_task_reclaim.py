import os
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import update

from minutes.bg_store import create_task, get_task, update_task_status
from minutes.db import session_scope
from minutes.models import Task
from minutes.task_reclaim import reclaim_interrupted_tasks
from minutes.upload_retention import sweep_expired_uploads


def _enable(monkeypatch):
    monkeypatch.setenv("RECLAIM_ON_START", "1")


def _only(monkeypatch, task_id: str, status: str, upload_path: str) -> None:
    monkeypatch.setattr(
        "minutes.task_reclaim._unfinished_tasks",
        lambda: [{"id": task_id, "status": status, "upload_path": upload_path}],
    )


def test_reclaim_does_nothing_when_redis_cannot_be_confirmed(monkeypatch):
    _enable(monkeypatch)
    monkeypatch.setattr("minutes.task_reclaim._broker_state", lambda: None)
    monkeypatch.setattr(
        "minutes.task_reclaim._enqueue",
        lambda *_args: (_ for _ in ()).throw(AssertionError("enqueued")),
    )

    reclaim_interrupted_tasks()


def test_reclaim_reenqueues_a_running_task_with_its_upload(monkeypatch, tmp_path):
    _enable(monkeypatch)
    upload = tmp_path / "meeting.mp3"
    upload.write_bytes(b"audio")
    task_id = str(uuid.uuid4())
    create_task(
        task_id,
        metadata={"upload_path": str(upload), "language": "English"},
    )
    update_task_status(task_id, "transcribing")
    _only(monkeypatch, task_id, "transcribing", str(upload))
    enqueued = []
    monkeypatch.setattr(
        "minutes.task_reclaim._broker_state",
        lambda: {"busy": set(), "blob": b""},
    )
    monkeypatch.setattr(
        "minutes.task_reclaim._enqueue",
        lambda tid, path: enqueued.append((tid, path)) or True,
    )

    reclaim_interrupted_tasks()

    assert enqueued == [(task_id, str(upload))]
    stored = get_task(task_id)
    assert stored["status"] == "failed"
    assert stored["result"]["language"] == "English"
    assert stored["result"]["upload_path"] == str(upload)


def test_reclaim_leaves_a_task_that_is_still_queued(monkeypatch, tmp_path):
    _enable(monkeypatch)
    upload = tmp_path / "meeting.mp3"
    upload.write_bytes(b"audio")
    task_id = str(uuid.uuid4())
    create_task(task_id, metadata={"upload_path": str(upload)})
    update_task_status(task_id, "formatting")
    _only(monkeypatch, task_id, "formatting", str(upload))
    monkeypatch.setattr(
        "minutes.task_reclaim._broker_state",
        lambda: {"busy": set(), "blob": task_id.encode()},
    )
    monkeypatch.setattr(
        "minutes.task_reclaim._enqueue",
        lambda *_args: (_ for _ in ()).throw(AssertionError("enqueued")),
    )

    reclaim_interrupted_tasks()

    assert get_task(task_id)["status"] == "formatting"


def test_reclaim_marks_a_missing_upload_failed(monkeypatch):
    _enable(monkeypatch)
    task_id = str(uuid.uuid4())
    create_task(task_id, metadata={"upload_path": "/tmp/minutes-missing-upload.mp3"})
    update_task_status(task_id, "preprocess")
    _only(monkeypatch, task_id, "preprocess", "/tmp/minutes-missing-upload.mp3")
    monkeypatch.setattr(
        "minutes.task_reclaim._broker_state",
        lambda: {"busy": set(), "blob": b""},
    )
    monkeypatch.setattr(
        "minutes.task_reclaim._enqueue",
        lambda *_args: (_ for _ in ()).throw(AssertionError("enqueued")),
    )

    reclaim_interrupted_tasks()

    stored = get_task(task_id)
    assert stored["status"] == "failed"
    assert stored["result"] == {"upload_path": "/tmp/minutes-missing-upload.mp3"}


def test_reclaim_returns_to_pending_when_enqueue_fails(monkeypatch, tmp_path):
    _enable(monkeypatch)
    upload = tmp_path / "meeting.mp3"
    upload.write_bytes(b"audio")
    task_id = str(uuid.uuid4())
    create_task(task_id, metadata={"upload_path": str(upload), "language": "English"})
    update_task_status(task_id, "transcribing")
    _only(monkeypatch, task_id, "transcribing", str(upload))
    monkeypatch.setattr(
        "minutes.task_reclaim._broker_state",
        lambda: {"busy": set(), "blob": b""},
    )
    monkeypatch.setattr("minutes.task_reclaim._enqueue", lambda *_args: False)

    reclaim_interrupted_tasks()

    stored = get_task(task_id)
    assert stored["status"] == "pending"
    assert stored["result"]["language"] == "English"


def test_failed_reclaim_allows_upload_retention_to_delete(monkeypatch, tmp_path):
    _enable(monkeypatch)
    monkeypatch.setenv("UPLOADS_DIR", str(tmp_path))
    monkeypatch.setenv("UPLOAD_RETENTION_SECONDS", "86400")
    upload = tmp_path / "meeting.mp3"
    upload.write_bytes(b"audio")
    derived = tmp_path / "meeting_mono.wav"
    derived.write_bytes(b"wav")
    old = (datetime.now(tz=timezone.utc) - timedelta(days=3)).timestamp()
    os.utime(upload, (old, old))
    os.utime(derived, (old, old))
    task_id = str(uuid.uuid4())
    create_task(task_id, metadata={"upload_path": str(upload)})
    update_task_status(task_id, "transcribing")
    _only(monkeypatch, task_id, "transcribing", str(upload))
    now = datetime.now(tz=timezone.utc)

    sweep_expired_uploads(now)
    assert os.path.exists(upload)

    monkeypatch.setattr(
        "minutes.task_reclaim._broker_state",
        lambda: {"busy": set(), "blob": b""},
    )
    monkeypatch.setattr("minutes.task_reclaim._enqueue", lambda *_args: True)
    reclaim_interrupted_tasks()
    with session_scope() as session:
        session.execute(
            update(Task)
            .where(Task.id == uuid.UUID(task_id))
            .values(last_failure_ts=now - timedelta(days=2))
        )

    sweep_expired_uploads(now)

    assert not os.path.exists(upload)
    assert not os.path.exists(derived)
