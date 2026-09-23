import uuid
from datetime import datetime, timezone

from fastapi.testclient import TestClient

from minutes.api import app
from minutes.bg_store import create_task
from minutes.db import session_scope
from minutes.models import Task, User
from minutes.task_access import event_visible_to
from tests.auth_helpers import assign_task_owner, create_user, logged_in_client, login


def _owned_task(user_id: uuid.UUID, *, result: dict | None = None) -> uuid.UUID:
    task_id = uuid.uuid4()
    with session_scope() as session:
        session.add(
            Task(
                id=task_id,
                user_id=user_id,
                status="success",
                result=result or {"summary": "notes"},
                deleted=False,
                created_at=datetime(2100, 1, 1, tzinfo=timezone.utc),
            )
        )
    return task_id


def test_anonymous_task_routes_are_unauthorized():
    client = TestClient(app)
    task_id = uuid.uuid4()
    assert client.get("/api/bg/tasks").status_code == 401
    assert client.get(f"/api/bg/status/{task_id}").status_code == 401
    assert client.get(f"/api/bg/result/{task_id}").status_code == 401
    assert client.get("/api/bg/events").status_code == 401
    assert client.post(f"/api/bg/cancel/{task_id}").status_code == 401
    assert client.post(f"/api/bg/delete/{task_id}").status_code == 401


def test_owner_lists_and_reads_only_own_task():
    owner_client, owner_id = logged_in_client(app)
    other_client, other_id = logged_in_client(app)
    own_id = _owned_task(owner_id)
    other_id_task = _owned_task(other_id)
    unowned_id = uuid.uuid4()
    create_task(str(unowned_id))

    listed = {task["id"] for task in owner_client.get("/api/bg/tasks?limit=10000").json()["tasks"]}
    assert str(own_id) in listed
    assert str(other_id_task) not in listed
    assert str(unowned_id) not in listed

    result = owner_client.get(f"/api/bg/result/{own_id}")
    assert result.status_code == 200
    assert result.json()["status"] == "success"

    for client in (other_client, owner_client):
        hidden = other_id_task if client is owner_client else own_id
        assert client.get(f"/api/bg/status/{hidden}").status_code == 404
        assert client.get(f"/api/bg/result/{hidden}").status_code == 404
        assert client.get(f"/api/bg/status/{unowned_id}").status_code == 404


def test_admin_does_not_see_another_users_task():
    owner_id = create_user()
    admin_id = create_user()
    with session_scope() as session:
        admin = session.get(User, admin_id)
        assert admin is not None
        admin.is_admin = True
    task_id = _owned_task(owner_id)
    client = login(TestClient(app), admin_id)

    response = client.get(f"/api/bg/result/{task_id}")

    assert response.status_code == 404
    assert response.json() == {"error": "unknown task"}


def test_rename_and_cancel_reject_other_users_task():
    _owner_client, owner_id = logged_in_client(app)
    other_client, _other_id = logged_in_client(app)
    task_id = _owned_task(owner_id)

    assert other_client.post(
        f"/api/bg/task/{task_id}/rename",
        json={"name": "stolen"},
    ).status_code == 404
    assert other_client.post(f"/api/bg/cancel/{task_id}").status_code == 404
    with session_scope() as session:
        task = session.get(Task, task_id)
        assert task is not None
        assert task.name != "stolen"
        assert task.status == "success"


def test_sse_hides_events_for_other_users():
    owner_id = create_user()
    other_id = create_user()
    own_task = _owned_task(owner_id)
    other_task = _owned_task(other_id)
    orphan = uuid.uuid4()
    create_task(str(orphan))
    assign_task_owner(own_task, owner_id)
    cache: dict[str, bool] = {}

    assert event_visible_to({"task_id": str(own_task)}, owner_id, cache) is True
    assert event_visible_to({"task_id": str(other_task)}, owner_id, cache) is False
    assert event_visible_to({"task_id": str(orphan)}, owner_id, cache) is False
    assert event_visible_to({"type": "task.event"}, owner_id, cache) is False
    assert cache[str(own_task)] is True
