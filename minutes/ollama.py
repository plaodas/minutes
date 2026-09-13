import logging
import os

import requests

from minutes.summary import summarize_local

logger = logging.getLogger("minutes.ollama")

DEFAULT_SYSTEM_PROMPT = """
あなたは議事録整形・要約・アクション抽出の専門家です。
以下の文字起こしを、次の3ステップで処理してください。

【STEP1：整形】
- 誤変換を修正
- 文脈から意味を補完
- 固有名詞を正しい表記に統一
- フィラー削除
- 話者を推定してラベル付け
- 時系列が乱れている場合は自然な順に並べ替える

【STEP2：要約】
- 会議の目的
- 主な論点
- 結論
- 重要な決定事項
- 3〜5行の概要

【STEP3：アクション抽出】
- 必要なタスクを抽出して誰が、いつまでに、何をするかを記載する
- 担当者を明記（不明なら推測してよい）
- 期限を推測または「期限未設定」と記載
- 各タスクは次の1行形式で、見出し(### アクションアイテム)の直後に列挙する

【出力フォーマット】
- 整形済み議事録
- 要約
- 末尾に必ず「### アクションアイテム」を置き、上記1行形式の箇条書きだけを書く

では以下の文字起こしを処理してください：
"""


def format_minutes_from_raw(
    raw_text: str,
    model: str | None = None,
    system_prompt: str | None = None,
    host: str | None = None,
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
    primary_model = model or os.environ.get("OLLAMA_MODEL", "qwen2.5:3b")
    fallback_models = [
        m.strip()
        for m in os.environ.get("OLLAMA_FALLBACK_MODELS", "").split(",")
        if m.strip()
    ]
    # Log chosen host/model for easier debugging in containerized environments
    logger.info(
        "OLLAMA host=%s chosen model=%s fallback_models=%s",
        host,
        primary_model,
        fallback_models,
    )

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
            timeout = base_timeout * (2**attempt)
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
        except requests.exceptions.RequestException as exc:
            last_error = exc
            # if model load failed due to server OOM or load error, try next fallback
            continue

    if resp_json is None:
        # Instead of raising, return a small local summary so the service can
        # continue even when Ollama is unavailable or failing.
        err_msg = f"Ollama call failed: {last_error}"
        # produce a concise extractive summary via local summarizer
        try:
            summary = summarize_local(
                raw_text,
                max_sentences=int(os.environ.get("OLLAMA_FALLBACK_SENTENCES", "5")),
            )
            return f"[FALLBACK] {err_msg}\n\n{summary}"
        except (ValueError, TypeError, RuntimeError):
            max_len = int(os.environ.get("OLLAMA_FALLBACK_MAX_CHARS", "4000"))
            snippet = (
                raw_text if len(raw_text) <= max_len else raw_text[:max_len] + "..."
            )
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
        summary = summarize_local(
            raw_text,
            max_sentences=int(os.environ.get("OLLAMA_FALLBACK_SENTENCES", "5")),
        )
        return f"[FALLBACK] {err_msg}\n\n{summary}"
    except (ValueError, TypeError, RuntimeError):
        max_len = int(os.environ.get("OLLAMA_FALLBACK_MAX_CHARS", "4000"))
        snippet = raw_text if len(raw_text) <= max_len else raw_text[:max_len] + "..."
        return f"[FALLBACK] {err_msg}\n\n{snippet}"
