import uuid
from collections import Counter

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import event

from minutes import bg_store
from minutes.api import app
from minutes.bg_store import create_task
from minutes.db import SessionLocal, session_scope
from minutes.models import Bucket, ServiceToken, Task, TaskHistory
from minutes.routers import (
    admin_buckets,
    background_task_artifacts,
    service_tokens,
    user_buckets,
)
from minutes.schemas import AdminCreateBucketRequest


def test_http_method_and_path_pairs_are_unique():
    route_keys = [
        (method, route.path)
        for route in app.routes
        for method in getattr(route, "methods", set())
        if method not in {"HEAD", "OPTIONS"}
    ]
    duplicates = {key: count for key, count in Counter(route_keys).items() if count > 1}

    assert duplicates == {}


def _json_schema_ref(paths, path, method, status):
    return paths[path][method]["responses"][str(status)]["content"]["application/json"][
        "schema"
    ]["$ref"]


def test_task_read_routes_publish_typed_openapi_responses():
    paths = app.openapi()["paths"]

    assert _json_schema_ref(paths, "/api/bg/tasks", "get", 200) == (
        "#/components/schemas/TaskListResponse"
    )
    assert _json_schema_ref(paths, "/api/bg/tasks/{task_id}/events", "get", 200) == (
        "#/components/schemas/TaskEventsResponse"
    )
    assert _json_schema_ref(paths, "/api/bg/histories", "post", 200) == (
        "#/components/schemas/BulkTaskHistoriesResponse"
    )
    assert _json_schema_ref(paths, "/api/bg/result/{task_id}", "get", 200) == (
        "#/components/schemas/ResultSuccess"
    )
    assert _json_schema_ref(paths, "/api/bg/result/{task_id}", "get", 404) == (
        "#/components/schemas/ErrorResponse"
    )
    assert _json_schema_ref(paths, "/api/bg/cancel/{task_id}", "post", 200) == (
        "#/components/schemas/TaskCancelledResponse"
    )
    assert _json_schema_ref(paths, "/api/bg/delete/{task_id}", "post", 200) == (
        "#/components/schemas/TaskDeletedResponse"
    )
    assert _json_schema_ref(paths, "/api/bg/task/{task_id}/rename", "post", 200) == (
        "#/components/schemas/TaskNameResponse"
    )
    assert _json_schema_ref(paths, "/api/auth/login", "post", 200) == (
        "#/components/schemas/AuthLoginResponse"
    )
    assert _json_schema_ref(paths, "/api/auth/login", "post", 401) == (
        "#/components/schemas/ErrorResponse"
    )
    events = paths["/api/bg/events"]["get"]["responses"]["200"]["content"]
    assert "application/json" not in events
    assert events["text/event-stream"]["schema"]["$ref"] == (
        "#/components/schemas/TaskEvent"
    )
    for artifact_path in (
        "/api/bg/minutes/{task_id}",
        "/api/bg/transcript/{task_id}",
        "/api/bg/summary/{task_id}",
        "/api/bg/action-items/{task_id}",
    ):
        assert _json_schema_ref(paths, artifact_path, "get", 202) == (
            "#/components/schemas/ResultPendingResponse"
        )
        assert _json_schema_ref(paths, artifact_path, "get", 404) == (
            "#/components/schemas/ErrorResponse"
        )
    minutes_200 = paths["/api/bg/minutes/{task_id}"]["get"]["responses"]["200"][
        "content"
    ]
    assert "application/json" not in minutes_200
    assert minutes_200["text/plain"]["schema"] == {"type": "string"}
    transcript_200 = paths["/api/bg/transcript/{task_id}"]["get"]["responses"]["200"][
        "content"
    ]
    assert "application/json" not in transcript_200
    assert set(transcript_200) == {"text/plain", "text/markdown"}
    assert _json_schema_ref(paths, "/api/bg/action-items/{task_id}", "get", 200) == (
        "#/components/schemas/ActionItemsResponse"
    )
    assert _json_schema_ref(paths, "/api/admin/buckets", "get", 200) == (
        "#/components/schemas/AdminBucketListResponse"
    )
    assert _json_schema_ref(paths, "/api/admin/buckets", "post", 200) == (
        "#/components/schemas/BucketNameResponse"
    )


