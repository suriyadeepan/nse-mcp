"""Calculate requested indicators using prior candles for warm-up."""

import argparse

from common import add_range_arguments, print_result
from src.server.analytics import compute_indicators


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--symbol", required=True)
    add_range_arguments(parser)
    parser.add_argument(
        "--indicators",
        nargs="+",
        choices=("SMA", "EMA", "RSI", "ATR"),
        default=("SMA", "EMA", "RSI", "ATR"),
    )
    parser.add_argument("--sma-period", type=int)
    parser.add_argument("--ema-period", type=int)
    parser.add_argument("--rsi-period", type=int)
    parser.add_argument("--atr-period", type=int)
    args = parser.parse_args()

    parameters = {
        name: period
        for name, period in (
            ("SMA", args.sma_period),
            ("EMA", args.ema_period),
            ("RSI", args.rsi_period),
            ("ATR", args.atr_period),
        )
        if period is not None
    }
    print_result(
        lambda: compute_indicators(
            args.symbol, args.start, args.end, args.indicators, parameters
        )
    )


if __name__ == "__main__":
    main()
