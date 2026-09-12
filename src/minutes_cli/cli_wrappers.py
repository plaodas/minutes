import argparse
from collections.abc import Sequence

from minutes.pipeline.task_runner import run_audio_pipeline
from minutes.task_result import result_output_file


def run_minute_pipeline(audio: str) -> str:
    """Run the same pipeline used by Celery and return its output path."""
    response = run_audio_pipeline(audio)
    output_file = result_output_file(response.get("result"))
    if not output_file:
        raise RuntimeError("pipeline completed without an output file")
    return output_file


def auto_minutes_ollama(audio: str, prompt: str | None = None) -> str:
    """Backward-compatible alias for the canonical pipeline command."""
    del prompt
    return run_minute_pipeline(audio)


def _main_from_argv(argv: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        prog="minutes-cli",
        description="Run the Minutes audio pipeline locally.",
    )
    parser.add_argument("command", choices=("run", "auto"))
    parser.add_argument("audio_file")
    args = parser.parse_args(argv)

    runner = run_minute_pipeline if args.command == "run" else auto_minutes_ollama
    output_file = runner(args.audio_file)
    print(f"Wrote: {output_file}")


if __name__ == "__main__":
    _main_from_argv()
