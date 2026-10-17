import json
import os
import time
import uuid
from contextlib import contextmanager

from fastapi.testclient import TestClient
from sqlalchemy.exc import SQLAlchemyError

from minutes.api import app
from minutes.auth import create_service_token, get_password_hash
from minutes.bg_store import create_task
from minutes.db import session_scope
from minutes.models import AuditEvent, Bucket, User
from minutes.routers import admin_buckets, background_task_lifecycle
from tests.auth_helpers import assign_task_owner, create_user, login


def _events(action: str, target_id: str) -> list[AuditEvent]:
    with session_scope() as session:
        rows = (
            session.query(AuditEvent)
            .filter(
                AuditEvent.action == action,
                AuditEvent.target_id == target_id,
            )
            .order_by(AuditEvent.id)
            .all()
        )
        session.expunge_all()
        return rows


def _stored(row: AuditEvent) -> str:
    return json.dumps(
        {
            "action": row.action,
            "actor_kind": row.actor_kind,
            "target_type": row.target_type,
            "target_id": row.target_id,
            "detail": row.detail,
        },
        default=str,
    )


def _admin_client() -> tuple[TestClient, uuid.UUID]:
    user_id = create_user()
    with session_scope() as session:
        user = session.get(User, user_id)
        assert user is not None
        user.is_admin = True
    return login(TestClient(app), user_id), user_id


def test_login_records_failure_and_success_without_password():
    username = f"audit-{uuid.uuid4().hex[:12]}"
    password = f"pw-{uuid.uuid4().hex}"
    user_id = uuid.uuid4()
    with session_scope() as session:
        session.add(
            User(
                id=user_id,
                username=username,
                password_hash=get_password_hash(password),
                is_admin=False,
            )
        )

    client = TestClient(app)
    unknown = client.post(
        "/api/auth/login",
        json={"username": f"missing-{username}", "password": password},
    )
    rejected = client.post(
        "/api/auth/login",
        json={"username": username, "password": "wrong-password"},
    )
    accepted = client.post(
        "/api/auth/login",
        json={"username": username, "password": password},
    )

    assert unknown.status_code == 401
    assert rejected.status_code == 401
    assert accepted.status_code == 200

    unknown_row = _events("auth.login.failure", f"missing-{username}")[0]
    assert unknown_row.actor_kind == "session"
    assert unknown_row.actor_user_id is None
    assert unknown_row.detail == {"username": f"missing-{username}"}
    assert password not in _stored(unknown_row)

    rejected_row = _events("auth.login.failure", str(user_id))[0]
    assert rejected_row.actor_user_id == user_id
    assert rejected_row.detail == {"username": username}
    assert "wrong-password" not in _stored(rejected_row)
    assert password not in _stored(rejected_row)

    success = _events("auth.login.success", str(user_id))[0]
    assert success.actor_kind == "session"
    assert success.actor_user_id == user_id
    assert success.detail == {"username": username}
    assert password not in _stored(success)


def test_failed_audit_write_does_not_fail_login(monkeypatch):
    @contextmanager
    def broken_scope():
        raise SQLAlchemyError("audit down")
        yield  # pragma: no cover

    monkeypatch.setattr("minutes.audit.session_scope", broken_scope)
    response = TestClient(app).post(
        "/api/auth/login",
        json={"username": f"missing-{uuid.uuid4().hex}", "password": "not-used"},
    )

    assert response.status_code == 401


def test_service_token_create_and_revoke_record_actor_without_plaintext(monkeypatch):
    monkeypatch.delenv("FORCE_ADMIN", raising=False)
    client, admin_id = _admin_client()
    created = client.post(
        "/api/service-tokens",
        json={"name": "audit-token", "user_id": str(admin_id)},
    )

    assert created.status_code == 200
    body = created.json()
    created_row = _events("service_token.create", body["id"])[0]
    assert created_row.actor_kind == "session"
    assert created_row.actor_user_id == admin_id
    assert created_row.detail == {"name": "audit-token", "user_id": str(admin_id)}
    assert body["token"] not in _stored(created_row)

    revoked = client.delete(f"/api/service-tokens/{body['id']}")

    assert revoked.status_code == 200
    revoked_row = _events("service_token.revoke", body["id"])[0]
    assert revoked_row.actor_kind == "session"
    assert revoked_row.actor_user_id == admin_id
    assert revoked_row.detail == {"name": "audit-token", "user_id": str(admin_id)}
    assert body["token"] not in _stored(revoked_row)


