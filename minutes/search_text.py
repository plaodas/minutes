def build_search_text(name: object, result: object) -> str:
    """Lowercase the fields history search should match."""
    parts: list[str] = []
    if isinstance(name, str) and name.strip():
        parts.append(name.strip())
    if isinstance(result, dict):
        for key in ("transcript", "summary", "minutes"):
            value = result.get(key)
            if isinstance(value, str) and value.strip():
                parts.append(value.strip())
    return "\n".join(parts).casefold()


def escape_like(value: str) -> str:
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
