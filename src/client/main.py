"""Market data MCP client."""

import argparse
import asyncio
import logging

logger = logging.getLogger(__name__)


def main() -> None:
    parser = argparse.ArgumentParser(prog="kite-mcp-client")
    parser.add_argument(
        "--server",
        default="http://localhost:8000/mcp",
        help="Streamable HTTP endpoint of the market data MCP server",
    )
    parser.add_argument("--prompt", help="Query to send to the agent")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO)

    if not args.prompt:
        parser.error("--prompt is required")

    from client.discovery import connect_to_server

    try:
        async def connect() -> None:
            async with connect_to_server(args.server):
                logger.info("connected to MCP server over Streamable HTTP")

        asyncio.run(connect())
    except ConnectionError as exc:
        parser.exit(1, f"kite-mcp-client: error: {exc}\n")


if __name__ == "__main__":
    main()
