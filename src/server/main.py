"""Market data MCP server."""

import argparse
import logging

logger = logging.getLogger(__name__)


def main() -> None:
    parser = argparse.ArgumentParser(prog="kite-mcp-server")
    parser.add_argument(
        "--data-dir",
        default="data",
        help="Directory containing market data parquet files",
    )
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO)
    logger.info("starting market data MCP server (data_dir=%s)", args.data_dir)


if __name__ == "__main__":
    main()