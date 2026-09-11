import uuid

from fastapi.testclient import TestClient

from minutes.api import app
from minutes.bg_store import create_task
from minutes.db import session_scope
from minutes.models import Task
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


def test_undelete_restores_soft_deleted_task():
    task_id = uuid.uuid4()
    create_task(str(task_id))
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
