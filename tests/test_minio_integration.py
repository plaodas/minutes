import os
import time
import requests
from minutes.minio_client import MinioService


def minio_available():
    return os.environ.get("MINIO_ENDPOINT") or os.environ.get("MINIO_ACCESS_KEY")


def test_minio_create_list_delete_bucket():
    if not minio_available():
        print("Skipping MinIO integration test: MINIO not configured")
        return

    svc = MinioService()
    name = f"test-bucket-{int(time.time())}"
    # create
    svc.create_bucket(name, public=False)
    buckets = svc.list_buckets()
    names = [b.name for b in buckets]
    assert name in names
    # delete
    svc.delete_bucket(name, force=True)
    buckets2 = svc.list_buckets()
    names2 = [b.name for b in buckets2]
    assert name not in names2
