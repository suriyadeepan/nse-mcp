"""Reusable DuckDB analytics over configured processed Parquet data."""

from collections.abc import Iterable
from datetime import date, datetime, timedelta, timezone
from typing import NotRequired, TypedDict
from zoneinfo import ZoneInfo

import duckdb

from .config import ANALYTICS_CONFIG
from .queries import (
    BARS_IN_RANGE_SQL,
    COMPARE_SYMBOLS_SQL,
    INDICATOR_CALCULATIONS_SQL,
    INTRADAY_STATS_SQL,
    PRICE_EXTREMES_SQL,
    VOLUME_STATS_SQL,
)
from .validation import (
    AnalyticsDataError,
    AnalyticsInputError,
    validate_bucket,
    validate_datetime_range,
    validate_indicators,
    validate_indicator_parameters,
    validate_interval,
    validate_limit,
    validate_symbol,
    validate_symbols,
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


class IndicatorValue(TypedDict):
    """One output candle with only the requested indicator columns present."""

    timestamp: datetime
    close: float
    SMA: NotRequired[float | None]
    EMA: NotRequired[float | None]
    RSI: NotRequired[float | None]
    ATR: NotRequired[float | None]


class IndicatorsResult(TypedDict):
    """Timestamped closing prices, indicator values, and readiness status."""

    values: list[IndicatorValue]
    indicator_parameters: dict[str, dict[str, int]]
    indicator_status: dict[str, str]
    returned_count: int


class SymbolComparison(TypedDict):
    """One symbol's performance, risk, and activity over common IST dates."""

    symbol: str
    rank: int | None
    status: str
    common_trading_days: int
    total_return_pct: float | None
    average_daily_return_pct: float | None
    annualized_volatility_pct: float | None
    maximum_drawdown_pct: float | None
    total_volume: float | None
    average_daily_volume: float | None
    average_daily_turnover: float | None


class CompareSymbolsResult(TypedDict):
    """Comparison metrics and the dates shared by every requested symbol."""

    common_trading_dates: list[date]
    common_trading_days: int
    symbols: list[SymbolComparison]


def _parquet_glob() -> str:
    return str(ANALYTICS_CONFIG.processed_data_dir / "**" / "*.parquet")


def _query_rows(query: str, params: list[object]) -> list[dict[str, object]]:
    """Execute a predefined query with the shared DuckDB resource limits."""
    connection = None
    try:
        connection = duckdb.connect(
            database=":memory:",
            config={
                "memory_limit": ANALYTICS_CONFIG.duckdb_memory_limit,
                "threads": str(ANALYTICS_CONFIG.duckdb_threads),
            },
        )
        return connection.sql(query, params=params).to_arrow_table().to_pylist()
    except duckdb.Error as exc:
        raise AnalyticsDataError(
            "analytics query could not read processed data"
        ) from exc
    finally:
        if connection is not None:
            connection.close()


def _normalize_timestamp(value: object) -> datetime | None:
    if value is None:
        return None
    if not isinstance(value, datetime) or value.tzinfo is None:
        raise AnalyticsDataError(
            "processed Parquet timestamps must include a timezone"
        )
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


def compute_indicators(
    symbol: str,
    start_datetime: datetime | str,
    end_datetime: datetime | str,
    indicators: Iterable[object],
    parameters: object = None,
) -> IndicatorsResult:
    """Calculate SMA, EMA, RSI, and ATR with prior-candle warm-up in DuckDB.

    ``parameters`` maps requested indicator names to integer periods; omitted
    periods use the configured default. The returned ``values`` have UTC
    timestamps and explicit ``None`` values until each indicator has enough
    history. ``indicator_status`` is ``no_data``, ``insufficient_history``, or
    ``ready`` for each requested indicator. A flat-price RSI is 50; RSI with
    gains but no losses is 100. EMA is seeded with the first period's SMA.
    """
    validated_symbol = validate_symbol(symbol)
    start, end = validate_datetime_range(start_datetime, end_datetime)
    requested = validate_indicators(indicators)
    if not requested:
        raise AnalyticsInputError("at least one indicator must be requested")
    supplied_periods = validate_indicator_parameters(requested, parameters)
    periods = {
        name: supplied_periods.get(
            name, ANALYTICS_CONFIG.indicator_default_period
        )
        for name in ("SMA", "EMA", "RSI", "ATR")
    }
    required_warmup = max(periods[name] for name in requested)
    if "EMA" in requested:
        required_warmup = max(required_warmup, periods["EMA"] * 10)
    warmup_count = max(
        ANALYTICS_CONFIG.indicator_warmup_default, required_warmup
    )
    if warmup_count > ANALYTICS_CONFIG.indicator_warmup_limit:
        raise AnalyticsInputError(
            "required indicator warm-up exceeds the configured limit of "
            f"{ANALYTICS_CONFIG.indicator_warmup_limit} candles"
        )

    start_year, start_month = start.strftime("%Y"), start.strftime("%m")
    end_year, end_month = end.strftime("%Y"), end.strftime("%m")
    ema_alpha = 2.0 / (periods["EMA"] + 1.0)
    rows = _query_rows(
        INDICATOR_CALCULATIONS_SQL,
        [
            _parquet_glob(),
            validated_symbol,
            start_year,
            start_year,
            start_month,
            start.isoformat(),
            warmup_count,
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
            ANALYTICS_CONFIG.max_returned_rows + 1,
            periods["SMA"],
            periods["SMA"] - 1,
            periods["RSI"] - 1,
            periods["RSI"] - 1,
            periods["RSI"] - 1,
            periods["RSI"] - 1,
            periods["ATR"] - 1,
            periods["ATR"] - 1,
            periods["EMA"],
            periods["EMA"],
            ema_alpha,
            ema_alpha,
            periods["RSI"],
            periods["RSI"],
            periods["ATR"],
            ANALYTICS_CONFIG.max_returned_rows + 1,
        ],
    )
    if len(rows) > ANALYTICS_CONFIG.max_returned_rows:
        raise AnalyticsInputError(
            "indicator result count exceeds the configured maximum of "
            f"{ANALYTICS_CONFIG.max_returned_rows}"
        )

    field_names = {
        "SMA": "sma_value",
        "EMA": "ema_value",
        "RSI": "rsi_value",
        "ATR": "atr_value",
    }
    values: list[IndicatorValue] = []
    for row in rows:
        output: IndicatorValue = {
            "timestamp": _normalize_timestamp(row["timestamp"]),
            "close": row["close"],
        }  # type: ignore[typeddict-item]
        for name in requested:
            output[name] = row[field_names[name]]  # type: ignore[literal-required]
        values.append(output)

    indicator_status = {
        name: (
            "no_data"
            if not values
            else "ready"
            if any(value[name] is not None for value in values)
            else "insufficient_history"
        )
        for name in requested
    }
    return {
        "values": values,
        "indicator_parameters": {
            name: {"period": periods[name]} for name in requested
        },
        "indicator_status": indicator_status,
        "returned_count": len(values),
    }


def compare_symbols(
    symbols: Iterable[object],
    start_datetime: datetime | str,
    end_datetime: datetime | str,
    interval: str = "daily",
) -> CompareSymbolsResult:
    """Compare symbols over the trading dates present for every symbol.

    Range instants are normalized to UTC and mapped to IST calendar dates for
    daily aggregation. Performance and risk use daily close-to-close returns;
    annualized volatility is sample standard deviation times sqrt(252), and
    maximum drawdown is the most negative peak-to-trough percentage. Volume
    and turnover averages use the shared-date set. Metrics requiring returns
    return metrics are ``None`` with ``insufficient_history`` when fewer than
    two common closes exist. Sample volatility needs three common closes (two
    returns), so the overall status remains ``insufficient_history`` below that
    point. Ranking is descending by total return, with symbol order as a
    deterministic tie-breaker.
    """
    validated_symbols = validate_symbols(symbols, minimum=2)
    validate_limit(
        len(validated_symbols), maximum=ANALYTICS_CONFIG.max_returned_rows
    )
    start, end = validate_datetime_range(start_datetime, end_datetime)
    validate_interval(interval)
    market_timezone = ZoneInfo(ANALYTICS_CONFIG.market_timezone)
    start_date = start.astimezone(market_timezone).date()
    end_date = end.astimezone(market_timezone).date()
    # A local trading date can begin in the prior UTC calendar month. Widen
    # Hive partition bounds by one day while retaining exact local date filters.
    partition_start = start_date - timedelta(days=1)
    start_year, start_month = (
        partition_start.strftime("%Y"),
        partition_start.strftime("%m"),
    )
    end_year, end_month = end_date.strftime("%Y"), end_date.strftime("%m")
    rows = _query_rows(
        COMPARE_SYMBOLS_SQL,
        [
            list(validated_symbols),
            _parquet_glob(),
            start_year,
            start_year,
            start_month,
            end_year,
            end_year,
            end_month,
            start_date,
            end_date,
            len(validated_symbols),
        ],
    )
    common_dates = rows[0]["common_trading_dates"] if rows else []
    if common_dates is None:
        common_dates = []
    results: list[SymbolComparison] = []
    for row in rows:
        results.append(
            {
                "symbol": row["symbol"],
                "rank": row["rank"],
                "status": row["status"],
                "common_trading_days": row["common_trading_days"],
                "total_return_pct": row["total_return_pct"],
                "average_daily_return_pct": row["average_daily_return_pct"],
                "annualized_volatility_pct": row["annualized_volatility_pct"],
                "maximum_drawdown_pct": row["maximum_drawdown_pct"],
                "total_volume": row["total_volume"],
                "average_daily_volume": row["average_daily_volume"],
                "average_daily_turnover": row["average_daily_turnover"],
            }
        )
    return {
        "common_trading_dates": common_dates,
        "common_trading_days": len(common_dates),
        "symbols": results,
    }
