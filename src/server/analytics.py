"""Reusable DuckDB analytics over configured processed Parquet data."""

from datetime import datetime, timezone
from typing import TypedDict

import duckdb

from .config import ANALYTICS_CONFIG
from .queries import BARS_IN_RANGE_SQL
from .validation import validate_datetime_range, validate_limit, validate_symbol


class OHLCVBar(TypedDict):
    """One candle with an aware UTC timestamp and OHLCV fields."""

    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: int | float


class BarsResult(TypedDict):
    """Result schema returned by :func:`get_bars`."""

    bars: list[OHLCVBar]
    returned_count: int


def get_bars(
    symbol: str,
    start_datetime: datetime | str,
    end_datetime: datetime | str,
    limit: int,
) -> BarsResult:
    """Return OHLCV bars in an inclusive UTC timestamp range.

    Timestamps may be timezone-aware ``datetime`` objects or ISO-8601 strings
    with an explicit offset. The result contains ``bars`` (ascending by
    timestamp, with deterministic ordering for duplicate timestamps) and
    ``returned_count``. An empty range returns an empty list and a count of 0.
    The requested range and limit are checked against the shared configuration.
    """
    validated_symbol = validate_symbol(symbol)
    start, end = validate_datetime_range(start_datetime, end_datetime)
    validated_limit = validate_limit(limit)

    start_year, start_month = start.strftime("%Y"), start.strftime("%m")
    end_year, end_month = end.strftime("%Y"), end.strftime("%m")
    parquet_glob = str(ANALYTICS_CONFIG.processed_data_dir / "**" / "*.parquet")
    params = [
        parquet_glob,
        validated_symbol,
        start_year,
        start_year,
        start_month,
        end_year,
        end_year,
        end_month,
        start.isoformat(),
        end.isoformat(),
        validated_limit,
    ]

    connection = duckdb.connect(
        database=":memory:",
        config={
            "memory_limit": ANALYTICS_CONFIG.duckdb_memory_limit,
            "threads": str(ANALYTICS_CONFIG.duckdb_threads),
        },
    )
    try:
        bars = (
            connection.sql(BARS_IN_RANGE_SQL, params=params)
            .to_arrow_table()
            .to_pylist()
        )
    finally:
        connection.close()

    for bar in bars:
        timestamp = bar["timestamp"]
        if not isinstance(timestamp, datetime) or timestamp.tzinfo is None:
            raise ValueError("processed Parquet timestamps must include a timezone")
        bar["timestamp"] = timestamp.astimezone(timezone.utc)

    return {"bars": bars, "returned_count": len(bars)}