def test_background_task_routes_are_owned_by_router_modules():
    expected_routes = {
        ("GET", "/api/bg/status/{task_id}"),
        ("GET", "/api/bg/result/{task_id}"),
        ("GET", "/api/bg/events"),
        ("GET", "/api/bg/tasks/{task_id}/events"),
        ("GET", "/api/bg/history/{task_id}"),
        ("POST", "/api/bg/task/{task_id}/rename"),
        ("POST", "/api/bg/task/{task_id}/regenerate-name"),
        ("GET", "/api/bg/tasks"),
        ("POST", "/api/bg/histories"),
        ("POST", "/api/bg/cancel/{task_id}"),
        ("POST", "/api/bg/delete/{task_id}"),
        ("POST", "/api/bg/force-delete/{task_id}"),
        ("POST", "/api/bg/undelete/{task_id}"),
        ("POST", "/api/bg/hard-delete/{task_id}"),
        ("GET", "/api/bg/minutes/{task_id}"),
        ("GET", "/api/bg/transcript/{task_id}"),
        ("GET", "/api/bg/summary/{task_id}"),
        ("GET", "/api/bg/action-items/{task_id}"),
    }
    background_routes = [
        route for route in app.routes if route.path.startswith("/api/bg")
    ]
    actual_routes = {
        (method, route.path)
        for route in background_routes
        for method in route.methods
        if method not in {"HEAD", "OPTIONS"}
    }

    assert actual_routes == expected_routes
    assert all(
        route.endpoint.__module__.startswith("minutes.routers.")
        for route in background_routes
    )


def test_admin_bucket_routes_are_owned_by_router_module():
    expected_routes = {
        ("GET", "/api/admin/buckets"),
        ("POST", "/api/admin/buckets"),
        ("DELETE", "/api/admin/buckets/{name}"),
    }
    routes = [
        route for route in app.routes if route.path.startswith("/api/admin/buckets")
    ]
    actual_routes = {
        (method, route.path)
        for route in routes
        for method in route.methods
        if method not in {"HEAD", "OPTIONS"}
    }

    assert actual_routes == expected_routes
    assert all(
        route.endpoint.__module__ == "minutes.routers.admin_buckets" for route in routes
    )


def test_service_token_routes_are_owned_by_router_module():
    expected_routes = {
        ("POST", "/api/service-tokens"),
        ("GET", "/api/service-tokens"),
        ("DELETE", "/api/service-tokens/{token_id}"),
    }
    routes = [
        route for route in app.routes if route.path.startswith("/api/service-tokens")
    ]
    actual_routes = {
        (method, route.path)
        for route in routes
        for method in route.methods
        if method not in {"HEAD", "OPTIONS"}
    }

    assert actual_routes == expected_routes
    assert all(
        route.endpoint.__module__ == "minutes.routers.service_tokens"
        for route in routes
    )


def test_upload_cleanup_routes_are_owned_by_router_module():
    expected_routes = {
        ("GET", "/api/admin/uploads/cleanup"),
        ("POST", "/api/admin/uploads/cleanup"),
    }
    routes = [
        route for route in app.routes if route.path == "/api/admin/uploads/cleanup"
    ]
    actual_routes = {
        (method, route.path)
        for route in routes
        for method in route.methods
        if method not in {"HEAD", "OPTIONS"}
    }

    assert actual_routes == expected_routes
    assert all(
        route.endpoint.__module__ == "minutes.routers.upload_cleanup"
        for route in routes
    )


def test_user_bucket_routes_are_owned_by_router_module():
    routes = [route for route in app.routes if route.path == "/api/buckets"]
    actual_methods = {
        method
        for route in routes
        for method in route.methods
        if method not in {"HEAD", "OPTIONS"}
    }

    assert actual_methods == {"GET", "POST"}
    assert all(
        route.endpoint.__module__ == "minutes.routers.user_buckets" for route in routes
    )


