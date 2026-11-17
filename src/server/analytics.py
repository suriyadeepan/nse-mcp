"""Reusable DuckDB analytics over configured processed Parquet data."""

from datetime import date, datetime, timezone
from typing import TypedDict
from zoneinfo import ZoneInfo

import duckdb

from .config import ANALYTICS_CONFIG
from .queries import (
    BARS_IN_RANGE_SQL,
    INTRADAY_STATS_SQL,
    PRICE_EXTREMES_SQL,
    VOLUME_STATS_SQL,
)
from .validation import (
    AnalyticsInputError,
    validate_bucket,
    validate_datetime_range,
    validate_limit,
    validate_symbol,
    validate_trading_date,
)


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


class IntradayStatsResult(TypedDict):
    """Session summary; unavailable values are ``None`` for empty/undefined data."""

    open: float | None
    close: float | None
    high: float | None
    low: float | None
    total_volume: int | float | None
    vwap: float | None
    absolute_return: float | None
    percentage_return: float | None
    bar_count: int
    first_timestamp: datetime | None
    last_timestamp: datetime | None


class PriceExtremesResult(TypedDict):
    """Range extremes and their earliest matching timestamps."""

    highest_high: float | None
    highest_high_timestamp: datetime | None
    lowest_low: float | None
    lowest_low_timestamp: datetime | None
    range_absolute: float | None
    range_percentage: float | None


class VolumeBucket(TypedDict):
    """One chronologically ordered IST bucket and its aggregate volume."""

    bucket: str
    volume: int | float


class VolumeStatsResult(TypedDict):
    """Candle-level volume statistics and IST bucket totals."""

    total_volume: int | float | None
    average_volume: float | None
    maximum_volume: int | float | None
    minimum_volume: int | float | None
    average_bucket_volume: float | None
    volume_by_bucket: list[VolumeBucket]
    bar_count: int


def _parquet_glob() -> str:
    return str(ANALYTICS_CONFIG.processed_data_dir / "**" / "*.parquet")


def _query_rows(query: str, params: list[object]) -> list[dict[str, object]]:
    """Execute a predefined query with the shared DuckDB resource limits."""
    connection = duckdb.connect(
        database=":memory:",
        config={
            "memory_limit": ANALYTICS_CONFIG.duckdb_memory_limit,
            "threads": str(ANALYTICS_CONFIG.duckdb_threads),
        },
    )
    try:
        return (
            connection.sql(query, params=params)
            .to_arrow_table()
            .to_pylist()
        )
    finally:
        connection.close()


def _normalize_timestamp(value: object) -> datetime | None:
    if value is None:
        return None
    if not isinstance(value, datetime) or value.tzinfo is None:
        raise ValueError("processed Parquet timestamps must include a timezone")
    return value.astimezone(timezone.utc)


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
    parquet_glob = _parquet_glob()
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

    bars = _query_rows(BARS_IN_RANGE_SQL, params)

    for bar in bars:
        bar["timestamp"] = _normalize_timestamp(bar["timestamp"])

    return {"bars": bars, "returned_count": len(bars)}


def intraday_stats(symbol: str, trading_date: date | str) -> IntradayStatsResult:
    """Summarize a symbol's IST calendar session.

    ``trading_date`` is an IST calendar date. Empty sessions have ``bar_count``
    zero and ``None`` metrics; zero-volume sessions retain volume 0 and have a
    ``None`` VWAP. Returns are close minus open and that difference as a
    percentage of open; undefined percentages are ``None``.
    """
    validated_symbol = validate_symbol(symbol)
    session_date = validate_trading_date(trading_date)
    row = _query_rows(
        INTRADAY_STATS_SQL,
        [
            _parquet_glob(),
            validated_symbol,
            f"{session_date.year:04}",
            f"{session_date.month:02}",
            session_date,
        ],
    )[0]
    row["first_timestamp"] = _normalize_timestamp(row["first_timestamp"])
    row["last_timestamp"] = _normalize_timestamp(row["last_timestamp"])
    return row  # type: ignore[return-value]


