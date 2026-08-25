import os
import requests
from typing import Optional


DEFAULT_SYSTEM_PROMPT = """
あなたは議事録を整形する専門家です。
以下の文字起こしを、文脈・固有名詞・誤変換を補正し、
読みやすい議事録として整形してください。

（省略 — 詳細なフォーマットは呼び出し側で付与できます）
"""


def format_minutes_from_raw(
    raw_text: str,
    model: str = "gemma4:e4b",
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

    payload = {
        "model": model,
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
            break
        except requests.exceptions.RequestException as exc:
            last_exc = exc
    else:
        raise RuntimeError(
            f"Failed to call Ollama at {host}/api/chat: {last_exc}. "
            "Ensure Ollama is running and the host is reachable from this process. "
            "If running Ollama on the Docker host, try setting OLLAMA_HOST=http://host.docker.internal:11434"
        ) from last_exc

    resp_json = resp.json()

    # extract content
    if "message" in resp_json and "content" in resp_json["message"]:
        return resp_json["message"]["content"]

    # fallback
    if "response" in resp_json:
        return resp_json["response"]

    raise ValueError(f"Unexpected response from Ollama: {resp_json}")
