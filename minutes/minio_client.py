import json
import logging
import os
from datetime import timedelta

from minio import Minio
from minio.error import S3Error

logger = logging.getLogger(__name__)


def make_minio_client():
    endpoint = os.environ.get("MINIO_ENDPOINT", "localhost:9000")
    access = os.environ.get("MINIO_ACCESS_KEY")
    secret = os.environ.get("MINIO_SECRET_KEY")
    if not access or not secret:
        raise RuntimeError("MINIO_ACCESS_KEY and MINIO_SECRET_KEY must be set")
    secure = os.environ.get("MINIO_SECURE", "false").lower() == "true"
    return Minio(endpoint, access_key=access, secret_key=secret, secure=secure)


class MinioService:
    def __init__(self, client=None):
        self.client = client or make_minio_client()

    def ensure_bucket(self, name: str, region: str | None = None):
        if not self.client.bucket_exists(name):
            self.client.make_bucket(name, location=region)

    def list_buckets(self):
        return list(self.client.list_buckets())

    def create_bucket(self, name: str, public: bool = False, region: str | None = None):
        if self.client.bucket_exists(name):
            raise ValueError("bucket already exists")
        self.client.make_bucket(name, location=region)
        if public:
            # set a simple public-read policy
            policy = {
                "Version": "2012-10-17",
                "Statement": [
                    {
                        "Effect": "Allow",
                        "Principal": {"AWS": ["*"]},
                        "Action": ["s3:GetObject"],
                        "Resource": [f"arn:aws:s3:::{name}/*"],
                    }
                ],
            }
            try:
                self.client.set_bucket_policy(name, json.dumps(policy))
            except S3Error:
                logger.debug("set_bucket_policy failed for %s", name, exc_info=True)

    def delete_bucket(self, name: str, force: bool = False):
        if force:
            # remove all objects first
            for obj in self.client.list_objects(name, recursive=True):
                try:
                    self.client.remove_object(name, obj.object_name)
                except S3Error:
                    logger.debug(
                        "remove_object failed for %s/%s",
                        name,
                        obj.object_name,
                        exc_info=True,
                    )
        self.client.remove_bucket(name)

    def list_objects(self, name: str, prefix: str = ""):
        return list(self.client.list_objects(name, prefix=prefix, recursive=True))

    def presigned_get(self, bucket: str, obj: str, expires: int = 3600):
        # Accept either an int (seconds) or a timedelta for expires.
        if isinstance(expires, (int, float)):
            expires = timedelta(seconds=int(expires))
        return self.client.get_presigned_url("GET", bucket, obj, expires=expires)

    def delete_object(self, bucket: str, obj: str, ignore_missing: bool = True):
        try:
            self.client.remove_object(bucket, obj)
        except S3Error:
            if not ignore_missing:
                raise
            logger.debug(
                "remove_object failed for %s/%s (ignored)", bucket, obj, exc_info=True
            )

    def delete_objects_with_prefix(
        self, bucket: str, prefix: str, ignore_missing: bool = True
    ):
        # iterate and remove objects under prefix
        for obj in self.client.list_objects(bucket, prefix=prefix, recursive=True):
            try:
                self.client.remove_object(bucket, obj.object_name)
            except S3Error:
                if not ignore_missing:
                    raise
                logger.debug(
                    "remove_object failed for %s/%s (ignored)",
                    bucket,
                    obj.object_name,
                    exc_info=True,
                )

    def _release_object(self, obj, bucket: str, object_name: str) -> None:
        try:
            obj.close()
        except (S3Error, OSError, AttributeError):
            logger.debug(
                "object close failed for %s/%s", bucket, object_name, exc_info=True
            )
        try:
            obj.release_conn()
        except (S3Error, OSError, AttributeError):
            logger.debug(
                "object release failed for %s/%s", bucket, object_name, exc_info=True
            )

    def iter_object(
        self, bucket: str, object_name: str, chunk_size: int = 32 * 1024
    ):
        obj = self.client.get_object(bucket, object_name)

        def chunks():
            try:
                for data in obj.stream(chunk_size):
                    if data:
                        yield data
            finally:
                self._release_object(obj, bucket, object_name)

        return chunks()

    def read_object_text(self, bucket: str, object_name: str) -> str:
        obj = self.client.get_object(bucket, object_name)
        try:
            data = obj.read()
        finally:
            self._release_object(obj, bucket, object_name)
        return data.decode("utf-8") if isinstance(data, bytes) else str(data)
