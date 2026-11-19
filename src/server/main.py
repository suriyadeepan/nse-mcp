"""Market data MCP server."""

import argparse
import logging
import os
import re
from collections.abc import Awaitable, Callable
from typing import Any

from mcp.server import MCPServer
from mcp.server.transport_security import TransportSecuritySettings

from .auth import BearerAuthMiddleware
from .tools import register_tools

logger = logging.getLogger(__name__)
STREAMABLE_HTTP_PATH = "/mcp"
_REQUEST_ID_PATTERN = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")


class RequestCorrelationMiddleware:
    """Log validated non-secret request IDs for authenticated MCP requests."""

    def __init__(self, app: Callable[..., Awaitable[None]]) -> None:
        self.app = app

    async def __call__(
        self,
        scope: dict[str, Any],
        receive: Callable[..., Awaitable[dict[str, Any]]],
        send: Callable[..., Awaitable[None]],
    ) -> None:
        if scope.get("type") == "http" and scope.get("path") == STREAMABLE_HTTP_PATH:
            headers = dict(scope.get("headers", []))
            request_id = headers.get(b"x-kite-request-id", b"").decode(
                "ascii", "ignore"
            )
            if _REQUEST_ID_PATTERN.fullmatch(request_id):
                logger.info(
                    "MCP request correlation_id=%s method=%s path=%s",
                    request_id,
                    scope.get("method", ""),
                    STREAMABLE_HTTP_PATH,
                )
        await self.app(scope, receive, send)


mcp = MCPServer("kite-mcp")
register_tools(mcp)


def build_transport_security(
    function_url_host: str | None = None,
) -> TransportSecuritySettings:
    """Build DNS rebinding protection from the configured Function URL host."""
    configured_host = function_url_host or os.environ.get("MCP_FUNCTION_URL_HOST")
    allowed_hosts = ["127.0.0.1:*", "localhost:*", "[::1]:*"]
    allowed_origins = [
        "http://127.0.0.1:*",
        "http://localhost:*",
        "http://[::1]:*",
    ]
    if configured_host:
        allowed_hosts.insert(0, configured_host)
        allowed_origins.insert(0, f"https://{configured_host}")
    return TransportSecuritySettings(
        enable_dns_rebinding_protection=True,
        allowed_hosts=allowed_hosts,
        allowed_origins=allowed_origins,
    )


transport_security = build_transport_security()
app = BearerAuthMiddleware(
    RequestCorrelationMiddleware(
        mcp.streamable_http_app(
            streamable_http_path=STREAMABLE_HTTP_PATH,
            transport_security=transport_security,
        )
    )
)


def main() -> None:
    parser = argparse.ArgumentParser(prog="kite-mcp")
    parser.add_argument(
        "--data-dir",
        default="data",
        help="Directory containing market data parquet files",
    )
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO)
    logger.info("starting market data MCP server (data_dir=%s)", args.data_dir)
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
