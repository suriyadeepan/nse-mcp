"""Summarize candle volumes and IST hourly or daily bucket totals."""

import argparse

from common import add_range_arguments, print_result
from src.server.analytics import get_volume_stats


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--symbol", required=True)
    add_range_arguments(parser)
    parser.add_argument("--bucket", choices=("hourly", "daily"), default="daily")
    args = parser.parse_args()
    print_result(
        lambda: get_volume_stats(
            args.symbol, args.start, args.end, args.bucket
        )
    )


if __name__ == "__main__":
    main()
