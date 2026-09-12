import os
from typing import Any


def _mapping(value: object) -> dict[str, Any] | None:
    return value if isinstance(value, dict) else None


def result_output_file(result: object) -> str | None:
    data = _mapping(result)
    if data is None:
        return None
    output_file = data.get("output_file")
    if isinstance(output_file, str) and output_file:
        return output_file
    nested = _mapping(data.get("result"))
    if nested is None:
        return None
    nested_file = nested.get("output_file")
    if isinstance(nested_file, str) and nested_file:
        return nested_file
    return None


def result_minio_info(result: object) -> dict[str, Any] | None:
    data = _mapping(result)
    if data is None:
        return None
    minio_info = data.get("minio")
    if not isinstance(minio_info, dict):
        nested = _mapping(data.get("result"))
        minio_info = nested.get("minio") if nested else None
    if not isinstance(minio_info, dict) or not minio_info.get("bucket"):
        return None
    return minio_info


def result_minio_object(result: object) -> tuple[str, str] | None:
    minio_info = result_minio_info(result)
    if minio_info is None:
        return None
    bucket = minio_info.get("bucket")
    object_name = minio_info.get("object")
    if (
        isinstance(bucket, str)
        and bucket
        and isinstance(object_name, str)
        and object_name
    ):
        return bucket, object_name
    return None


def local_output_path(output_file: str, outputs_dir: str | None = None) -> str:
    directory = (
        outputs_dir
        if outputs_dir is not None
        else os.environ.get("OUTPUTS_DIR", "outputs")
    )
    return os.path.join(directory, os.path.basename(output_file))
