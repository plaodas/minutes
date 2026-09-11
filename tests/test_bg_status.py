from fastapi.testclient import TestClient

from minutes import api
from minutes.routers import background_tasks


def test_bg_status_uses_persisted_task_state(monkeypatch):
    task_id = "dd3a1d68-07f0-413a-b337-9f39c2d3ce76"
    monkeypatch.setattr(
        background_tasks,
        "get_task",
        lambda requested_id: {
            "id": requested_id,
            "status": "formatting",
            "progress": 100.0,
            "error": None,
        },
    )

    response = TestClient(api.app).get(f"/api/bg/status/{task_id}")

    assert response.status_code == 200
    assert response.json()["task_id"] == task_id
    assert response.json()["status"] == "formatting"
    assert response.json()["stage"] == "formatting"
    assert response.json()["error"] is None


def test_bg_result_uses_persisted_task_state(monkeypatch):
    task_id = "dd3a1d68-07f0-413a-b337-9f39c2d3ce76"
    monkeypatch.setattr(
        background_tasks,
        "get_task",
        lambda requested_id: {
            "id": requested_id,
            "status": "success",
            "result": {"output_file": "minutes.txt"},
        },
    )

    response = TestClient(api.app).get(f"/api/bg/result/{task_id}")

    assert response.status_code == 200
    assert response.json() == {
        "status": "success",
        "result": {"output_file": "minutes.txt"},
    }


def test_bg_task_events_rejects_invalid_task_id():
    response = TestClient(api.app).get("/api/bg/tasks/not-a-uuid/events")

    assert response.status_code == 400
    assert response.json() == {"error": "invalid task id"}
