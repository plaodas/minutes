import os
import requests
from typing import Optional
from minutes.summary import summarize_local


DEFAULT_SYSTEM_PROMPT = """
あなたは議事録を整形する専門家です。
以下の文字起こしを、文脈・固有名詞・誤変換を補正し、
読みやすい議事録として整形してください。
"""


def format_minutes_from_raw(
    raw_text: str,
    model: str | None = None,
    system_prompt: Optional[str] = None,
    host: Optional[str] = None,
) -> str:
    """Format raw transcript text via Ollama.

    The `host` may be provided or read from the `OLLAMA_HOST` environment
    variable. When running inside Docker and Ollama runs on the host machine,
    set `OLLAMA_HOST=http://host.docker.internal:11434` so the container can
    reach the host's Ollama instance.
    """
    sys_prompt = system_prompt or DEFAULT_SYSTEM_PROMPT
    host = host or os.environ.get("OLLAMA_HOST", "http://localhost:11434")

    # allow overriding default model and fallback models via env
    primary_model = model or os.environ.get("OLLAMA_MODEL", "gemma2:2b")
    fallback_models = [m.strip() for m in os.environ.get("OLLAMA_FALLBACK_MODELS", "gemma4-mini,gemma3,gemma4:e4b").split(",") if m.strip()]

    def _call_model(model_name: str):
        payload = {
            "model": model_name,
            "messages": [
                {"role": "system", "content": sys_prompt},
                {"role": "user", "content": f"【文字起こし】\n{raw_text}"},
            ],
            "stream": False,
        }

        base_timeout = int(os.environ.get("OLLAMA_TIMEOUT", "120"))
        last_exc = None
        for attempt in range(3):
            timeout = base_timeout * (2 ** attempt)
            try:
                resp = requests.post(f"{host}/api/chat", json=payload, timeout=timeout)
                resp.raise_for_status()
                return resp.json()
            except requests.exceptions.RequestException as exc:
                last_exc = exc
        raise last_exc

    # try primary model, then fallbacks if available
    models_to_try = [primary_model] + fallback_models
    last_error = None
    resp_json = None
    for m in models_to_try:
        try:
            resp_json = _call_model(m)
            break
        except Exception as exc:
            last_error = exc
            # if model load failed due to server OOM or load error, try next fallback
            continue

    if resp_json is None:
        # Instead of raising, return a small local summary so the service can
        # continue even when Ollama is unavailable or failing.
        err_msg = f"Ollama call failed: {last_error}"
        # produce a concise extractive summary via local summarizer
        try:
            summary = summarize_local(raw_text, max_sentences=int(os.environ.get("OLLAMA_FALLBACK_SENTENCES", "5")))
            return f"[FALLBACK] {err_msg}\n\n{summary}"
        except Exception:
            max_len = int(os.environ.get("OLLAMA_FALLBACK_MAX_CHARS", "4000"))
            snippet = raw_text if len(raw_text) <= max_len else raw_text[:max_len] + "..."
            return f"[FALLBACK] {err_msg}\n\n{snippet}"

    # extract content
    if "message" in resp_json and "content" in resp_json["message"]:
        return resp_json["message"]["content"]

    # fallback
    if "response" in resp_json:
        return resp_json["response"]

    # Unexpected structured response; attempt local summarization as fallback.
    err_msg = f"Unexpected response from Ollama: {resp_json}"
    try:
        summary = summarize_local(raw_text, max_sentences=int(os.environ.get("OLLAMA_FALLBACK_SENTENCES", "5")))
        return f"[FALLBACK] {err_msg}\n\n{summary}"
    except Exception:
        max_len = int(os.environ.get("OLLAMA_FALLBACK_MAX_CHARS", "4000"))
        snippet = raw_text if len(raw_text) <= max_len else raw_text[:max_len] + "..."
        return f"[FALLBACK] {err_msg}\n\n{snippet}"