def test_auth_routes_are_owned_by_router_module():
    expected_routes = {
        ("GET", "/api/auth/features"),
        ("POST", "/api/auth/login"),
        ("POST", "/api/auth/logout"),
    }
    routes = [route for route in app.routes if route.path.startswith("/api/auth/")]
    actual_routes = {
        (method, route.path)
        for route in routes
        for method in route.methods
        if method not in {"HEAD", "OPTIONS"}
    }

    assert actual_routes == expected_routes
    assert all(
        route.endpoint.__module__ == "minutes.routers.authentication"
        for route in routes
    )


def test_upload_routes_are_owned_by_router_module():
    expected_routes = {
        ("POST", "/api/transcribe-upload"),
        ("POST", "/api/transcribe-upload-bg"),
    }
    routes = [
        route for route in app.routes if route.path.startswith("/api/transcribe-upload")
    ]
    actual_routes = {
        (method, route.path)
        for route in routes
        for method in route.methods
        if method not in {"HEAD", "OPTIONS"}
    }

    assert actual_routes == expected_routes
    assert all(
        route.endpoint.__module__ == "minutes.routers.uploads" for route in routes
    )


LEGACY_UNPREFIXED_ALIASES = {
    ("GET", "/auth/features"),
    ("POST", "/auth/login"),
    ("POST", "/auth/logout"),
    ("POST", "/transcribe-upload"),
    ("POST", "/transcribe-upload-bg"),
    ("GET", "/admin/uploads/cleanup"),
    ("POST", "/admin/uploads/cleanup"),
}


def test_legacy_unprefixed_aliases_stay_available_but_out_of_schema():
    actual_routes = {
        (method, route.path)
        for route in app.routes
        for method in getattr(route, "methods", set())
        if method not in {"HEAD", "OPTIONS"}
    }
    schema_paths = set(app.openapi()["paths"])

    assert LEGACY_UNPREFIXED_ALIASES <= actual_routes
    assert {path for _, path in LEGACY_UNPREFIXED_ALIASES}.isdisjoint(schema_paths)
    assert "/api/auth/features" in schema_paths
    assert "/api/transcribe-upload-bg" in schema_paths
    assert "/api/admin/uploads/cleanup" in schema_paths


def test_legacy_auth_features_alias_still_responds():
    response = TestClient(app).get("/auth/features")

    assert response.status_code == 200
    assert "is_admin" in response.json()


def test_pipeline_routes_are_owned_by_router_module():
    expected_routes = {
        ("GET", "/api/health"),
        ("POST", "/api/format-raw"),
    }
    routes = [
        route
        for route in app.routes
        if any(
            (method, route.path) in expected_routes
            for method in getattr(route, "methods", set())
        )
    ]
    actual_routes = {
        (method, route.path)
        for route in routes
        for method in route.methods
        if method not in {"HEAD", "OPTIONS"}
    }

    assert actual_routes == expected_routes
    assert all(
        route.endpoint.__module__ == "minutes.routers.pipeline" for route in routes
    )


def test_task_status_and_result_have_only_db_backed_routes():
    route_keys = {
        (method, route.path)
        for route in app.routes
        for method in getattr(route, "methods", set())
        if method not in {"HEAD", "OPTIONS"}
    }

    assert ("GET", "/api/status/{task_id}") not in route_keys
    assert ("GET", "/api/result/{task_id}") not in route_keys
    assert ("GET", "/api/bg/status/{task_id}") in route_keys
    assert ("GET", "/api/bg/result/{task_id}") in route_keys


def test_admin_bucket_creation_commits_once(monkeypatch):
    bucket_name = f"test-{uuid.uuid4()}"
    commits = []

    class FakeMinioService:
        def create_bucket(self, name, public=False):
            assert (name, public) == (bucket_name, True)

    def track_commit(_session):
        commits.append("commit")

    monkeypatch.setattr(admin_buckets, "MinioService", FakeMinioService)
    event.listen(SessionLocal.class_, "after_commit", track_commit)
    try:
        result = admin_buckets.create_bucket(
            AdminCreateBucketRequest(name=bucket_name, public=True)
        )
    finally:
        event.remove(SessionLocal.class_, "after_commit", track_commit)

    assert result == {"name": bucket_name}
    assert commits == ["commit"]
    with session_scope() as session:
        bucket = (
            session.query(Bucket.name, Bucket.public)
            .filter(Bucket.name == bucket_name)
            .one()
        )
        assert bucket == (bucket_name, True)
        session.query(Bucket).filter(Bucket.name == bucket_name).delete()


