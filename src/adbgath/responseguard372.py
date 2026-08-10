from __future__ import annotations

from typing import Any, Awaitable, Callable

ASGIApp = Callable[[dict[str, Any], Callable[[], Awaitable[dict[str, Any]]], Callable[[dict[str, Any]], Awaitable[None]]], Awaitable[None]]

_GUARDED_PATHS = frozenset({"/", "/auth/login", "/auth/setup", "/wireless", "/lab"})


def _header_value(headers: list[tuple[bytes, bytes]], name: bytes) -> bytes | None:
    wanted = name.lower()
    for key, value in headers:
        if key.lower() == wanted:
            return value
    return None


def _normalized_headers(headers: list[tuple[bytes, bytes]], body_length: int) -> list[tuple[bytes, bytes]]:
    cleaned = [(key, value) for key, value in headers if key.lower() != b"content-length"]
    cleaned.append((b"content-length", str(body_length).encode("ascii")))
    return cleaned


class HtmlContentLengthGuard:
    """Buffer small first-party HTML pages and emit an exact Content-Length.

    ADBGath has several compatibility layers that progressively enrich the same
    dashboard HTML response.  This middleware is deliberately limited to the
    small first-party HTML/authentication routes so downloads, API responses,
    WebSockets and long-running streams remain fully streaming.
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: dict[str, Any], receive, send) -> None:
        if scope.get("type") != "http" or scope.get("path") not in _GUARDED_PATHS:
            await self.app(scope, receive, send)
            return

        start: dict[str, Any] | None = None
        chunks: list[bytes] = []
        completed = False

        async def guarded_send(message: dict[str, Any]) -> None:
            nonlocal start, completed
            message_type = message.get("type")
            if message_type == "http.response.start":
                start = dict(message)
                start["headers"] = list(message.get("headers", []))
                return
            if message_type != "http.response.body":
                await send(message)
                return

            chunks.append(bytes(message.get("body", b"")))
            if message.get("more_body", False):
                return

            if start is None:
                raise RuntimeError("HTTP response body was emitted before response start.")

            body = b"".join(chunks)
            headers = list(start.get("headers", []))
            content_type = (_header_value(headers, b"content-type") or b"").lower()

            # The known failure affects generated HTML, but normalizing an empty
            # redirect body on these small routes is safe and keeps the boundary
            # deterministic as well.
            if b"text/html" in content_type or not body:
                start["headers"] = _normalized_headers(headers, len(body))

            await send(start)
            await send({"type": "http.response.body", "body": body, "more_body": False})
            completed = True

        await self.app(scope, receive, guarded_send)

        # ASGI responses should always terminate with a body event. Fail closed
        # rather than silently dropping a captured response if a custom endpoint
        # violates that contract.
        if start is not None and not completed:
            body = b"".join(chunks)
            headers = list(start.get("headers", []))
            start["headers"] = _normalized_headers(headers, len(body))
            await send(start)
            await send({"type": "http.response.body", "body": body, "more_body": False})


def patch_webapp(module: Any) -> None:
    if getattr(module, "_adbgath_372_html_content_length_guard_patched", False):
        return

    original_create_app = module.create_app

    def create_app(*, workspace=None, service=None, remote_token=None, secure_cookie=False):
        app = original_create_app(
            workspace=workspace,
            service=service,
            remote_token=remote_token,
            secure_cookie=secure_cookie,
        )
        app.add_middleware(HtmlContentLengthGuard)
        return app

    module.create_app = create_app
    module._adbgath_372_html_content_length_guard_patched = True
