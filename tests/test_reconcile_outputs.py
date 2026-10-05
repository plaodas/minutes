import os
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy.exc import SQLAlchemyError

from minutes.bg_store import create_task
from minutes.reconcile_bg_tasks import quarantine_unreferenced_outputs
from minutes.task_lifecycle import mark_task_deleted


def _age(path, seconds: int) -> None:
    stamp = (datetime.now(tz=timezone.utc) - timedelta(seconds=seconds)).timestamp()
    os.utime(path, (stamp, stamp))


def _write(path) -> str:
    path.write_text("minutes", encoding="utf-8")
    return str(path)


def test_quarantine_moves_only_old_unreferenced_outputs(monkeypatch, tmp_path):
    monkeypatch.setenv("OUTPUT_QUARANTINE_SECONDS", "3600")
    monkeypatch.setenv("OUTPUT_DELETED_RETENTION_SECONDS", "86400")
    deleted = tmp_path / "deleted"
    deleted.mkdir()

    referenced = _write(tmp_path / f"minutes_{uuid.uuid4().hex}_kept.txt")
    nested = _write(tmp_path / f"minutes_{uuid.uuid4().hex}_nested.txt")
    soft_deleted = _write(tmp_path / f"minutes_{uuid.uuid4().hex}_soft.txt")
    fresh = _write(tmp_path / f"minutes_{uuid.uuid4().hex}_fresh.txt")
    stale = _write(tmp_path / f"minutes_{uuid.uuid4().hex}_stale.txt")
    other = _write(tmp_path / f"notes_{uuid.uuid4().hex}.txt")
    expired = _write(deleted / f"minutes_{uuid.uuid4().hex}_expired.txt")
    retained = _write(deleted / f"minutes_{uuid.uuid4().hex}_retained.txt")

    for path in (referenced, nested, soft_deleted, stale, other):
        _age(path, 7200)
    _age(expired, 90000)
    _age(retained, 60)

    referenced_id = uuid.uuid4()
    nested_id = uuid.uuid4()
    soft_deleted_id = uuid.uuid4()
    create_task(str(referenced_id), metadata={"output_file": referenced})
    create_task(
        str(nested_id),
        metadata={"result": {"output_file": nested}},
    )
    create_task(str(soft_deleted_id), metadata={"output_file": soft_deleted})
    assert mark_task_deleted(str(soft_deleted_id)) is True

    now = datetime.now(tz=timezone.utc)
    quarantine_unreferenced_outputs(str(tmp_path), now=now)

    assert os.path.exists(referenced)
    assert os.path.exists(nested)
    assert os.path.exists(soft_deleted)
    assert os.path.exists(fresh)
    assert os.path.exists(other)
    assert not os.path.exists(stale)
    moved = deleted / os.path.basename(stale)
    assert moved.is_file()
    assert abs(moved.stat().st_mtime - now.timestamp()) < 2
    assert not os.path.exists(expired)
    assert os.path.exists(retained)


def test_quarantine_leaves_files_when_task_load_fails(monkeypatch, tmp_path):
    monkeypatch.setenv("OUTPUT_QUARANTINE_SECONDS", "3600")
    stale = _write(tmp_path / f"minutes_{uuid.uuid4().hex}_stale.txt")
    _age(stale, 7200)

    def fail_scope():
        raise SQLAlchemyError("db down")

    monkeypatch.setattr("minutes.db.session_scope", fail_scope)

    quarantine_unreferenced_outputs(str(tmp_path))

    assert os.path.exists(stale)
    assert not (tmp_path / "deleted").exists()