def test_user_bucket_creation_commits_once(monkeypatch):
    bucket_name = f"user-{uuid.uuid4()}"
    owner_id = uuid.uuid4()
    commits = []

    class FakeMinioClient:
        def bucket_exists(self, name):
            assert name == bucket_name
            return False

        def make_bucket(self, name):
            assert name == bucket_name

    class FakeMinioService:
        client = FakeMinioClient()

    def track_commit(_session):
        commits.append("commit")

    monkeypatch.setattr(user_buckets, "MinioService", FakeMinioService)
    event.listen(SessionLocal.class_, "after_commit", track_commit)
    try:
        result = user_buckets.create_bucket(
            user_buckets.CreateBucketRequest(name=bucket_name, public=True),
            x_user_id=str(owner_id),
        )
    finally:
        event.remove(SessionLocal.class_, "after_commit", track_commit)

    assert result["name"] == bucket_name
    assert result["owner_id"] == str(owner_id)
    assert result["public"] is True
    assert commits == ["commit"]
    with session_scope() as session:
        bucket = (
            session.query(Bucket.name, Bucket.owner_id, Bucket.public)
            .filter(Bucket.name == bucket_name)
            .one()
        )
        assert bucket == (bucket_name, owner_id, True)
        session.query(Bucket).filter(Bucket.name == bucket_name).delete()


def test_service_token_revocation_commits_once():
    token_id = uuid.uuid4()
    with session_scope() as session:
        session.add(
            ServiceToken(
                id=token_id,
                name="route-test",
                token_hash=uuid.uuid4().hex,
            )
        )

    commits = []

    def track_commit(_session):
        commits.append("commit")

    event.listen(SessionLocal.class_, "after_commit", track_commit)
    try:
        result = service_tokens.revoke_token(str(token_id))
    finally:
        event.remove(SessionLocal.class_, "after_commit", track_commit)

    assert result == {"revoked": True}
    assert commits == ["commit"]
    with session_scope() as session:
        revoked = (
            session.query(ServiceToken.revoked)
            .filter(ServiceToken.id == token_id)
            .scalar()
        )
        assert revoked is True
        session.query(ServiceToken).filter(ServiceToken.id == token_id).delete()


@pytest.mark.parametrize(
    "path",
    [
        "/api/bg/minutes/missing",
        "/api/bg/transcript/missing",
        "/api/bg/summary/missing",
        "/api/bg/action-items/missing",
    ],
)
def test_background_artifact_routes_return_404_for_unknown_task(monkeypatch, path):
    monkeypatch.setattr(background_task_artifacts, "get_task", lambda _task_id: None)

    response = TestClient(app).get(path)

    assert response.status_code == 404
    assert response.json() == {"error": "unknown task"}


def test_background_artifact_routes_return_202_when_pending(monkeypatch):
    monkeypatch.setattr(
        background_task_artifacts,
        "get_task",
        lambda _task_id: {"status": "transcribing", "error": None},
    )

    response = TestClient(app).get("/api/bg/minutes/task-1")

    assert response.status_code == 202
    assert response.json() == {"status": "transcribing", "error": None}


def test_action_items_json_matches_schema(monkeypatch):
    monkeypatch.setattr(
        background_task_artifacts,
        "get_task",
        lambda _task_id: {
            "status": "success",
            "result": {"action_items": [{"text": "Send report"}]},
        },
    )

    response = TestClient(app).get("/api/bg/action-items/task-1")

    assert response.status_code == 200
    assert response.json() == {
        "task_id": "task-1",
        "items": [{"text": "Send report"}],
    }


def test_action_items_reparse_empty_list_from_japanese_minutes(monkeypatch):
    minutes = """
【STEP3：アクション抽出】
- **誰が**：かたやまひろこ
- **何を**：医師の助けを頼む
- **いつまでに**：期限未設定
"""
    monkeypatch.setattr(
        background_task_artifacts,
        "get_task",
        lambda _task_id: {
            "status": "success",
            "result": {"action_items": [], "minutes": minutes},
        },
    )

    response = TestClient(app).get("/api/bg/action-items/task-1")

    assert response.status_code == 200
    payload = response.json()
    assert payload["task_id"] == "task-1"
    assert payload["items"][0]["who"] == "かたやまひろこ"
    assert payload["items"][0]["what"] == "医師の助けを頼む"


