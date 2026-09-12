import uuid
from collections import Counter

import pytest
from fastapi.testclient import TestClient

from minutes import bg_store
from minutes.api import app
from minutes.bg_store import create_task
from minutes.db import session_scope
from minutes.models import Task, TaskHistory
from minutes.routers import background_task_artifacts


def test_http_method_and_path_pairs_are_unique():
    route_keys = [
        (method, route.path)
        for route in app.routes
        for method in getattr(route, "methods", set())
        if method not in {"HEAD", "OPTIONS"}
    ]
    duplicates = {key: count for key, count in Counter(route_keys).items() if count > 1}

    assert duplicates == {}


def test_background_task_routes_are_owned_by_router_modules():
    expected_routes = {
        ("GET", "/api/bg/status/{task_id}"),
        ("GET", "/api/bg/result/{task_id}"),
        ("GET", "/api/bg/events"),
        ("GET", "/api/bg/tasks/{task_id}/events"),
        ("GET", "/api/bg/history/{task_id}"),
        ("POST", "/api/bg/task/{task_id}/rename"),
        ("POST", "/api/bg/task/{task_id}/regenerate-name"),
        ("GET", "/api/bg/tasks"),
        ("POST", "/api/bg/histories"),
        ("POST", "/api/bg/cancel/{task_id}"),
        ("POST", "/api/bg/delete/{task_id}"),
        ("POST", "/api/bg/force-delete/{task_id}"),
        ("POST", "/api/bg/undelete/{task_id}"),
        ("POST", "/api/bg/hard-delete/{task_id}"),
        ("GET", "/api/bg/minutes/{task_id}"),
        ("GET", "/api/bg/transcript/{task_id}"),
        ("GET", "/api/bg/summary/{task_id}"),
        ("GET", "/api/bg/action-items/{task_id}"),
    }
    background_routes = [
        route for route in app.routes if route.path.startswith("/api/bg")
    ]
    actual_routes = {
        (method, route.path)
        for route in background_routes
        for method in route.methods
        if method not in {"HEAD", "OPTIONS"}
    }

    assert actual_routes == expected_routes
    assert all(
        route.endpoint.__module__.startswith("minutes.routers.")
        for route in background_routes
    )


@pytest.mark.parametrize(
    "path",
    [
        "/api/bg/minutes/missing",
        "/api/bg/transcript/missing",
        "/api/bg/summary/missing",
        "/api/bg/action-items/missing",
    ],
)
def test_background_artifact_routes_return_404_for_unknown_task(monkeypatch, path):
    monkeypatch.setattr(background_task_artifacts, "get_task", lambda _task_id: None)

    response = TestClient(app).get(path)

    assert response.status_code == 404
    assert response.json() == {"error": "unknown task"}


def test_background_history_rejects_invalid_task_id():
    response = TestClient(app).get("/api/bg/history/not-a-uuid")

    assert response.status_code == 400
    assert response.json() == {"error": "invalid task id"}


def test_background_rename_requires_name():
    response = TestClient(app).post("/api/bg/task/not-a-uuid/rename", json={"name": ""})

    assert response.status_code == 400
    assert response.json() == {"error": "missing name"}


def test_background_rename_persists_history_and_event(monkeypatch):
    task_id = uuid.uuid4()
    create_task(str(task_id))
    published = []
    monkeypatch.setattr(bg_store, "publish_event", published.append)

    response = TestClient(app).post(
        f"/api/bg/task/{task_id}/rename",
        json={"name": "Planning notes"},
    )

    assert response.status_code == 200
    with session_scope() as session:
        task = session.get(Task, task_id)
        history = (
            session.query(TaskHistory)
            .filter(
                TaskHistory.task_id == task_id,
                TaskHistory.event_type == "rename",
            )
            .one()
        )
        assert task is not None
        assert task.name == "Planning notes"
        assert history.payload == {"name": "Planning notes"}
    assert published[-1]["event_type"] == "rename"
