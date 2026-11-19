"""Bearer authentication for HTTP requests to the MCP application."""

import hmac
import json
import os
from collections.abc import Awaitable, Callable
from typing import Any

ASGIApp = Callable[[dict[str, Any], Callable[..., Awaitable[None]], Callable[..., Awaitable[None]]], Awaitable[None]]


class BearerAuthMiddleware:
    """Require the configured bearer token without logging or echoing it."""

    def __init__(self, app: ASGIApp, token_env: str = "MCP_BEARER_TOKEN") -> None:
        self.app = app
        self.token_env = token_env

    async def __call__(self, scope: dict[str, Any], receive: Callable[..., Awaitable[dict[str, Any]]], send: Callable[..., Awaitable[None]]) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        configured_token = os.environ.get(self.token_env, "")
        supplied_token = self._bearer_token(scope)
        if not configured_token:
            await self._respond(send, 503, "Authentication is not configured")
            return
        if supplied_token is None or not hmac.compare_digest(supplied_token, configured_token):
            await self._respond(send, 401, "Unauthorized")
            return

        await self.app(scope, receive, send)

    @staticmethod
    def _bearer_token(scope: dict[str, Any]) -> str | None:
        headers = dict(scope.get("headers", []))
        authorization = headers.get(b"authorization", b"").decode("latin-1")
        scheme, separator, token = authorization.partition(" ")
        if not separator or scheme.lower() != "bearer" or not token or " " in token:
            return None
        return token

    @staticmethod
    async def _respond(send: Callable[..., Awaitable[None]], status: int, message: str) -> None:
        body = json.dumps({"detail": message}).encode("utf-8")
        headers = [(b"content-type", b"application/json"), (b"content-length", str(len(body)).encode())]
        if status == 401:
            headers.append((b"www-authenticate", b"Bearer"))
        await send({"type": "http.response.start", "status": status, "headers": headers})
        await send({"type": "http.response.body", "body": body})
