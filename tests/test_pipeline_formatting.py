import json
from types import SimpleNamespace

from minutes.pipeline.formatting import build_pipeline_result, format_transcript
from minutes.transcribe import jsonable_segment, jsonable_segments


def test_format_transcript_passes_metadata_prompt_to_formatter():
    captured = {}

    def formatter(raw_text, system_prompt=None):
        captured["raw_text"] = raw_text
        captured["system_prompt"] = system_prompt
        return "formatted"

    result = format_transcript(
        "raw transcript",
        {"language": "Japanese", "include_actions": False},
        formatter,
    )

    assert result == "formatted"
    assert captured["raw_text"] == "raw transcript"
    assert "日本語" in captured["system_prompt"]
    assert "Do not extract action items" in captured["system_prompt"]


def test_build_pipeline_result_adds_summary_and_action_items():
    result = build_pipeline_result(
        transcript="raw transcript",
        segments=[{"start": 0, "end": 1}],
        minutes="Summary\n\nAction Items\n- Send report\n- Book room",
        output_file="outputs/minutes.txt",
        summarizer=lambda text, max_sentences: f"summary:{max_sentences}",
    )

    assert result == {
        "transcript": "raw transcript",
        "segments": [{"start": 0, "end": 1}],
        "minutes": "Summary\n\nAction Items\n- Send report\n- Book room",
        "summary": "summary:3",
        "action_items": [{"text": "Send report"}, {"text": "Book room"}],
        "output_file": "outputs/minutes.txt",
    }


def test_build_pipeline_result_serializes_whisper_segments():
    result = build_pipeline_result(
        transcript="hi",
        segments=[SimpleNamespace(start=0.0, end=1.5, text="hi")],
        minutes="minutes",
        output_file="outputs/minutes.txt",
        summarizer=lambda text, max_sentences: "sum",
    )

    assert result["segments"] == [{"start": 0.0, "end": 1.5, "text": "hi"}]
    json.dumps(result)


def test_jsonable_segments_leave_dicts_unchanged():
    original = [{"end": 10.0, "text": "ok"}]
    assert jsonable_segments(original) == original
    assert jsonable_segment(SimpleNamespace(end=2.0, text="x")) == {
        "end": 2.0,
        "text": "x",
    }
