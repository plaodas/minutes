import os
import types
import logging
import tempfile

import minutes.tasks as tasks


class DummySelf:
    def __init__(self, id="test-task"):
        self.request = types.SimpleNamespace(id=id)


def _make_files(tmp_path):
    inp = tmp_path / "input.wav"
    inp.write_bytes(b"RIFF....")
    base = str(inp.with_suffix(""))
    mono = base + "_mono.wav"
    norm = base + "_norm.wav"
    clean = base + "_clean.wav"
    for p in (mono, norm, clean):
        with open(p, "wb") as fh:
            fh.write(b"WAVE")
    return str(inp), mono, norm, clean


def test_cleanup_intermediates_enabled(monkeypatch, tmp_path):
    # Arrange: create input and intermediate files
    input_path, mono, norm, clean = _make_files(tmp_path)

    # Patch heavy functions to short-circuit processing
    monkeypatch.setattr(tasks, "preprocess", lambda p: (mono, norm, clean))
    monkeypatch.setattr(tasks, "transcribe", lambda c, **kw: ("raw", []))
    monkeypatch.setattr(tasks, "format_minutes_from_raw", lambda r: "minutes")
    monkeypatch.setattr(tasks, "update_task_success", lambda tid, structured, db=None: None)
    monkeypatch.setattr(tasks, "update_task_status", lambda *a, **k: None)
    monkeypatch.setattr(tasks, "update_task_progress", lambda *a, **k: None)

    # Ensure cleanup enabled
    monkeypatch.setenv("DELETE_INTERMEDIATE", "true")
    # ensure outputs go to tmp dir to avoid permission issues
    monkeypatch.setenv("OUTPUTS_DIR", str(tmp_path / "outputs"))

    # Act
    # call the task run method; Celery Task will be used as `self`
    tasks.process_audio.run(input_path)

    # Assert: intermediate files removed
    assert not os.path.exists(mono)
    assert not os.path.exists(norm)
    assert not os.path.exists(clean)


def test_no_cleanup_when_disabled(monkeypatch, tmp_path):
    input_path, mono, norm, clean = _make_files(tmp_path)

    monkeypatch.setattr(tasks, "preprocess", lambda p: (mono, norm, clean))
    monkeypatch.setattr(tasks, "transcribe", lambda c, **kw: ("raw", []))
    monkeypatch.setattr(tasks, "format_minutes_from_raw", lambda r: "minutes")
    monkeypatch.setattr(tasks, "update_task_success", lambda tid, structured, db=None: None)
    monkeypatch.setattr(tasks, "update_task_status", lambda *a, **k: None)
    monkeypatch.setattr(tasks, "update_task_progress", lambda *a, **k: None)

    monkeypatch.setenv("DELETE_INTERMEDIATE", "false")
    monkeypatch.setenv("OUTPUTS_DIR", str(tmp_path / "outputs"))

    tasks.process_audio.run(input_path)

    assert os.path.exists(mono)
    assert os.path.exists(norm)
    assert os.path.exists(clean)
