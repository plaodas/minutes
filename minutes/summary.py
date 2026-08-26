import re

def summarize_local(raw_text: str, max_sentences: int = 5) -> str:
    """Very small extractive summarizer: split into sentences and pick the
    longest sentences as a crude summary. Returns joined sentences.
    """
    if not raw_text:
        return ""

    # naive sentence splitter
    parts = re.split(r'(?<=[。．！？!?\.!\?])\s*', raw_text)
    parts = [p.strip() for p in parts if p.strip()]
    if not parts:
        # fallback to line-based
        parts = [l.strip() for l in raw_text.splitlines() if l.strip()]

    # if fewer sentences than max, return joined
    if len(parts) <= max_sentences:
        return "\n\n".join(parts)

    # score by length (simple heuristic)
    scored = sorted(parts, key=lambda s: len(s), reverse=True)
    top = scored[:max_sentences]
    # preserve original order
    top_sorted = [s for s in parts if s in top]
    return "\n\n".join(top_sorted)
