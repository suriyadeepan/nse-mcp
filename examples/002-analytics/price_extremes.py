"""Find the earliest timestamps of the highest high and lowest low."""

import argparse

from common import add_range_arguments, print_result
from src.server.analytics import get_price_extremes


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--symbol", required=True)
    add_range_arguments(parser)
    args = parser.parse_args()
    print_result(
        lambda: get_price_extremes(args.symbol, args.start, args.end)
    )


if __name__ == "__main__":
    main()
