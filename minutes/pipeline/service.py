import datetime
import logging
import os
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from minutes.schemas import TaskStage

from .artifacts import write_text_atomic
from .audio import prepare_audio
from .formatting import build_pipeline_result, format_transcript
from .storage import cache_minutes_artifact
from .transcription import (
    HttpPost,
    ProgressUpdater,
    StatusUpdater,
    Transcriber,
    transcribe_locally,
    transcribe_remotely,
)

logger = logging.getLogger("minutes.pipeline.service")
Preprocessor = Callable[[str], Any]
Formatter = Callable[..., str]


@dataclass
class PipelineService:
    preprocess: Preprocessor
    transcriber: Transcriber
    formatter: Formatter
    post: HttpPost
    artifact_cache: Callable[[str | None, str, str], dict[str, Any] | None] = (
        cache_minutes_artifact
    )
    artifact_writer: Callable[[str, str], None] = write_text_atomic

    def run(
        self,
        input_path: str,
        *,
        task_id: str | None = None,
        metadata: object = None,
        update_status: StatusUpdater,
        update_progress: ProgressUpdater,
        inference_url: str | None = None,
        outputs_dir: str | None = None,
        delete_intermediate: bool = True,
    ) -> dict[str, Any]:
        update_status(TaskStage.PREPROCESS, None)
        try:
            prepared = prepare_audio(input_path, self.preprocess)
        except (RuntimeError, OSError, ValueError, TypeError) as exc:
            raise RuntimeError(f"preprocess failed: {exc}") from exc

        update_status(TaskStage.TRANSCRIBING, None)
        if inference_url:
            transcription = transcribe_remotely(
                prepared.clean,
                inference_url=inference_url,
                duration_seconds=prepared.duration_seconds,
                post=self.post,
                update_status=update_status,
                update_progress=update_progress,
            )
        else:
            transcription = transcribe_locally(
                prepared.clean,
                duration_seconds=prepared.duration_seconds,
                transcriber=self.transcriber,
                update_status=update_status,
                update_progress=update_progress,
            )

        update_status(TaskStage.FORMATTING, None)
        final_minutes = format_transcript(
            transcription.raw_text,
            metadata,
            self.formatter,
        )
        timestamp = datetime.datetime.now(tz=datetime.timezone.utc).strftime(
            "%Y%m%d%H%M%S"
        )
        output_path = os.path.join(
            outputs_dir or os.environ.get("OUTPUTS_DIR", "outputs"),
            f"minutes_{timestamp}.txt",
        )
        self.artifact_writer(final_minutes, output_path)

        result = build_pipeline_result(
            transcript=transcription.raw_text,
            segments=transcription.segments,
            minutes=final_minutes,
            output_file=output_path,
        )
        minio_artifact = self.artifact_cache(task_id, timestamp, output_path)
        if minio_artifact:
            result["minio"] = minio_artifact

        if delete_intermediate:
            self._cleanup_intermediates(
                input_path,
                (prepared.mono, prepared.normalized, prepared.clean),
                task_id,
            )
        return result

    @staticmethod
    def _cleanup_intermediates(
        input_path: str,
        paths: tuple[str, str, str],
        task_id: str | None,
    ) -> None:
        base_dir = os.path.dirname(os.path.abspath(input_path)) or os.getcwd()
        for path in paths:
            try:
                if not path:
                    continue
                absolute_path = os.path.abspath(path)
                if os.path.commonpath((base_dir, absolute_path)) != base_dir:
                    logger.warning(
                        "Skipping removal of intermediate outside base dir: %s",
                        absolute_path,
                    )
                    continue
                if os.path.exists(absolute_path):
                    os.remove(absolute_path)
                    logger.info(
                        "Removed intermediate file %s for task %s",
                        absolute_path,
                        task_id,
                    )
            except (OSError, ValueError):
                logger.exception(
                    "Failed to remove intermediate %s for task %s",
                    path,
                    task_id,
                )
