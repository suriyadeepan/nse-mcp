"""Market data MCP client."""

import argparse
import logging

logger = logging.getLogger(__name__)


def main() -> None:
    parser = argparse.ArgumentParser(prog="kite-mcp-client")
    parser.add_argument(
        "--server",
        default="http://localhost:8000",
        help="Base URL of the market data MCP server",
    )
    parser.add_argument("--prompt", help="Query to send to the agent")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO)

    if not args.prompt:
        parser.error("--prompt is required")

    from client.agent import run

    logger.info("querying %s", args.server)
    run(args.server, args.prompt)


if __name__ == "__main__":
    main()