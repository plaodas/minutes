import json

from fastapi.testclient import TestClient
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.requests import Request

from backend.app import app
from minutes.http_errors import error_message_from_detail, http_exception_handler


def test_http_exception_handler_returns_error_object():
    request = Request({"type": "http", "method": "GET", "path": "/", "headers": []})
    response = http_exception_handler(
        request, StarletteHTTPException(status_code=401, detail="Not authenticated")
    )

    assert response.status_code == 401
    assert json.loads(response.body) == {"error": "Not authenticated"}


def test_error_message_from_detail_prefers_nested_error():
    assert error_message_from_detail({"error": "missing name"}) == "missing name"
    assert error_message_from_detail("") == "request failed"


def test_admin_http_exception_is_normalized_to_error_object():
    response = TestClient(app).get("/api/admin/buckets")

    assert response.status_code == 403
    assert response.json() == {"error": "forbidden"}
