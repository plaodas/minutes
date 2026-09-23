from types import SimpleNamespace

from minutes.pipeline import service as pipeline_service
from minutes.pipeline.service import PipelineService
from minutes.pipeline.transcription import TranscriptionResult
from minutes.schemas import TaskStage


def test_pipeline_service_orchestrates_remote_transcription(monkeypatch, tmp_path):
    prepared = SimpleNamespace(
        mono="mono.wav",
        normalized="normalized.wav",
        clean="clean.wav",
        duration_seconds=10.0,
    )
    monkeypatch.setattr(
        pipeline_service,
        "prepare_audio",
        lambda input_path, preprocess: prepared,
    )
    monkeypatch.setattr(
        pipeline_service,
        "transcribe_remotely",
        lambda *args, **kwargs: TranscriptionResult(
            raw_text="remote transcript",
            segments=[{"end": 10.0}],
        ),
    )
    statuses = []
    written = []
    service = PipelineService(
        preprocess=lambda path: path,
        transcriber=lambda *args, **kwargs: ("unused", []),
        formatter=lambda raw: f"minutes: {raw}",
        post=lambda *args, **kwargs: None,
        artifact_cache=lambda task_id, timestamp, output_path: None,
        artifact_writer=lambda content, path: written.append((content, path)),
    )

    result = service.run(
        "input.wav",
        task_id="task-id",
        update_status=lambda stage, detail: statuses.append((stage, detail)),
        update_progress=lambda progress: None,
        inference_url="http://inference/transcribe",
        outputs_dir=str(tmp_path),
        delete_intermediate=False,
    )

    assert statuses == [
        (TaskStage.PREPROCESS, None),
        (TaskStage.TRANSCRIBING, None),
        (TaskStage.FORMATTING, None),
    ]
    assert result["transcript"] == "remote transcript"
    assert result["segments"] == [{"end": 10.0}]
    assert result["minutes"] == "minutes: remote transcript"
    assert written == [("minutes: remote transcript", result["output_file"])]


def test_pipeline_service_passes_language_to_local_transcription(monkeypatch, tmp_path):
    prepared = SimpleNamespace(
        mono="mono.wav",
        normalized="normalized.wav",
        clean="clean.wav",
        duration_seconds=10.0,
    )
    monkeypatch.setattr(
        pipeline_service,
        "prepare_audio",
        lambda input_path, preprocess: prepared,
    )
    seen = {}

    def transcribe_locally(*_args, **kwargs):
        seen.update(kwargs)
        return TranscriptionResult(raw_text="local transcript", segments=[])

    monkeypatch.setattr(pipeline_service, "transcribe_locally", transcribe_locally)
    service = PipelineService(
        preprocess=lambda path: path,
        transcriber=lambda *args, **kwargs: ("unused", []),
        formatter=lambda raw, system_prompt=None: raw,
        post=lambda *args, **kwargs: None,
        artifact_cache=lambda task_id, timestamp, output_path: None,
        artifact_writer=lambda content, path: None,
    )

    service.run(
        "input.wav",
        metadata={"language": "English"},
        update_status=lambda stage, detail: None,
        update_progress=lambda progress: None,
        outputs_dir=str(tmp_path),
        delete_intermediate=False,
    )

    assert seen["language"] == "English"
