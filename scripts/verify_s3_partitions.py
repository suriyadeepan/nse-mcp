#!/usr/bin/env python3
"""Verify symbol/month filters and DuckDB partition pruning on the S3 dataset."""

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
        dataset = parquet_glob(config)
        filters = [dataset, "1m", args.year, args.month, args.symbol]
        rows, first_date, last_date, symbols, years, months = connection.execute(
            "SELECT count(*), min(trading_date), max(trading_date), "
            "list_distinct(list(symbol)), list_distinct(list(year)), "
            "list_distinct(list(TRY_CAST(month AS INTEGER))) "
            "FROM read_parquet(?, hive_partitioning = true) "
            "WHERE interval = ? AND year = ? AND month = ? AND symbol = ?",
            filters,
        ).fetchone()
        plan = connection.execute(
            "EXPLAIN SELECT count(*) FROM read_parquet(?, hive_partitioning = true) "
            "WHERE interval = ? AND year = ? AND month = ? AND symbol = ?",
            filters,
        ).fetchone()[1]
    finally:
        connection.close()

    if not rows:
        raise SystemExit(
            f"No {args.symbol} one-minute bars found for {args.year}-{args.month:02}."
        )
    if symbols != [args.symbol] or years != [args.year] or months != [args.month]:
        raise SystemExit("Filtered query returned rows outside the requested partitions.")

    print(
        f"Verified {rows:,} one-minute bars for {args.symbol}, "
        f"{args.year}-{args.month:02} ({first_date} through {last_date})."
    )
    print("DuckDB query plan (look for File Filters on interval, year, month, symbol):")
    print(plan)


if __name__ == "__main__":
    main()
