import uuid

import pytest
import requests
from sqlalchemy.exc import OperationalError, SQLAlchemyError

from minutes.bg_store import create_task, get_task, update_task_status
from minutes.ollama import format_minutes_from_raw
from minutes.pipeline import task_runner
from minutes.schemas import TaskStage
from minutes.task_reclaim import reclaim_interrupted_tasks


def _enable_reclaim(monkeypatch):
    monkeypatch.setenv("RECLAIM_ON_START", "1")


def _only(monkeypatch, task_id, status, upload_path):
    monkeypatch.setattr(
        "minutes.task_reclaim._unfinished_tasks",
        lambda: [{"id": task_id, "status": status, "upload_path": upload_path}],
    )


def _pipeline(monkeypatch, seen, error=None):
    def factory(**_kwargs):
        class Service:
            def run(self, _input_path, **kwargs):
                seen.append(kwargs.get("metadata"))
                if error is not None:
                    raise error
                update_status = kwargs["update_status"]
                update_status(TaskStage.PREPROCESS)
                update_status(TaskStage.TRANSCRIBING)
                update_status(TaskStage.FORMATTING)
                return {
                    "minutes": "body",
                    "transcript": "raw",
                    "segments": [],
                    "output_file": "missing-output.txt",
                }

        return Service()

    monkeypatch.setattr(task_runner, "PipelineService", factory)


def test_redis_outage_leaves_the_unfinished_task_alone(monkeypatch, tmp_path):
    _enable_reclaim(monkeypatch)
    upload = tmp_path / "meeting.mp3"
    upload.write_bytes(b"audio")
    task_id = str(uuid.uuid4())
    create_task(task_id, metadata={"upload_path": str(upload)})
    update_task_status(task_id, "transcribing")
    _only(monkeypatch, task_id, "transcribing", str(upload))
    monkeypatch.setattr("minutes.task_reclaim._broker_state", lambda: None)
    monkeypatch.setattr(
        "minutes.task_reclaim._enqueue",
        lambda *_args: (_ for _ in ()).throw(AssertionError("enqueued")),
    )

    reclaim_interrupted_tasks()

    assert get_task(task_id)["status"] == "transcribing"


def test_worker_loss_restarts_formatting_from_the_beginning(monkeypatch):
    task_id = str(uuid.uuid4())
    create_task(
        task_id,
        metadata={"upload_path": "/tmp/audio.wav", "language": "English"},
    )
    update_task_status(task_id, "formatting")
    seen = []
    _pipeline(monkeypatch, seen)

    result = task_runner.run_audio_pipeline("/tmp/audio.wav", task_id)

    assert result["status"] == "success"
    assert seen[0]["language"] == "English"
    assert get_task(task_id)["status"] == "success"
    assert get_task(task_id)["fail_count"] == 0


def test_worker_still_running_is_not_reclaimed(monkeypatch, tmp_path):
    _enable_reclaim(monkeypatch)
    upload = tmp_path / "meeting.mp3"
    upload.write_bytes(b"audio")
    task_id = str(uuid.uuid4())
    create_task(task_id, metadata={"upload_path": str(upload)})
    update_task_status(task_id, "transcribing")
    _only(monkeypatch, task_id, "transcribing", str(upload))
    monkeypatch.setattr(
        "minutes.task_reclaim._broker_state",
        lambda: {"busy": {task_id}, "blob": b""},
    )
    monkeypatch.setattr(
        "minutes.task_reclaim._enqueue",
        lambda *_args: (_ for _ in ()).throw(AssertionError("enqueued")),
    )

    reclaim_interrupted_tasks()

    assert get_task(task_id)["status"] == "transcribing"


def test_ollama_outage_returns_fallback_after_three_timeouts(monkeypatch):
    timeouts = []

    def post(_url, json, timeout):
        timeouts.append(timeout)
        raise requests.ConnectionError("ollama down")

    monkeypatch.setattr("minutes.ollama.requests.post", post)
    monkeypatch.setenv("OLLAMA_TIMEOUT", "2")
    monkeypatch.setenv("OLLAMA_FALLBACK_MODELS", "")
    monkeypatch.setenv("OLLAMA_HOST", "http://ollama:11434")

    minutes = format_minutes_from_raw("会議を開いた。結論は来週である。")

    assert timeouts == [2, 4, 8]
    assert minutes.startswith("[FALLBACK] Ollama call failed:")
    assert "会議を開いた。" in minutes


def test_database_outage_lets_the_finished_pipeline_return(monkeypatch):
    task_id = str(uuid.uuid4())
    create_task(
        task_id,
        metadata={"upload_path": "/tmp/audio.wav", "language": "English"},
    )
    seen = []
    _pipeline(monkeypatch, seen)

    def database_down(*_args, **_kwargs):
        raise OperationalError("update", {}, Exception("db down"))

    monkeypatch.setattr(
        "minutes.task_state.TaskEventService.record_and_publish",
        database_down,
    )

    result = task_runner.run_audio_pipeline("/tmp/audio.wav", task_id)

    assert result["status"] == "success"
    assert seen[0]["language"] == "English"
    assert get_task(task_id)["status"] == "pending"


def test_database_outage_skips_reclaim(monkeypatch):
    _enable_reclaim(monkeypatch)
    monkeypatch.setattr(
        "minutes.task_reclaim._broker_state",
        lambda: {"busy": set(), "blob": b""},
    )

    def database_down():
        raise SQLAlchemyError("db down")

    monkeypatch.setattr("minutes.task_reclaim._unfinished_tasks", database_down)
    monkeypatch.setattr(
        "minutes.task_reclaim._enqueue",
        lambda *_args: (_ for _ in ()).throw(AssertionError("enqueued")),
    )

    reclaim_interrupted_tasks()


def test_whisper_failure_marks_the_task_failed_and_reraises(monkeypatch):
    task_id = str(uuid.uuid4())
    create_task(
        task_id,
        metadata={
            "upload_path": "/tmp/audio.wav",
            "language": "English",
            "minutes": "partial",
        },
    )
    _pipeline(monkeypatch, [], error=RuntimeError("preprocess failed: whisper"))

    with pytest.raises(RuntimeError, match="whisper"):
        task_runner.run_audio_pipeline("/tmp/audio.wav", task_id)

    stored = get_task(task_id)
    assert stored["status"] == "failed"
    assert stored["result"] == {"upload_path": "/tmp/audio.wav"}
    assert stored["fail_count"] == 1


def test_restart_reenqueues_when_the_broker_lost_the_job(monkeypatch, tmp_path):
    _enable_reclaim(monkeypatch)
    upload = tmp_path / "meeting.mp3"
    upload.write_bytes(b"audio")
    task_id = str(uuid.uuid4())
    create_task(task_id, metadata={"upload_path": str(upload), "language": "English"})
    update_task_status(task_id, "preprocess")
    _only(monkeypatch, task_id, "preprocess", str(upload))
    enqueued = []
    monkeypatch.setattr(
        "minutes.task_reclaim._broker_state",
        lambda: {"busy": set(), "blob": b""},
    )
    monkeypatch.setattr(
        "minutes.task_reclaim._enqueue",
        lambda tid, path: enqueued.append((tid, path)) or True,
    )

    reclaim_interrupted_tasks()

    assert enqueued == [(task_id, str(upload))]
    stored = get_task(task_id)
    assert stored["status"] == "failed"
    assert stored["result"]["language"] == "English"
