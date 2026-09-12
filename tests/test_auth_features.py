from fastapi.testclient import TestClient

from backend.app import app


def test_auth_features_default(monkeypatch):
    # ensure FORCE_ADMIN not set
    monkeypatch.delenv("FORCE_ADMIN", raising=False)
    client = TestClient(app)
    r = client.get("/api/auth/features")
    assert r.status_code == 200
    assert r.json().get("is_admin") is False


def test_auth_features_header_admin(monkeypatch):
    monkeypatch.delenv("FORCE_ADMIN", raising=False)
    client = TestClient(app)
    r = client.get("/api/auth/features", headers={"X-Admin": "1"})
    assert r.status_code == 200
    assert r.json().get("is_admin") is True


def test_auth_features_force_env(monkeypatch):
    monkeypatch.setenv("FORCE_ADMIN", "true")
    client = TestClient(app)
    r = client.get("/api/auth/features")
    assert r.status_code == 200
    assert r.json().get("is_admin") is True


def test_auth_login_rejects_unknown_user():
    response = TestClient(app).post(
        "/api/auth/login",
        json={"username": "missing-user", "password": "invalid"},
    )

    assert response.status_code == 401
    assert response.json() == {"error": "invalid credentials"}


def test_auth_logout_clears_session_cookie():
    response = TestClient(app).post("/api/auth/logout")

    assert response.status_code == 200
    assert response.json() == {"logged_out": True}
    assert "minutes_session=" in response.headers["set-cookie"]
    assert "Max-Age=0" in response.headers["set-cookie"]
