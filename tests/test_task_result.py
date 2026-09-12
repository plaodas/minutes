import os

from minutes.task_result import (
    local_output_path,
    result_minio_info,
    result_minio_object,
    result_output_file,
)


def test_result_output_file_prefers_top_level():
    assert (
        result_output_file(
            {"output_file": "a.txt", "result": {"output_file": "b.txt"}}
        )
        == "a.txt"
    )


def test_result_output_file_reads_nested_value():
    assert result_output_file({"result": {"output_file": "b.txt"}}) == "b.txt"
    assert result_output_file({"output_file": ""}) is None
    assert result_output_file(None) is None


def test_result_minio_info_and_object():
    nested = {"result": {"minio": {"bucket": "outputs", "object": "minutes/a.txt"}}}
    assert result_minio_info(nested) == {
        "bucket": "outputs",
        "object": "minutes/a.txt",
    }
    assert result_minio_object(nested) == ("outputs", "minutes/a.txt")
    assert result_minio_object({"minio": {"bucket": "outputs"}}) is None


def test_local_output_path_uses_basename(monkeypatch):
    monkeypatch.setenv("OUTPUTS_DIR", os.path.join("tmp", "outs"))
    assert local_output_path("dir/file.txt") == os.path.join("tmp", "outs", "file.txt")
