import json
from types import SimpleNamespace

from minutes.ollama import DEFAULT_SYSTEM_PROMPT
from minutes.pipeline.formatting import (
    build_pipeline_result,
    extract_action_items,
    format_transcript,
)
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


def test_extract_action_items_parses_japanese_step3_triples():
    minutes = """
【STEP3：アクション抽出】

- **誰が**：かたやまひろこ
- **何を**：大島の着物を10万円で売ること
- **いつまでに**：期限未設定
- **誰が**：かたやまひろこ
- **何を**：医師の助けを頼む
- **いつまでに**：期限未設定
"""
    items = extract_action_items(minutes)
    assert items == [
        {
            "text": "かたやまひろこ: 大島の着物を10万円で売ること（期限未設定）",
            "who": "かたやまひろこ",
            "what": "大島の着物を10万円で売ること",
            "due": "期限未設定",
        },
        {
            "text": "かたやまひろこ: 医師の助けを頼む（期限未設定）",
            "who": "かたやまひろこ",
            "what": "医師の助けを頼む",
            "due": "期限未設定",
        },
    ]


def test_extract_action_items_parses_inline_prompt_format():
    minutes = """
### アクションアイテム
- 誰が: 山田 / 何を: 見積を送る / いつまでに: 金曜
- 誰が: 佐藤 / 何を: 会場を抑える / いつまでに: 期限未設定
"""
    items = extract_action_items(minutes)
    assert [item["what"] for item in items] == ["見積を送る", "会場を抑える"]
    assert items[0]["who"] == "山田"
    assert items[0]["due"] == "金曜"


def test_default_prompt_asks_for_machine_readable_actions():
    assert "### アクションアイテム" in DEFAULT_SYSTEM_PROMPT
    assert "誰が:" in DEFAULT_SYSTEM_PROMPT
    assert "何を:" in DEFAULT_SYSTEM_PROMPT
    assert "いつまでに:" in DEFAULT_SYSTEM_PROMPT
