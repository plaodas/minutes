import uuid

from fastapi.testclient import TestClient

from minutes.api import app
from minutes.db import session_scope
from minutes.models import AuditEvent, ServiceToken
from tests.auth_helpers import create_user, login
from tests.test_audit import _admin_client


def _named(name: str) -> int:
    with session_scope() as session:
        return session.query(ServiceToken).filter(ServiceToken.name == name).count()


def test_new_token_requires_an_existing_user(monkeypatch):
    monkeypatch.delenv("FORCE_ADMIN", raising=False)
    client, admin_id = _admin_client()
    name = f"needs-user-{uuid.uuid4().hex}"

    missing = client.post("/api/service-tokens", json={"name": name})
    invalid = client.post(
        "/api/service-tokens",
        json={"name": name, "user_id": "not-a-uuid"},
    )
    unknown = client.post(
        "/api/service-tokens",
        json={"name": name, "user_id": str(uuid.uuid4())},
    )
    created = client.post(
        "/api/service-tokens",
        json={"name": name, "user_id": str(admin_id)},
    )

    assert missing.status_code == 400
    assert invalid.status_code == 400
    assert unknown.status_code == 400
    assert created.status_code == 200
    assert _named(name) == 1
    with session_scope() as session:
        token = session.get(ServiceToken, uuid.UUID(created.json()["id"]))
        assert token is not None
        assert token.user_id == admin_id


def test_admin_user_list_is_names_only(monkeypatch):
    monkeypatch.delenv("FORCE_ADMIN", raising=False)
    username = f"listed-{uuid.uuid4().hex[:8]}"
    user_id = create_user(username)
    client, _admin_id = _admin_client()
    outsider = login(TestClient(app), create_user())

    denied = outsider.get("/api/users")
    listed = client.get("/api/users")

    assert denied.status_code == 403
    assert listed.status_code == 200
    match = next(user for user in listed.json()["users"] if user["id"] == str(user_id))
    assert match == {"id": str(user_id), "username": username}
    assert "password" not in listed.text


def test_user_issues_a_token_for_themselves_only(monkeypatch):
    monkeypatch.delenv("FORCE_ADMIN", raising=False)
    owner_id = create_user()
    other_id = create_user()
    owner = login(TestClient(app), owner_id)
    other = login(TestClient(app), other_id)
    name = f"mine-{uuid.uuid4().hex}"

    denied = owner.post(
        "/api/service-tokens",
        json={"name": name, "user_id": str(owner_id)},
    )
    created = owner.post(
        "/api/my/service-tokens",
        json={"name": name, "user_id": str(other_id)},
    )

    assert denied.status_code == 403
    assert created.status_code == 200
    token_id = created.json()["id"]
    assert created.json()["token"]
    with session_scope() as session:
        token = session.get(ServiceToken, uuid.UUID(token_id))
        assert token is not None
        assert token.user_id == owner_id
        row = (
            session.query(AuditEvent)
            .filter(
                AuditEvent.action == "service_token.create",
                AuditEvent.target_id == token_id,
            )
            .one()
        )
        assert row.actor_kind == "session"
        assert row.actor_user_id == owner_id
        assert row.detail == {"name": name, "user_id": str(owner_id)}
        assert created.json()["token"] not in str(row.detail)

    own_list = owner.get("/api/my/service-tokens")
    other_list = other.get("/api/my/service-tokens")
    hidden = other.delete(f"/api/my/service-tokens/{token_id}")
    revoked = owner.delete(f"/api/my/service-tokens/{token_id}")

    assert own_list.status_code == 200
    assert [item["id"] for item in own_list.json()["tokens"]] == [token_id]
    assert own_list.json()["tokens"][0]["user_id"] == str(owner_id)
    assert other_list.json()["tokens"] == []
    assert hidden.status_code == 404
    assert revoked.status_code == 200
    with session_scope() as session:
        token = session.get(ServiceToken, uuid.UUID(token_id))
        assert token is not None
        assert token.revoked is True
