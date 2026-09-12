import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from minutes_cli import cli_wrappers


def test_run_minute_pipeline_uses_shared_pipeline(monkeypatch):
    monkeypatch.setattr(
        cli_wrappers,
        "run_audio_pipeline",
        lambda audio: {
            "status": "success",
            "result": {"output_file": f"outputs/{Path(audio).stem}.txt"},
        },
    )

    assert cli_wrappers.run_minute_pipeline("meeting.wav") == "outputs/meeting.txt"


def test_auto_command_is_a_backward_compatible_alias(monkeypatch):
    monkeypatch.setattr(
        cli_wrappers,
        "run_minute_pipeline",
        lambda audio: f"outputs/{Path(audio).stem}.txt",
    )

    assert cli_wrappers.auto_minutes_ollama("meeting.wav") == "outputs/meeting.txt"
