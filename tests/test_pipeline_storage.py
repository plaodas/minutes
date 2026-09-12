from datetime import datetime, timezone

from minutes.pipeline.storage import cache_minutes_artifact


class FakeClient:
    def __init__(self):
        self.uploads = []

    def fput_object(self, bucket, object_name, output_file):
        self.uploads.append((bucket, object_name, output_file))


class FakeService:
    def __init__(self):
        self.client = FakeClient()
        self.ensured = []
        self.presigned = []

    def ensure_bucket(self, bucket):
        self.ensured.append(bucket)

    def presigned_get(self, bucket, object_name, expires):
        self.presigned.append((bucket, object_name, expires))
        return "https://example.test/minutes"


def test_cache_minutes_artifact_returns_metadata(monkeypatch):
    service = FakeService()
    monkeypatch.setenv("MINIO_DEFAULT_BUCKET", "minutes")
    monkeypatch.setenv("MINIO_PRESIGNED_EXPIRES", "120")

    result = cache_minutes_artifact(
        task_id="task-1",
        timestamp="20260912010101",
        output_file="outputs/minutes.txt",
        service_factory=lambda: service,
        now=lambda: datetime(2026, 9, 12, tzinfo=timezone.utc),
    )

    assert service.ensured == ["minutes"]
    assert service.client.uploads == [
        ("minutes", "minutes/task-1/minutes_20260912010101.txt", "outputs/minutes.txt")
    ]
    assert result == {
        "bucket": "minutes",
        "object": "minutes/task-1/minutes_20260912010101.txt",
        "url": "https://example.test/minutes",
        "expires": 120,
        "expires_at": "2026-09-12T00:02:00+00:00Z",
    }


def test_cache_minutes_artifact_is_optional(monkeypatch):
    monkeypatch.delenv("MINIO_DEFAULT_BUCKET", raising=False)
    monkeypatch.delenv("MINIO_BUCKET", raising=False)

    assert cache_minutes_artifact("task-1", "stamp", "minutes.txt") is None


def test_cache_minutes_artifact_ignores_upload_failure(monkeypatch):
    service = FakeService()
    monkeypatch.setenv("MINIO_DEFAULT_BUCKET", "minutes")
    monkeypatch.setattr(
        service.client,
        "fput_object",
        lambda *_args: (_ for _ in ()).throw(OSError("upload failed")),
    )

    assert (
        cache_minutes_artifact(
            "task-1",
            "stamp",
            "minutes.txt",
            service_factory=lambda: service,
        )
        is None
    )
