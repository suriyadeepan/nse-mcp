"""Market data MCP server."""

import argparse
import logging

from mcp.server.fastmcp import FastMCP

logger = logging.getLogger(__name__)

mcp = FastMCP("kite-mcp")
app = mcp.streamable_http_app()


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
