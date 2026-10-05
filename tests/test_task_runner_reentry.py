import uuid

from minutes.bg_store import (
    create_task,
    get_task,
    update_task_status,
    update_task_success,
)
from minutes.pipeline import task_runner
from minutes.schemas import TaskStage


def _block_pipeline(monkeypatch, seen):
    def factory(**_kwargs):
        class Service:
            def run(self, _input_path, **kwargs):
                seen.append(kwargs.get("metadata"))
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


def test_success_is_not_run_again(monkeypatch):
    task_id = str(uuid.uuid4())
    create_task(task_id, metadata={"minutes": "kept"})
    update_task_success(task_id, {"minutes": "kept", "output_file": "missing.txt"})
    seen = []
    _block_pipeline(monkeypatch, seen)

    result = task_runner.run_audio_pipeline("/tmp/audio.wav", task_id)

    assert seen == []
    assert result["status"] == "success"
    assert result["result"]["minutes"] == "kept"


def test_cancelled_is_not_run_again(monkeypatch):
    from minutes.bg_store import update_task_cancelled

    task_id = str(uuid.uuid4())
    create_task(task_id, metadata={"upload_path": "/tmp/audio.wav"})
    update_task_cancelled(task_id)
    seen = []
    _block_pipeline(monkeypatch, seen)

    result = task_runner.run_audio_pipeline("/tmp/audio.wav", task_id)

    assert seen == []
    assert result["status"] == "cancelled"


def test_interrupted_stage_restarts_with_upload_metadata(monkeypatch):
    task_id = str(uuid.uuid4())
    create_task(
        task_id,
        metadata={
            "upload_path": "/tmp/audio.wav",
            "upload_filename": "audio.wav",
            "language": "English",
            "minutes": "partial",
        },
    )
    update_task_status(task_id, "transcribing")
    seen = []
    _block_pipeline(monkeypatch, seen)

    result = task_runner.run_audio_pipeline("/tmp/audio.wav", task_id)

    assert result["status"] == "success"
    assert seen[0]["language"] == "English"
    assert seen[0]["upload_path"] == "/tmp/audio.wav"
    stored = get_task(task_id)
    assert stored["status"] == "success"
    assert stored["fail_count"] == 0
