"""Market data MCP server."""

import argparse
import logging
import os

from mcp.server import MCPServer
from mcp.server.transport_security import TransportSecuritySettings

from .auth import BearerAuthMiddleware
from .tools import register_tools

logger = logging.getLogger(__name__)

mcp = MCPServer("kite-mcp")
register_tools(mcp)
STREAMABLE_HTTP_PATH = "/mcp"


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
    mcp.streamable_http_app(
        streamable_http_path=STREAMABLE_HTTP_PATH,
        transport_security=transport_security,
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
