import os
from fastapi.testclient import TestClient

from backend.app import app


def test_auth_features_default(monkeypatch):
    # ensure FORCE_ADMIN not set
    monkeypatch.delenv("FORCE_ADMIN", raising=False)
    client = TestClient(app)
    r = client.get("/auth/features")
    assert r.status_code == 200
    assert r.json().get("is_admin") is False


def test_auth_features_header_admin(monkeypatch):
    monkeypatch.delenv("FORCE_ADMIN", raising=False)
    client = TestClient(app)
    r = client.get("/auth/features", headers={"X-Admin": "1"})
    assert r.status_code == 200
    assert r.json().get("is_admin") is True


def test_auth_features_force_env(monkeypatch):
    monkeypatch.setenv("FORCE_ADMIN", "true")
    client = TestClient(app)
    r = client.get("/auth/features")
    assert r.status_code == 200
    assert r.json().get("is_admin") is True
