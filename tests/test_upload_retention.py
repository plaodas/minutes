import os
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import event, update

from minutes.bg_store import create_task, update_task_cancelled, update_task_failure
from minutes.db import engine, session_scope
from minutes.models import Task
from minutes.schemas import TaskStage
from minutes.task_deletion import delete_task_permanently
from minutes.upload_retention import sweep_expired_uploads


def _age(path, days: int) -> None:
    stamp = (datetime.now(tz=timezone.utc) - timedelta(days=days)).timestamp()
    os.utime(path, (stamp, stamp))


def _write(path) -> str:
    path.write_bytes(b"audio")
    return str(path)


def test_failure_and_cancel_keep_upload_path():
    failed_id = uuid.uuid4()
    cancelled_id = uuid.uuid4()
    create_task(str(failed_id), metadata={"upload_path": "/uploads/a.mp3", "language": "English"})
    create_task(str(cancelled_id), metadata={"upload_path": "/uploads/b.mp3"})

    update_task_failure(str(failed_id), "transcription failed")
    update_task_cancelled(str(cancelled_id))

    with session_scope() as session:
        failed = session.get(Task, failed_id)
        cancelled = session.get(Task, cancelled_id)
        assert failed is not None and cancelled is not None
        assert failed.result == {"upload_path": "/uploads/a.mp3"}
        assert cancelled.result == {"upload_path": "/uploads/b.mp3"}


def test_hard_delete_removes_managed_upload(monkeypatch, tmp_path):
    monkeypatch.setenv("UPLOADS_DIR", str(tmp_path))
    upload = _write(tmp_path / "meeting.mp3")
    derived = _write(tmp_path / "meeting_mono.wav")
    task_id = uuid.uuid4()
    create_task(str(task_id), metadata={"upload_path": upload})

    assert delete_task_permanently(str(task_id)) == {"deleted": True}
    assert not os.path.exists(upload)
    assert not os.path.exists(derived)


def _param_values(parameters: object) -> list[str]:
    if isinstance(parameters, dict):
        values = parameters.values()
    elif isinstance(parameters, (list, tuple)):
        values = parameters
    else:
        return []
    return [str(getattr(value, "value", value)) for value in values]


def test_sweep_drops_expired_failures_and_orphans(monkeypatch, tmp_path):
    monkeypatch.setenv("UPLOADS_DIR", str(tmp_path))
    monkeypatch.setenv("UPLOAD_RETENTION_SECONDS", "86400")
    now = datetime.now(tz=timezone.utc)
    old = now - timedelta(days=2)

    active = _write(tmp_path / "active.mp3")
    active_wav = _write(tmp_path / "active_mono.wav")
    fresh_failure = _write(tmp_path / "fresh.mp3")
    stale_failure = _write(tmp_path / "stale.mp3")
    stale_wav = _write(tmp_path / "stale_mono.wav")
    stale_cancel = _write(tmp_path / "cancel.mp3")
    orphan_old = _write(tmp_path / "orphan-old.mp3")
    orphan_new = _write(tmp_path / "orphan-new.mp3")
    aged = (
        active,
        active_wav,
        fresh_failure,
        stale_failure,
        stale_wav,
        stale_cancel,
        orphan_old,
    )
    for path in aged:
        _age(path, 3)

    active_id = uuid.uuid4()
    fresh_id = uuid.uuid4()
    stale_id = uuid.uuid4()
    cancel_id = uuid.uuid4()
    success_id = uuid.uuid4()
    create_task(str(active_id), metadata={"upload_path": active})
    create_task(str(fresh_id), metadata={"upload_path": fresh_failure})
    create_task(str(stale_id), metadata={"upload_path": stale_failure})
    create_task(str(cancel_id), metadata={"upload_path": stale_cancel})
    create_task(str(success_id), metadata={"minutes": "done"})

    with session_scope() as session:
        session.execute(
            update(Task)
            .where(Task.id == fresh_id)
            .values(status=TaskStage.FAILED.value, last_failure_ts=now)
        )
        session.execute(
            update(Task)
            .where(Task.id == stale_id)
            .values(status=TaskStage.FAILED.value, last_failure_ts=old)
        )
        session.execute(
            update(Task)
            .where(Task.id == cancel_id)
            .values(status=TaskStage.CANCELLED.value, updated_at=old)
        )
        session.execute(
            update(Task)
            .where(Task.id == success_id)
            .values(status=TaskStage.SUCCESS.value)
        )

    captured: list[list[str]] = []

    def capture(_conn, _cursor, statement, parameters, _context, _executemany):
        if "JSON_EXTRACT" not in statement and "->>" not in statement:
            return
        captured.append(_param_values(parameters))

    event.listen(engine, "before_cursor_execute", capture)
    try:
        sweep_expired_uploads(now)
    finally:
        event.remove(engine, "before_cursor_execute", capture)

    assert captured
    statuses = set(captured[0])
    assert TaskStage.SUCCESS.value not in statuses
    assert TaskStage.PENDING.value in statuses
    assert TaskStage.FAILED.value in statuses

    assert os.path.exists(active)
    assert os.path.exists(active_wav)
    assert os.path.exists(fresh_failure)
    assert os.path.exists(orphan_new)
    assert not os.path.exists(stale_failure)
    assert not os.path.exists(stale_wav)
    assert not os.path.exists(stale_cancel)
    assert not os.path.exists(orphan_old)
