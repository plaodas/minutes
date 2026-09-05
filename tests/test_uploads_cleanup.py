import os
import time
import tempfile
from fastapi.testclient import TestClient
from backend.app import app


def touch(path, mtime=None):
    with open(path, "w") as f:
        f.write("x")
    if mtime is not None:
        os.utime(path, (mtime, mtime))


def test_cleanup_dry_run(monkeypatch, tmp_path):
    # create two files, one old
    old = tmp_path / "minutes_old.txt"
    recent = tmp_path / "minutes_new.txt"
    now = int(time.time())
    touch(str(old), mtime=now - 7200)
    touch(str(recent), mtime=now)

    client = TestClient(app)
    # ensure admin
    headers = {"X-Admin": "1"}
    params = {"dir": str(tmp_path), "pattern": "minutes_", "older_than": 3600}
    r = client.get("/admin/uploads/cleanup", params=params, headers=headers)
    assert r.status_code == 200
    data = r.json()
    assert data["count"] == 1
    assert data["candidates"][0]["name"] == "minutes_old.txt"


def test_cleanup_post_delete(monkeypatch, tmp_path):
    f = tmp_path / "minutes_to_delete.txt"
    now = int(time.time())
    touch(str(f), mtime=now - 7200)

    client = TestClient(app)
    headers = {"X-Admin": "1"}
    payload = {"dir": str(tmp_path), "pattern": "minutes_", "older_than": 3600}
    r = client.post("/admin/uploads/cleanup", json=payload, headers=headers)
    assert r.status_code == 200
    data = r.json()
    assert data["count"] == 1
    assert not f.exists()
