from minio import Minio
from minio.error import S3Error
import os
import json


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
            except Exception:
                # non-fatal
                pass

    def delete_bucket(self, name: str, force: bool = False):
        if force:
            # remove all objects first
            for obj in self.client.list_objects(name, recursive=True):
                try:
                    self.client.remove_object(name, obj.object_name)
                except Exception:
                    pass
        self.client.remove_bucket(name)

    def list_objects(self, name: str, prefix: str = ""):
        return list(self.client.list_objects(name, prefix=prefix, recursive=True))

    def presigned_get(self, bucket: str, obj: str, expires: int = 3600):
        return self.client.get_presigned_url("GET", bucket, obj, expires=expires)
