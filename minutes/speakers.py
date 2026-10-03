from copy import deepcopy
from typing import Any


def render_transcript(segments: list[object]) -> str:
    lines: list[str] = []
    for segment in segments:
        if not isinstance(segment, dict):
            continue
        text = str(segment.get("text") or "").strip()
        speaker = str(segment.get("speaker") or "").strip()
        if speaker:
            lines.append(f"[{speaker}] {text}".rstrip())
        elif text:
            lines.append(text)
    return "\n".join(lines)


def apply_speaker_updates(
    result: dict[str, Any],
    updates: list[tuple[int, str]],
) -> dict[str, Any]:
    segments = result.get("segments")
    if not isinstance(segments, list) or not segments:
        raise ValueError("no segments")
    if not updates:
        raise ValueError("missing updates")

    copied = deepcopy(result)
    next_segments = copied["segments"]

    for index, speaker in updates:
        if (
            not isinstance(index, int)
            or index < 0
            or index >= len(next_segments)
            or not isinstance(next_segments[index], dict)
        ):
            raise ValueError("invalid segment index")
        segment = next_segments[index]
        cleaned = speaker.strip()
        if not cleaned:
            raise ValueError("missing speaker")
        if len(cleaned) > 80:
            raise ValueError("speaker name too long")
        next_segments[index] = {**segment, "speaker": cleaned}

    copied["transcript"] = render_transcript(next_segments)
    return copied
