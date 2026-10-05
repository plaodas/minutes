import uuid

from minutes.log_context import request_id_var


class RequestIdMiddleware:
    """Attach one request id to logs and the response.

    A pure ASGI middleware so the SSE stream is not buffered.
    """

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope.get("type") != "http":
            await self.app(scope, receive, send)
            return

        request_id = _incoming_request_id(scope) or str(uuid.uuid4())
        token = request_id_var.set(request_id)

        async def send_with_id(message):
            if message["type"] == "http.response.start":
                headers = list(message.get("headers") or [])
                headers.append((b"x-request-id", request_id.encode()))
                message = {**message, "headers": headers}
            await send(message)

        try:
            await self.app(scope, receive, send_with_id)
        finally:
            request_id_var.reset(token)


def _incoming_request_id(scope) -> str:
    for name, value in scope.get("headers") or []:
        if name.lower() == b"x-request-id":
            return value.decode(errors="replace").strip()
    return ""