def get_price_extremes(
    symbol: str,
    start_datetime: datetime | str,
    end_datetime: datetime | str,
) -> PriceExtremesResult:
    """Return high/low prices and earliest UTC timestamps in an inclusive range."""
    validated_symbol = validate_symbol(symbol)
    start, end = validate_datetime_range(start_datetime, end_datetime)
    start_year, start_month = start.strftime("%Y"), start.strftime("%m")
    end_year, end_month = end.strftime("%Y"), end.strftime("%m")
    row = _query_rows(
        PRICE_EXTREMES_SQL,
        [
            _parquet_glob(),
            validated_symbol,
            start_year,
            start_year,
            start_month,
            end_year,
            end_year,
            end_month,
            start.isoformat(),
            end.isoformat(),
        ],
    )[0]
    row["highest_high_timestamp"] = _normalize_timestamp(
        row["highest_high_timestamp"]
    )
    row["lowest_low_timestamp"] = _normalize_timestamp(row["lowest_low_timestamp"])
    return row  # type: ignore[return-value]


def get_volume_stats(
    symbol: str,
    start_datetime: datetime | str,
    end_datetime: datetime | str,
    bucket: str,
) -> VolumeStatsResult:
    """Summarize candle volumes and chronological hourly/daily IST buckets.

    ``average_volume``, ``maximum_volume``, and ``minimum_volume`` describe
    individual candles. ``average_bucket_volume`` is the mean of the returned
    bucket totals. Daily labels use ``YYYY-MM-DD``; hourly labels are ISO-8601
    timestamps in the configured market timezone. Empty ranges have no volume
    metrics and an empty bucket list.
    """
    validated_symbol = validate_symbol(symbol)
    start, end = validate_datetime_range(start_datetime, end_datetime)
    validated_bucket = validate_bucket(bucket)
    start_year, start_month = start.strftime("%Y"), start.strftime("%m")
    end_year, end_month = end.strftime("%Y"), end.strftime("%m")
    bucket_unit = "hour" if validated_bucket == "hourly" else "day"
    rows = _query_rows(
        VOLUME_STATS_SQL,
        [
            _parquet_glob(),
            validated_symbol,
            start_year,
            start_year,
            start_month,
            end_year,
            end_year,
            end_month,
            start.isoformat(),
            end.isoformat(),
            bucket_unit,
            ANALYTICS_CONFIG.market_timezone,
            ANALYTICS_CONFIG.max_returned_rows + 1,
        ],
    )
    bucket_rows = [row for row in rows if row["bucket"] is not None]
    if len(bucket_rows) > ANALYTICS_CONFIG.max_returned_rows:
        raise AnalyticsInputError(
            "volume bucket count exceeds the configured maximum of "
            f"{ANALYTICS_CONFIG.max_returned_rows}"
        )

    summary = rows[0]
    market_timezone = ZoneInfo(ANALYTICS_CONFIG.market_timezone)
    volume_by_bucket: list[VolumeBucket] = []
    for row in bucket_rows:
        bucket_value = row["bucket"]
        if not isinstance(bucket_value, datetime):
            raise ValueError("DuckDB returned an unexpected volume bucket type")
        label = (
            bucket_value.date().isoformat()
            if validated_bucket == "daily"
            else bucket_value.replace(tzinfo=market_timezone).isoformat()
        )
        volume_by_bucket.append(
            {"bucket": label, "volume": row["bucket_volume"]}
        )

    return {
        "total_volume": summary["total_volume"],
        "average_volume": summary["average_volume"],
        "maximum_volume": summary["maximum_volume"],
        "minimum_volume": summary["minimum_volume"],
        "average_bucket_volume": summary["average_bucket_volume"],
        "volume_by_bucket": volume_by_bucket,
        "bar_count": summary["bar_count"],
    }  # type: ignore[return-value]
