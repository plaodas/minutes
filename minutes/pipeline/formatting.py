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


_ACTION_HEADING = re.compile(
    r"(?i)^(?:#{1,6}\s*)?(?:【\s*)?(?:STEP\s*3[:：]?\s*)?"
    r"(?:アクション(?:抽出|アイテム)|Action\s+Items)\s*(?:】)?\s*$"
)
_SECTION_END = re.compile(
    r"(?i)^(?:#{1,6}\s*|【\s*)(?:STEP\s*[12]|整形済み|要約|Transcript|Summary|出力フォーマット)\b"
)
_FIELD_KEY = {
    "誰が": "who",
    "担当": "who",
    "担当者": "who",
    "何を": "what",
    "いつまでに": "due",
    "期限": "due",
}
_FIELD_LINE = re.compile(
    r"^(?:[-*•]+\s*)?(?:\*\*)?(?P<key>誰が|何を|いつまでに|担当者?|期限)"
    r"(?:\*\*)?\s*[:：]\s*(?P<value>.+?)\s*$"
)
_INLINE_ITEM = re.compile(
    r"誰が\s*[:：]\s*(?P<who>.+?)\s*/\s*何を\s*[:：]\s*(?P<what>.+?)"
    r"\s*/\s*いつまでに\s*[:：]\s*(?P<due>.+?)\s*$"
)
_TODO_LINE = re.compile(r"\b(Action|TODO|Action Item)[:\-]", re.IGNORECASE)


def _strip_markup(value: str) -> str:
    return value.replace("**", "").strip(" \t-•*")


def _item_from_parts(who: str, what: str, due: str) -> dict[str, str] | None:
    who = _strip_markup(who)
    what = _strip_markup(what)
    due = _strip_markup(due) or "期限未設定"
    if not who and not what:
        return None
    if who and what:
        text = f"{who}: {what}（{due}）"
    elif what:
        text = f"{what}（{due}）"
    else:
        text = f"{who}（{due}）"
    item = {"text": text, "due": due}
    if who:
        item["who"] = who
    if what:
        item["what"] = what
    return item


def _flush_fields(current: dict[str, str]) -> dict[str, str] | None:
    return _item_from_parts(
        current.get("who", ""),
        current.get("what", ""),
        current.get("due", ""),
    )


def _parse_who_what_due(text: str) -> list[dict[str, str]]:
    items: list[dict[str, str]] = []
    current: dict[str, str] = {}
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        inline = _INLINE_ITEM.search(line)
        if inline:
            flushed = _flush_fields(current)
            if flushed:
                items.append(flushed)
            current = {}
            item = _item_from_parts(
                inline.group("who"),
                inline.group("what"),
                inline.group("due"),
            )
            if item:
                items.append(item)
            continue
        field = _FIELD_LINE.match(line)
        if not field:
            continue
        slot = _FIELD_KEY[field.group("key")]
        if slot in current and (current.get("what") or current.get("who")):
            flushed = _flush_fields(current)
            if flushed:
                items.append(flushed)
            current = {}
        current[slot] = field.group("value")
    flushed = _flush_fields(current)
    if flushed:
        items.append(flushed)
    return items


def _action_section(minutes: str) -> str | None:
    lines = minutes.splitlines()
    start = None
    for index, line in enumerate(lines):
        if _ACTION_HEADING.match(line.strip()):
            start = index + 1
            break
    if start is None:
        return None
    end = len(lines)
    for index in range(start, len(lines)):
        stripped = lines[index].strip()
        if _SECTION_END.match(stripped) and not _ACTION_HEADING.match(stripped):
            end = index
            break
    return "\n".join(lines[start:end])


def _bullet_items(section: str) -> list[dict[str, str]]:
    items = []
    for line in section.splitlines():
        item = line.strip().lstrip("-•* ")
        if item and not re.match(r"^[A-Z][a-z]+:$", item):
            items.append({"text": item})
    return items


def extract_action_items(minutes: str) -> list[dict[str, str]]:
    """Parse action items from formatted minutes (Japanese STEP3 or English)."""
    if not minutes or not minutes.strip():
        return []
    section = _action_section(minutes)
    structured = _parse_who_what_due(section if section is not None else minutes)
    if structured:
        return structured
    if section:
        return _bullet_items(section)
    return [
        {"text": line.strip()}
        for line in minutes.splitlines()
        if _TODO_LINE.search(line)
    ]


def _extract_action_items(minutes: str) -> list[dict[str, str]]:
    return extract_action_items(minutes)


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
