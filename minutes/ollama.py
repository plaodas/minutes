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
    host: str = "http://localhost:11434",
) -> str:
    sys_prompt = system_prompt or DEFAULT_SYSTEM_PROMPT

    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": sys_prompt},
            {"role": "user", "content": f"【文字起こし】\n{raw_text}"},
        ],
        "stream": False,
    }

    resp = requests.post(f"{host}/api/chat", json=payload)
    resp.raise_for_status()
    resp_json = resp.json()

    # extract content
    if "message" in resp_json and "content" in resp_json["message"]:
        return resp_json["message"]["content"]

    # fallback
    if "response" in resp_json:
        return resp_json["response"]

    raise ValueError(f"Unexpected response from Ollama: {resp_json}")
