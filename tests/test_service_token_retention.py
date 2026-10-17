import uuid
from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient

from minutes.api import app
from minutes.auth import create_service_token
from minutes.db import session_scope
from minutes.models import ServiceToken
from minutes.service_token_retention import sweep_expired_service_tokens
from tests.auth_helpers import create_user, login
from tests.test_audit import _admin_client
from tests.test_external_provision import SECRET, _provision


def _stamp(token_id: str, revoked_at: datetime | None, *, revoked: bool = True) -> None:
    with session_scope() as session:
        token = session.get(ServiceToken, uuid.UUID(token_id))
        assert token is not None
        token.revoked = revoked
        token.revoked_at = revoked_at


def _exists(token_id: str) -> bool:
    with session_scope() as session:
        return session.get(ServiceToken, uuid.UUID(token_id)) is not None


def test_revoke_records_revoked_at(monkeypatch):
    monkeypatch.delenv("FORCE_ADMIN", raising=False)
    admin, admin_id = _admin_client()
    owner = login(TestClient(app), create_user())
    before = datetime.now(tz=timezone.utc)

    admin_token, admin_token_id = create_service_token(
        name="admin", user_id=str(admin_id)
    )
    own = owner.post("/api/my/service-tokens", json={"name": "mine"})

    assert admin.delete(f"/api/service-tokens/{admin_token_id}").status_code == 200
    assert owner.delete(f"/api/my/service-tokens/{own.json()['id']}").status_code == 200

    with session_scope() as session:
        admin_row = session.get(ServiceToken, uuid.UUID(admin_token_id))
        own_row = session.get(ServiceToken, uuid.UUID(own.json()["id"]))
        assert admin_row is not None and own_row is not None
        assert admin_row.revoked is True
        assert own_row.revoked is True
        for row in (admin_row, own_row):
            stamp = row.revoked_at
            assert stamp is not None
            if stamp.tzinfo is None:
                stamp = stamp.replace(tzinfo=timezone.utc)
            assert before <= stamp <= datetime.now(tz=timezone.utc)
    assert admin_token


def test_external_rotation_records_revoked_at(monkeypatch):
    monkeypatch.setenv("PROVISION_SECRET", SECRET)
    client = TestClient(app)
    external_id = f"ext-{uuid.uuid4().hex}"
    before = datetime.now(tz=timezone.utc)
    first = _provision(client, external_id)
    second = _provision(client, external_id)

    assert first.status_code == 200
    assert second.status_code == 200
    with session_scope() as session:
        old = session.get(ServiceToken, uuid.UUID(first.json()["token_id"]))
        current = session.get(ServiceToken, uuid.UUID(second.json()["token_id"]))
        assert old is not None and current is not None
        assert old.revoked is True
        assert current.revoked is False
        assert current.revoked_at is None
        stamp = old.revoked_at
        assert stamp is not None
        if stamp.tzinfo is None:
            stamp = stamp.replace(tzinfo=timezone.utc)
        assert before <= stamp <= datetime.now(tz=timezone.utc)


def test_sweep_deletes_only_tokens_revoked_more_than_30_days_ago():
    user_id = create_user()
    moment = datetime(2026, 10, 17, tzinfo=timezone.utc)
    _, old_id = create_service_token(name="old", user_id=str(user_id))
    _, recent_id = create_service_token(name="recent", user_id=str(user_id))
    _, active_id = create_service_token(name="active", user_id=str(user_id))
    _, unstamped_id = create_service_token(name="unstamped", user_id=str(user_id))
    _stamp(old_id, moment - timedelta(days=30, seconds=1))
    _stamp(recent_id, moment - timedelta(days=30))
    _stamp(unstamped_id, None)

    sweep_expired_service_tokens(moment)

    assert _exists(old_id) is False
    assert _exists(recent_id) is True
    assert _exists(active_id) is True
    assert _exists(unstamped_id) is True
