from minutes.ollama import format_minutes_from_raw


class _Response:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self._payload


def _capture_chat(monkeypatch, content):
    captured = {}

    def post(url, json, timeout):
        captured["url"] = url
        captured["json"] = json
        captured["timeout"] = timeout
        return _Response({"message": {"content": content, "thinking": "reasoning"}})

    monkeypatch.setattr("minutes.ollama.requests.post", post)
    monkeypatch.setenv("OLLAMA_FALLBACK_MODELS", "")
    monkeypatch.setenv("OLLAMA_HOST", "http://ollama:11434")
    return captured


def test_qwen3_request_disables_thinking(monkeypatch):
    captured = _capture_chat(monkeypatch, "整形済み議事録")

    result = format_minutes_from_raw("会議の文字起こし", model="qwen3.5:4b")

    assert result == "整形済み議事録"
    assert captured["json"]["think"] is False
    assert captured["json"]["model"] == "qwen3.5:4b"


def test_qwen25_request_leaves_thinking_unset(monkeypatch):
    captured = _capture_chat(monkeypatch, "整形済み議事録")

    result = format_minutes_from_raw("会議の文字起こし", model="qwen2.5:3b")

    assert result == "整形済み議事録"
    assert "think" not in captured["json"]
    assert captured["json"]["model"] == "qwen2.5:3b"
