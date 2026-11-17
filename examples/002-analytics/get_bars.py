"""Fetch a bounded, timestamp-ordered candle sample."""

import argparse

from common import add_range_arguments, print_result
from src.server.analytics import get_bars


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--symbol", required=True)
    add_range_arguments(parser)
    parser.add_argument("--limit", type=int, default=20)
    args = parser.parse_args()
    print_result(
        lambda: get_bars(args.symbol, args.start, args.end, args.limit)
    )


if __name__ == "__main__":
    main()
