import uuid
from typing import Any


def parse_task_key(maybe_id: Any) -> Any:
    if isinstance(maybe_id, uuid.UUID):
        return maybe_id
    if not isinstance(maybe_id, str):
        return maybe_id
    value = maybe_id.strip()
    if (value.startswith('"') and value.endswith('"')) or (
        value.startswith("'") and value.endswith("'")
    ):
        value = value[1:-1].strip()
    if value.startswith("{") and value.endswith("}"):
        value = value[1:-1].strip()
    cleaned = "".join(char for char in value if char.isalnum() or char == "-")
    try:
        return uuid.UUID(cleaned)
    except (ValueError, AttributeError):
        return maybe_id
