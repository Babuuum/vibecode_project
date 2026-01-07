from __future__ import annotations

from uuid import uuid4

from starlette.datastructures import Headers, MutableHeaders

from autocontent.shared.logging import bind_log_context, clear_log_context


class RequestIdMiddleware:
    def __init__(self, app, header_name: str = "X-Request-ID") -> None:
        self.app = app
        self.header_name = header_name

    async def __call__(self, scope, receive, send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        headers = Headers(scope=scope)
        request_id = headers.get(self.header_name) or uuid4().hex
        bind_log_context(request_id=request_id)

        async def send_wrapper(message):
            if message["type"] == "http.response.start":
                response_headers = MutableHeaders(scope=message)
                response_headers[self.header_name] = request_id
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        finally:
            clear_log_context()
