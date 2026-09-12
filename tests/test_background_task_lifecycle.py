import uuid

from fastapi.testclient import TestClient

from minutes import bg_store
from minutes import tasks as task_workers
from minutes.api import app
from minutes.bg_store import create_task, get_task
from minutes.db import session_scope
from minutes.models import Task, TaskHistory
from minutes.routers import background_task_lifecycle


def test_cancel_marks_task_cancelled_when_celery_revoke_fails(monkeypatch):
    task_id = str(uuid.uuid4())
    cancelled = []

    def fail_revoke(*_args, **_kwargs):
        raise background_task_lifecycle.CeleryError("broker unavailable")

    monkeypatch.setattr(background_task_lifecycle.celery.control, "revoke", fail_revoke)
    monkeypatch.setattr(
        background_task_lifecycle, "update_task_cancelled", cancelled.append
    )

    response = TestClient(app).post(f"/api/bg/cancel/{task_id}")

    assert response.status_code == 200
    assert response.json() == {"task_id": task_id, "cancelled": True}
    assert cancelled == [task_id]


def test_undelete_restores_soft_deleted_task(monkeypatch):
    task_id = uuid.uuid4()
    create_task(str(task_id))
    published = []
    monkeypatch.setattr(bg_store, "publish_event", published.append)
    client = TestClient(app)

    delete_response = client.post(f"/api/bg/delete/{task_id}")
    undelete_response = client.post(f"/api/bg/undelete/{task_id}")

    assert delete_response.status_code == 200
    assert undelete_response.status_code == 200
    with session_scope() as session:
        task = session.get(Task, task_id)
        assert task is not None
        assert task.status == "pending"
        assert task.deleted is False
        assert task.deleted_at is None
        undeleted = (
            session.query(TaskHistory)
            .filter(
                TaskHistory.task_id == task_id,
                TaskHistory.event_type == "undeleted",
            )
            .one()
        )
        assert undeleted.payload == {"previous": "deleted", "status": "pending"}
    assert [event["event_type"] for event in published] == ["deleted", "undeleted"]
    assert [event["stage"] for event in published] == ["deleted", "pending"]


def test_hard_delete_removes_task_and_publishes_event(monkeypatch):
    task_id = uuid.uuid4()
    create_task(str(task_id))
    published = []
    monkeypatch.setattr(bg_store, "publish_event", published.append)

    result = task_workers.hard_delete_task.run(str(task_id), None)

    assert result == {"deleted": True}
    assert get_task(str(task_id)) is None
    assert published[-1]["event_type"] == "deleted_hard"
    assert published[-1]["task_id"] == str(task_id)


def test_force_delete_publishes_hard_delete_event(monkeypatch):
    task_id = uuid.uuid4()
    create_task(str(task_id))
    published = []
    monkeypatch.setattr(
        background_task_lifecycle.celery.control,
        "revoke",
        lambda *_args, **_kwargs: None,
    )
    monkeypatch.setattr(
        background_task_lifecycle,
        "emit_task_event",
        lambda task_id, event_type, payload: published.append(
            (task_id, event_type, payload)
        ),
    )

    response = TestClient(app).post(f"/api/bg/force-delete/{task_id}")

    assert response.status_code == 200
    assert get_task(str(task_id)) is None
    assert published == [(str(task_id), "deleted_hard", {})]
