"""Compare symbols on shared IST trading dates using daily bars."""

import argparse

from common import add_range_arguments, print_result
from src.server.analytics import compare_symbols


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--symbols", nargs="+", required=True, help="At least two distinct symbols"
    )
    add_range_arguments(parser)
    parser.add_argument("--interval", choices=("daily",), default="daily")
    args = parser.parse_args()
    print_result(
        lambda: compare_symbols(
            args.symbols, args.start, args.end, interval=args.interval
        )
    )


if __name__ == "__main__":
    main()
