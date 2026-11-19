"""Market data MCP server."""

import argparse
import logging

from mcp.server import MCPServer
from mcp.server.transport_security import TransportSecuritySettings

from .auth import BearerAuthMiddleware
from .tools import register_tools

logger = logging.getLogger(__name__)

mcp = MCPServer("kite-mcp")
register_tools(mcp)
STREAMABLE_HTTP_PATH = "/mcp"
LAMBDA_FUNCTION_URL_HOST = (
    "onznjliuy5yjpzwozpjrjepwa40nzdhe.lambda-url.ap-south-1.on.aws"
)
transport_security = TransportSecuritySettings(
    enable_dns_rebinding_protection=True,
    allowed_hosts=[
        LAMBDA_FUNCTION_URL_HOST,
        "127.0.0.1:*",
        "localhost:*",
        "[::1]:*",
    ],
    allowed_origins=[
        f"https://{LAMBDA_FUNCTION_URL_HOST}",
        "http://127.0.0.1:*",
        "http://localhost:*",
        "http://[::1]:*",
    ],
)
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
