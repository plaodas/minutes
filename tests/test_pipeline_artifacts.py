import os

import pytest

from minutes.pipeline.artifacts import write_text_atomic


def test_write_text_atomic_replaces_destination(tmp_path):
    destination = tmp_path / "minutes.txt"

    result = write_text_atomic("formatted minutes", str(destination))

    assert result == str(destination)
    assert destination.read_text(encoding="utf-8") == "formatted minutes"
    assert list(tmp_path.glob("*.tmp")) == []


def test_write_text_atomic_removes_temporary_file_on_failure(monkeypatch, tmp_path):
    destination = tmp_path / "minutes.txt"

    def fail_replace(_source, _destination):
        raise OSError("replace failed")

    monkeypatch.setattr(os, "replace", fail_replace)

    with pytest.raises(OSError, match="replace failed"):
        write_text_atomic("formatted minutes", str(destination))

    assert not destination.exists()
    assert list(tmp_path.glob("*.tmp")) == []
