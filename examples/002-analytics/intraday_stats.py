"""Summarize one symbol's IST calendar trading session."""

import argparse

from common import print_result
from src.server.analytics import intraday_stats


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--symbol", required=True)
    parser.add_argument("--date", required=True, help="IST date in YYYY-MM-DD form")
    args = parser.parse_args()
    print_result(lambda: intraday_stats(args.symbol, args.date))


if __name__ == "__main__":
    main()