def test_background_history_rejects_invalid_task_id():
    response = TestClient(app).get("/api/bg/history/not-a-uuid")

    assert response.status_code == 400
    assert response.json() == {"error": "invalid task id"}


def test_background_rename_requires_name():
    response = TestClient(app).post("/api/bg/task/not-a-uuid/rename", json={"name": ""})

    assert response.status_code == 400
    assert response.json() == {"error": "missing name"}


def test_background_rename_persists_history_and_event(monkeypatch):
    task_id = uuid.uuid4()
    create_task(str(task_id))
    published = []
    operations = []

    def track_commit(_session):
        operations.append("commit")

    def track_publish(task_event):
        published.append(task_event)
        operations.append("publish")

    monkeypatch.setattr(bg_store, "publish_event", track_publish)
    event.listen(SessionLocal.class_, "after_commit", track_commit)
    try:
        response = TestClient(app).post(
            f"/api/bg/task/{task_id}/rename",
            json={"name": "Planning notes"},
        )
    finally:
        event.remove(SessionLocal.class_, "after_commit", track_commit)

    assert response.status_code == 200
    assert operations == ["commit", "publish"]
    with session_scope() as session:
        task = session.get(Task, task_id)
        history = (
            session.query(TaskHistory)
            .filter(
                TaskHistory.task_id == task_id,
                TaskHistory.event_type == "rename",
            )
            .one()
        )
        assert task is not None
        assert task.name == "Planning notes"
        assert history.payload == {"name": "Planning notes"}
    assert published[-1]["event_type"] == "rename"


def test_background_regenerate_name_commits_before_event(
    monkeypatch,
    tmp_path,
):
    task_id = uuid.uuid4()
    source = tmp_path / "meeting.txt"
    source.write_text(
        "Weekly engineering sync discussed the release plan.",
        encoding="utf-8",
    )
    create_task(str(task_id), metadata={"output_file": source.name})
    monkeypatch.setenv("OUTPUTS_DIR", str(tmp_path))
    published = []
    operations = []

    def track_commit(_session):
        operations.append("commit")

    def track_publish(task_event):
        published.append(task_event)
        operations.append("publish")

    monkeypatch.setattr(bg_store, "publish_event", track_publish)
    event.listen(SessionLocal.class_, "after_commit", track_commit)
    try:
        response = TestClient(app).post(
            f"/api/bg/task/{task_id}/regenerate-name"
        )
    finally:
        event.remove(SessionLocal.class_, "after_commit", track_commit)

    assert response.status_code == 200
    assert operations == ["commit", "publish"]
    generated_name = response.json()["name"]
    with session_scope() as session:
        task = session.get(Task, task_id)
        history = (
            session.query(TaskHistory)
            .filter(
                TaskHistory.task_id == task_id,
                TaskHistory.event_type == "rename",
            )
            .one()
        )
        assert task.name == generated_name
        assert history.payload == {"name": generated_name}
    assert published[-1]["payload"] == {"name": generated_name}


def test_background_regenerate_name_does_not_publish_when_file_is_missing(
    monkeypatch,
    tmp_path,
):
    task_id = uuid.uuid4()
    create_task(str(task_id), metadata={"output_file": "missing.txt"})
    monkeypatch.setenv("OUTPUTS_DIR", str(tmp_path))
    published = []
    monkeypatch.setattr(bg_store, "publish_event", published.append)

    response = TestClient(app).post(f"/api/bg/task/{task_id}/regenerate-name")

    assert response.status_code == 404
    assert response.json() == {"error": "output file not found"}
    with session_scope() as session:
        task = session.get(Task, task_id)
        rename_events = (
            session.query(TaskHistory)
            .filter(
                TaskHistory.task_id == task_id,
                TaskHistory.event_type == "rename",
            )
            .count()
        )
        assert task.name is None
        assert rename_events == 0
    assert published == []
