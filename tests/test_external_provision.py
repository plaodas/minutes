import uuid

from fastapi.testclient import TestClient

from minutes.api import app
from minutes.db import session_scope
from minutes.models import User

SECRET = "provision-test-secret"


def _client(monkeypatch, secret: str | None) -> TestClient:
    if secret is None:
        monkeypatch.delenv("PROVISION_SECRET", raising=False)
    else:
        monkeypatch.setenv("PROVISION_SECRET", secret)
    return TestClient(app)


def _provision(client: TestClient, external_id: str, secret: str = SECRET):
    return client.post(
        "/api/external/users",
        json={"external_id": external_id},
        headers={"Authorization": f"Bearer {secret}"},
    )


def test_external_provision_is_hidden_without_secret(monkeypatch):
    client = _client(monkeypatch, None)
    response = _provision(client, f"ext-{uuid.uuid4().hex}", secret="anything")

    assert response.status_code == 404
    assert response.json() == {"error": "not found"}


def test_external_provision_rejects_wrong_secret(monkeypatch):
    client = _client(monkeypatch, SECRET)
    response = _provision(client, f"ext-{uuid.uuid4().hex}", secret="wrong-secret")

    assert response.status_code == 401
    assert response.json() == {"error": "invalid credentials"}


def test_external_provision_rejects_blank_external_id(monkeypatch):
    client = _client(monkeypatch, SECRET)

    blank = _provision(client, "   ")
    too_long = _provision(client, "x" * 256)

    assert blank.status_code == 400
    assert blank.json() == {"error": "invalid external_id"}
    assert too_long.status_code == 400
    assert too_long.json() == {"error": "invalid external_id"}


def test_external_provision_token_can_list_tasks(monkeypatch):
    client = _client(monkeypatch, SECRET)
    external_id = f"ext-{uuid.uuid4().hex}"
    created = _provision(client, external_id)

    assert created.status_code == 200
    body = created.json()
    listed = client.get(
        "/api/bg/tasks",
        headers={"Authorization": f"Bearer {body['token']}"},
    )

    assert listed.status_code == 200
    assert listed.json()["tasks"] == []
    with session_scope() as session:
        user = session.get(User, uuid.UUID(body["user_id"]))
        assert user is not None
        assert user.is_admin is False
        assert user.external_subject == external_id


def test_external_provision_rotates_token_for_same_user(monkeypatch):
    client = _client(monkeypatch, SECRET)
    external_id = f"ext-{uuid.uuid4().hex}"
    first = _provision(client, external_id)
    second = _provision(client, external_id)

    assert first.status_code == 200
    assert second.status_code == 200
    first_body = first.json()
    second_body = second.json()
    assert first_body["user_id"] == second_body["user_id"]
    assert first_body["token"] != second_body["token"]

    old = client.get(
        "/api/bg/tasks",
        headers={"Authorization": f"Bearer {first_body['token']}"},
    )
    new = client.get(
        "/api/bg/tasks",
        headers={"Authorization": f"Bearer {second_body['token']}"},
    )

    assert old.status_code == 401
    assert new.status_code == 200


def test_external_provision_separates_users(monkeypatch):
    client = _client(monkeypatch, SECRET)
    first = _provision(client, f"ext-{uuid.uuid4().hex}")
    second = _provision(client, f"ext-{uuid.uuid4().hex}")

    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json()["user_id"] != second.json()["user_id"]
