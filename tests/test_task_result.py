import os

import pytest

from minutes.task_result import (
    MissingOutputFileError,
    local_output_path,
    read_local_output_text,
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


def test_read_local_output_text(tmp_path, monkeypatch):
    monkeypatch.setenv("OUTPUTS_DIR", str(tmp_path))
    (tmp_path / "notes.txt").write_text("hello", encoding="utf-8")
    assert read_local_output_text({"output_file": "dir/notes.txt"}) == "hello"


def test_read_local_output_text_missing_path():
    with pytest.raises(MissingOutputFileError):
        read_local_output_text({})
