from fastapi.testclient import TestClient

from minutes import app_lifecycle, sse
from minutes.api import app


def test_app_uses_dedicated_lifespan():
    assert app.router.lifespan_context.__module__ == "minutes.app_lifecycle"


def test_lifespan_starts_and_stops_services(monkeypatch):
    calls = []
    monkeypatch.setenv("REDIS_URL", "redis://example:6379/0")
    monkeypatch.setattr(
        app_lifecycle,
        "reconcile_once",
        lambda: calls.append("reconcile"),
    )
    monkeypatch.setattr(
        sse,
        "start_redis_listener",
        lambda url: calls.append(("start_redis", url)),
    )
    monkeypatch.setattr(
        sse,
        "stop_redis_listener",
        lambda: calls.append("stop_redis"),
    )

    with TestClient(app):
        reconcile_task = app.state.reconcile_task
        assert calls == [
            "reconcile",
            ("start_redis", "redis://example:6379/0"),
        ]
        assert not reconcile_task.done()

    assert reconcile_task.done()
    assert calls[-1] == "stop_redis"
