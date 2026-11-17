#!/usr/bin/env python3
"""Summarize one symbol's monthly bars directly from the configured S3 dataset."""

import argparse

from src.server.config import load_analytics_config
from src.server.data import connect_duckdb, parquet_glob


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--symbol", default="RELIANCE")
    parser.add_argument("--year", type=int, default=2026)
    parser.add_argument("--month", type=int, choices=range(1, 13), default=8)
    args = parser.parse_args()

    config = load_analytics_config()
    if config.processed_data_source != "s3":
        parser.error("set PROCESSED_DATA_SOURCE=s3 to query the S3 dataset")

    connection = connect_duckdb(config)
    try:
        result = connection.execute(
            "SELECT count(*) AS bars, "
            "count(DISTINCT trading_date) AS sessions, "
            "arg_min(open, timestamp) AS first_open, "
            "arg_max(close, timestamp) AS last_close "
            "FROM read_parquet(?, hive_partitioning = true) "
            "WHERE interval = ? AND year = ? AND month = ? AND symbol = ?",
            [
                parquet_glob(config),
                "1m",
                args.year,
                args.month,
                args.symbol,
            ],
        ).fetchone()
    finally:
        connection.close()

    bars, sessions, first_open, last_close = result
    period = f"{args.year}-{args.month:02}"
    if not bars:
        print(f"No {args.symbol} one-minute bars found for {period}.")
        return

    change = (last_close / first_open - 1) * 100 if first_open else None
    close_summary = f"₹{first_open:,.2f} open → ₹{last_close:,.2f} close"
    if change is not None:
        close_summary += f" ({change:+.2f}%)"
    print(
        f"{args.symbol} · {period}: {sessions} sessions, {bars:,} one-minute bars; "
        f"{close_summary}."
    )


if __name__ == "__main__":
    main()
