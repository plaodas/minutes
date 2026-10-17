import uuid
from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient

from minutes.api import app
from minutes.db import session_scope
from minutes.models import AuditEvent


def _add_event(
    *,
    action: str,
    target_type: str,
    target_id: str,
    created_at: datetime,
    detail: dict | None = None,
) -> None:
    with session_scope() as session:
        session.add(
            AuditEvent(
                created_at=created_at,
                action=action,
                actor_kind="session",
                target_type=target_type,
                target_id=target_id,
                detail=detail,
            )
        )


def test_audit_event_list_requires_admin():
    response = TestClient(app).get("/api/audit-events")

    assert response.status_code == 403
    assert response.json() == {"error": "forbidden"}


def test_audit_event_list_is_newest_first_and_filterable(monkeypatch):
    monkeypatch.delenv("FORCE_ADMIN", raising=False)
    target_id = f"task-{uuid.uuid4().hex}"
    start = datetime(2026, 10, 17, 1, 0, tzinfo=timezone.utc)
    _add_event(
        action="task.delete",
        target_type="task",
        target_id=target_id,
        created_at=start,
        detail={"username": "kept"},
    )
    _add_event(
        action="task.undelete",
        target_type="task",
        target_id=target_id,
        created_at=start + timedelta(minutes=5),
    )
    _add_event(
        action="task.delete",
        target_type="bucket",
        target_id=target_id,
        created_at=start + timedelta(minutes=10),
    )

    client = TestClient(app)
    headers = {"X-Admin": "1"}
    listed = client.get(
        "/api/audit-events",
        params={"target_id": target_id, "limit": 1},
        headers=headers,
    )
    filtered = client.get(
        "/api/audit-events",
        params={
            "action": "task.delete",
            "target_type": "task",
            "target_id": target_id,
        },
        headers=headers,
    )

    assert listed.status_code == 200
    newest = listed.json()["events"]
    assert len(newest) == 1
    assert newest[0]["action"] == "task.delete"
    assert newest[0]["target_type"] == "bucket"
    assert newest[0]["actor_kind"] == "session"
    assert "password" not in str(newest[0])

    assert filtered.status_code == 200
    matches = filtered.json()["events"]
    assert [row["action"] for row in matches] == ["task.delete"]
    assert matches[0]["target_type"] == "task"
    assert matches[0]["detail"] == {"username": "kept"}

    blank = client.get(
        "/api/audit-events",
        params={"action": "  ", "target_type": "", "target_id": target_id},
        headers=headers,
    )
    assert blank.status_code == 200
    assert len(blank.json()["events"]) == 3


def test_audit_event_list_caps_limit_at_200(monkeypatch):
    monkeypatch.delenv("FORCE_ADMIN", raising=False)
    target_id = f"cap-{uuid.uuid4().hex}"
    start = datetime(2026, 10, 17, 2, 0, tzinfo=timezone.utc)
    with session_scope() as session:
        session.add_all(
            [
                AuditEvent(
                    created_at=start + timedelta(seconds=index),
                    action="auth.login.success",
                    actor_kind="session",
                    target_type="user",
                    target_id=target_id,
                )
                for index in range(201)
            ]
        )

    response = TestClient(app).get(
        "/api/audit-events",
        params={"target_id": target_id, "limit": 500},
        headers={"X-Admin": "1"},
    )

    assert response.status_code == 200
    events = response.json()["events"]
    assert len(events) == 200
    assert response.json()["has_more"] is True
    assert events[0]["created_at"].startswith("2026-10-17T02:03:20")


def test_audit_event_list_pages_older_than_the_last_row(monkeypatch):
    monkeypatch.delenv("FORCE_ADMIN", raising=False)
    target_id = f"page-{uuid.uuid4().hex}"
    moment = datetime(2026, 10, 17, 3, 0, tzinfo=timezone.utc)
    _add_event(
        action="task.delete",
        target_type="task",
        target_id=target_id,
        created_at=moment,
        detail={"order": "oldest"},
    )
    _add_event(
        action="task.undelete",
        target_type="task",
        target_id=target_id,
        created_at=moment,
        detail={"order": "middle"},
    )
    _add_event(
        action="task.force_delete",
        target_type="task",
        target_id=target_id,
        created_at=moment,
        detail={"order": "newest"},
    )
    _add_event(
        action="bucket.delete",
        target_type="bucket",
        target_id=target_id,
        created_at=moment + timedelta(minutes=1),
    )

    client = TestClient(app)
    headers = {"X-Admin": "1"}
    first = client.get(
        "/api/audit-events",
        params={"target_type": "task", "target_id": target_id, "limit": 1},
        headers=headers,
    )
    assert first.status_code == 200
    first_body = first.json()
    assert first_body["has_more"] is True
    assert first_body["events"][0]["detail"] == {"order": "newest"}

    cursor = first_body["events"][0]
    second = client.get(
        "/api/audit-events",
        params={
            "target_type": "task",
            "target_id": target_id,
            "limit": 1,
            "before_created_at": cursor["created_at"],
            "before_id": cursor["id"],
        },
        headers=headers,
    )
    assert second.status_code == 200
    second_body = second.json()
    assert second_body["has_more"] is True
    assert second_body["events"][0]["detail"] == {"order": "middle"}

    older = second_body["events"][0]
    third = client.get(
        "/api/audit-events",
        params={
            "target_type": "task",
            "target_id": target_id,
            "limit": 1,
            "before_created_at": older["created_at"],
            "before_id": older["id"],
        },
        headers=headers,
    )
    assert third.status_code == 200
    third_body = third.json()
    assert third_body["has_more"] is False
    assert third_body["events"][0]["detail"] == {"order": "oldest"}


def test_audit_event_list_rejects_a_partial_cursor(monkeypatch):
    monkeypatch.delenv("FORCE_ADMIN", raising=False)
    client = TestClient(app)
    headers = {"X-Admin": "1"}

    missing_id = client.get(
        "/api/audit-events",
        params={"before_created_at": "2026-10-17T03:00:00"},
        headers=headers,
    )
    missing_time = client.get(
        "/api/audit-events",
        params={"before_id": 1},
        headers=headers,
    )
    invalid_time = client.get(
        "/api/audit-events",
        params={"before_created_at": "yesterday", "before_id": 1},
        headers=headers,
    )

    assert missing_id.status_code == 400
    assert missing_time.status_code == 400
    assert invalid_time.status_code == 400
    assert missing_id.json() == {"error": "invalid audit cursor"}