def test_external_provision_records_one_row_and_rotated_token_ids(monkeypatch):
    secret = "provision-audit-secret"
    monkeypatch.setenv("PROVISION_SECRET", secret)
    external_id = f"ext-{uuid.uuid4().hex}"
    client = TestClient(app)

    def provision():
        return client.post(
            "/api/external/users",
            json={"external_id": external_id},
            headers={"Authorization": f"Bearer {secret}"},
        )

    first = provision()
    second = provision()

    assert first.status_code == 200
    assert second.status_code == 200
    first_body = first.json()
    second_body = second.json()
    rows = _events("external_user.provision", first_body["user_id"])
    assert [row.actor_kind for row in rows] == ["provision", "provision"]
    assert rows[0].detail["external_id"] == external_id
    assert rows[0].detail["token_id"] == first_body["token_id"]
    assert rows[0].detail["revoked_token_ids"] == []
    assert rows[1].detail["token_id"] == second_body["token_id"]
    assert rows[1].detail["revoked_token_ids"] == [first_body["token_id"]]
    stored = _stored(rows[0]) + _stored(rows[1])
    assert first_body["token"] not in stored
    assert second_body["token"] not in stored
    assert secret not in stored


def test_task_delete_and_restore_record_the_session_user():
    task_id = uuid.uuid4()
    create_task(str(task_id))
    user_id = create_user()
    client = login(TestClient(app), user_id)
    assign_task_owner(task_id, user_id)

    assert client.post(f"/api/bg/delete/{task_id}").status_code == 200
    assert client.post(f"/api/bg/undelete/{task_id}").status_code == 200

    deleted = _events("task.delete", str(task_id))[0]
    restored = _events("task.undelete", str(task_id))[0]
    assert deleted.actor_kind == "session"
    assert deleted.actor_user_id == user_id
    assert deleted.actor_token_id is None
    assert restored.actor_kind == "session"
    assert restored.actor_user_id == user_id


def test_task_delete_via_service_token_records_the_token_id():
    task_id = uuid.uuid4()
    create_task(str(task_id))
    user_id = create_user()
    assign_task_owner(task_id, user_id)
    token, token_id = create_service_token(name="audit-delete", user_id=str(user_id))

    response = TestClient(app).post(
        f"/api/bg/delete/{task_id}",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    row = _events("task.delete", str(task_id))[0]
    assert row.actor_kind == "service_token"
    assert row.actor_user_id == user_id
    assert str(row.actor_token_id) == token_id
    assert token not in _stored(row)


def test_force_delete_and_enqueued_hard_delete_are_distinct(monkeypatch):
    monkeypatch.setattr(background_task_lifecycle, "ADMIN_API_TOKEN", None)
    monkeypatch.setattr(
        "minutes.tasks.hard_delete_task.delay",
        lambda *_args, **_kwargs: "job-audit",
    )
    user_id = create_user()
    client = login(TestClient(app), user_id)

    force_id = uuid.uuid4()
    create_task(str(force_id))
    assign_task_owner(force_id, user_id)
    assert client.post(f"/api/bg/force-delete/{force_id}").status_code == 200
    force_row = _events("task.force_delete", str(force_id))[0]
    assert force_row.actor_user_id == user_id
    assert _events("task.hard_delete", str(force_id)) == []

    hard_id = uuid.uuid4()
    create_task(str(hard_id))
    assign_task_owner(hard_id, user_id)
    response = client.post(f"/api/bg/hard-delete/{hard_id}")
    assert response.status_code == 200
    assert response.json()["enqueued"] is True
    hard_row = _events("task.hard_delete", str(hard_id))[0]
    assert hard_row.detail == {"enqueued": True}
    assert hard_row.actor_user_id == user_id


def test_upload_cleanup_records_deleted_names(monkeypatch, tmp_path):
    monkeypatch.delenv("FORCE_ADMIN", raising=False)
    old = tmp_path / "minutes_old.txt"
    old.write_text("x")
    old_mtime = int(time.time()) - 7200
    os.utime(old, (old_mtime, old_mtime))

    response = TestClient(app).post(
        "/api/admin/uploads/cleanup",
        json={"dir": str(tmp_path), "pattern": "minutes_", "older_than": 3600},
        headers={"X-Admin": "1"},
    )

    assert response.status_code == 200
    row = _events("upload.cleanup", str(tmp_path))[0]
    assert row.actor_kind == "admin_override"
    assert row.detail == {
        "count": 1,
        "pattern": "minutes_",
        "names": ["minutes_old.txt"],
    }


def test_bucket_delete_records_the_bucket_name(monkeypatch):
    monkeypatch.delenv("FORCE_ADMIN", raising=False)
    bucket_name = f"audit-{uuid.uuid4().hex[:12]}"

    class FakeMinioService:
        def delete_bucket(self, name, force=False):
            assert name == bucket_name

    monkeypatch.setattr(admin_buckets, "MinioService", FakeMinioService)
    with session_scope() as session:
        session.add(Bucket(name=bucket_name, public=False))

    response = TestClient(app).delete(
        f"/api/admin/buckets/{bucket_name}",
        headers={"X-Admin": "1"},
    )

    assert response.status_code == 200
    row = _events("bucket.delete", bucket_name)[0]
    assert row.actor_kind == "admin_override"
    assert row.target_type == "bucket"
    assert row.detail == {"force": False}
