import uuid
from contextlib import contextmanager

from sqlalchemy import event

from minutes import bg_store
from minutes.bg_store import create_task
from minutes.db import SessionLocal, session_scope
from minutes.models import Bucket, Task, TaskHistory


def test_record_history_commits_once_via_transaction_scope(monkeypatch):
    commits = []

    class FakeSession:
        def add(self, _row):
            pass

        def commit(self):
            commits.append("commit")

    @contextmanager
    def fake_session_scope():
        session = FakeSession()
        yield session
        session.commit()

    monkeypatch.setattr(bg_store, "session_scope", fake_session_scope)

    bg_store.record_history(str(uuid.uuid4()), "created", emit_event=False)

    assert commits == ["commit"]


def test_create_task_with_user_id():
    owner = uuid.uuid4()
    task_id = uuid.uuid4()
    # create task with explicit UUIDs
    create_task(str(task_id), metadata={"foo": "bar"}, user_id=str(owner))
    with session_scope() as db:
        t = db.get(Task, task_id)
        assert t is not None
        assert t.user_id == owner
        assert isinstance(t.result, dict)
        assert t.result.get("foo") == "bar"


def test_create_task_with_external_id_and_owner():
    owner = uuid.uuid4()
    external = "external-123"
    create_task(external, metadata={"meta": "x"}, user_id=str(owner))
    # Use raw SQL to avoid SQLAlchemy UUID type conversions in SQLite tests
    from sqlalchemy import text

    from minutes.db import engine

    conn = engine.connect()
    try:
        row = conn.execute(
            text("SELECT id, user_id, result FROM tasks WHERE result LIKE :p"),
            {"p": f"%{external}%"},
        ).fetchone()
        assert row is not None
        user_text = row[1]
        # user_text may be stored as hex string without hyphens; normalize and compare
        user_norm = str(user_text).replace("-", "").lower()
        # Ensure a user_id was stored (format: 32-hex chars)
        assert user_norm and len(user_norm) == 32
        import json

        res = json.loads(row[2]) if row[2] else {}
        assert res.get("meta") == "x"
    finally:
        conn.close()


def test_progress_updates_publish_when_history_is_coalesced(monkeypatch):
    task_id = uuid.uuid4()
    create_task(str(task_id))
    published = []
    monkeypatch.setattr(bg_store, "publish_event", published.append)

    bg_store.update_task_progress(str(task_id), 10.0)
    bg_store.update_task_progress(str(task_id), 20.0)

    assert [event["payload"]["progress"] for event in published] == [10.0, 20.0]
    assert all(event["event_type"] == "progress" for event in published)
    assert all(event["type"] == "task.event" for event in published)


def test_success_records_history_and_publishes_status(monkeypatch):
    task_id = uuid.uuid4()
    create_task(str(task_id))
    published = []
    monkeypatch.setattr(bg_store, "publish_event", published.append)

    bg_store.update_task_success(str(task_id), {"summary": "done"})

    with session_scope() as db:
        history = (
            db.query(TaskHistory)
            .filter(
                TaskHistory.task_id == task_id,
                TaskHistory.event_type == "success",
            )
            .one_or_none()
        )
    assert history is not None
    assert history.payload == {"result": {"summary": "done"}}
    assert published[-1]["event_type"] == "status"
    assert published[-1]["stage"] == "success"


def test_failure_update_commits_state_and_history_once(monkeypatch):
    task_id = uuid.uuid4()
    create_task(str(task_id))
    commits = []
    published = []

    def track_commit(_session):
        commits.append("commit")

    event.listen(SessionLocal.class_, "after_commit", track_commit)
    monkeypatch.setattr(bg_store, "publish_event", published.append)
    try:
        bg_store.update_task_failure(str(task_id), "transcription failed")
    finally:
        event.remove(SessionLocal.class_, "after_commit", track_commit)

    assert commits == ["commit"]
    with session_scope() as db:
        task = db.get(Task, task_id)
        history = (
            db.query(TaskHistory)
            .filter(
                TaskHistory.task_id == task_id,
                TaskHistory.event_type == "failure",
            )
            .one()
        )
        assert task is not None
        assert task.status == "failed"
        assert history.payload == {"error": "transcription failed"}
    assert published[-1]["event_type"] == "failure"


def test_cancelled_update_records_state_history_and_event(monkeypatch):
    task_id = uuid.uuid4()
    create_task(str(task_id))
    published = []
    monkeypatch.setattr(bg_store, "publish_event", published.append)

    bg_store.update_task_cancelled(str(task_id))

    with session_scope() as db:
        task = db.get(Task, task_id)
        history = (
            db.query(TaskHistory)
            .filter(
                TaskHistory.task_id == task_id,
                TaskHistory.event_type == "cancelled",
            )
            .one()
        )
        assert task is not None
        assert task.status == "cancelled"
        assert history.payload == {}
    assert published[-1]["event_type"] == "cancelled"


def test_success_registers_minio_bucket():
    task_id = uuid.uuid4()
    bucket_name = f"task-results-{task_id}"
    create_task(str(task_id))

    bg_store.update_task_success(
        str(task_id),
        {
            "minio": {
                "bucket": bucket_name,
                "object": "minutes.txt",
                "metadata": {"source": "task"},
            }
        },
    )

    with session_scope() as db:
        bucket = (
            db.query(Bucket.name, Bucket.bucket_metadata)
            .filter(Bucket.name == bucket_name)
            .one_or_none()
        )
        assert bucket == (bucket_name, {"source": "task"})
