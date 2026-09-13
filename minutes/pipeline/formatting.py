import re
from collections.abc import Callable
from typing import Any

from minutes.ollama import DEFAULT_SYSTEM_PROMPT
from minutes.transcribe import jsonable_segments

Formatter = Callable[..., str]
Summarizer = Callable[..., str]


def build_system_prompt(metadata: object) -> str | None:
    if not isinstance(metadata, dict):
        return None

    prompt = DEFAULT_SYSTEM_PROMPT
    language = metadata.get("language")
    if (
        isinstance(language, str)
        and language
        and language.lower() not in {"auto", "auto-detect", "auto detect"}
    ):
        if "jap" in language.lower():
            prompt = "出力は日本語で行ってください。\n" + prompt
        else:
            prompt = "Please produce the output in English.\n" + prompt
    if metadata.get("include_actions") is False:
        prompt += "\nDo not extract action items. Skip STEP3."
    return prompt


def format_transcript(
    raw_text: str,
    metadata: object,
    formatter: Formatter,
) -> str:
    system_prompt = build_system_prompt(metadata)
    if system_prompt:
        return formatter(raw_text, system_prompt=system_prompt)
    return formatter(raw_text)


def _extract_action_items(minutes: str) -> list[dict[str, str]]:
    match = re.search(
        r"(?is)(?:^|\n)\s*action items\s*\n(.*?)(?:\n\s*\n|\Z)",
        minutes,
    )
    if match:
        return [
            {"text": item}
            for line in match.group(1).splitlines()
            if (item := line.strip().lstrip("-•* "))
        ]

    return [
        {"text": line.strip()}
        for line in minutes.splitlines()
        if re.search(r"\b(Action|TODO|Action Item)[:\-]", line, re.IGNORECASE)
    ]


def _summarize(minutes: str, summarizer: Summarizer | None) -> str:
    try:
        if summarizer is None:
            from minutes.summary import summarize_local

            summarizer = summarize_local
        return summarizer(minutes, max_sentences=3)
    except (ImportError, ValueError, TypeError, RuntimeError):
        return ""


def build_pipeline_result(
    *,
    transcript: str,
    segments: list[Any],
    minutes: str,
    output_file: str,
    summarizer: Summarizer | None = None,
) -> dict[str, Any]:
    try:
        action_items = _extract_action_items(minutes)
    except re.error:
        action_items = []
    return {
        "transcript": transcript,
        "segments": jsonable_segments(segments),
        "minutes": minutes,
        "summary": _summarize(minutes, summarizer),
        "action_items": action_items,
        "output_file": output_file,
    }
