import json
import logging

from fastapi.testclient import TestClient

from minutes.api import app
from minutes.log_context import JsonLogFormatter, request_id_var, task_id_var


def test_json_formatter_includes_request_and_task_ids():
    request_token = request_id_var.set("req-1")
    task_token = task_id_var.set("task-1")
    try:
        record = logging.LogRecord(
            name="minutes.test",
            level=logging.INFO,
            pathname=__file__,
            lineno=1,
            msg="hello %s",
            args=("there",),
            exc_info=None,
        )
        payload = json.loads(JsonLogFormatter().format(record))
    finally:
        request_id_var.reset(request_token)
        task_id_var.reset(task_token)

    assert payload["message"] == "hello there"
    assert payload["level"] == "INFO"
    assert payload["logger"] == "minutes.test"
    assert payload["request_id"] == "req-1"
    assert payload["task_id"] == "task-1"
    assert "time" in payload


def test_request_id_middleware_echoes_or_creates_a_header():
    with TestClient(app) as client:
        supplied = client.get("/api/health", headers={"X-Request-ID": "trace-9"})
        assert supplied.headers["x-request-id"] == "trace-9"
        generated = client.get("/api/health")
        assert generated.headers["x-request-id"]
        assert generated.headers["x-request-id"] != "trace-9"
