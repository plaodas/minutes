import sys

from requests.exceptions import RequestException
from sqlalchemy.exc import SQLAlchemyError

from minutes.pipeline.task_runner import run_audio_pipeline


def run(upload_path: str, task_id: str):
    try:
        result = run_audio_pipeline(upload_path, task_id)
        print("SUCCESS", result["result"]["output_file"])
    except (
        OSError,
        RuntimeError,
        ValueError,
        TypeError,
        RequestException,
        SQLAlchemyError,
    ) as exc:
        print("FAILED", repr(exc))


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: python3 minutes/run_single_task_small.py <upload_path> <task_id>")
        sys.exit(2)
    run(sys.argv[1], sys.argv[2])
