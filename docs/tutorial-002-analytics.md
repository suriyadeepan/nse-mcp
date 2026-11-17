# Tutorial: Query processed market data with DuckDB analytics

This tutorial calls the six public functions in `src.server.analytics`. Each
function reads the configured `data/processed/` Parquet dataset directly
through DuckDB. The Python examples accept inputs from the command line and
print the function's result as JSON.

## 1. Prepare your query

Run commands from the repository root. Install the project dependencies first
if this checkout has not been set up. The example scripts add the repository
root to Python's import path, so they can be run directly:

```sh
uv run examples/002-analytics/get_bars.py --help
```

Find valid symbols in the configured processed dataset:

```sh
uv run python -c 'from src.server.config import ANALYTICS_CONFIG; from src.server.data import list_symbols; print(list_symbols(ANALYTICS_CONFIG.processed_data_dir))'
```

Use a listed symbol in the examples. Symbols are checked against the Parquet
partitions, so an unknown symbol fails validation. This checkout currently has
no processed Parquet files; populate `data/processed/` using the ingestion
workflow in [Tutorial 001](tutorial-001-ingestion.md) before querying.

Range examples use offset-aware ISO-8601 timestamps. The bounds are inclusive
and are normalized to UTC instants. For example, `2025-03-03T09:15:00+05:30`
represents the start of a session in India. Session dates and volume buckets
are interpreted in `Asia/Kolkata`.

## 2. Retrieve candles

Use `get_bars` to inspect a small, ordered sample before doing further analysis.
`limit` is required by the function and is capped by the configured result
limit.

```sh
uv run examples/002-analytics/get_bars.py \
  --symbol RELIANCE \
  --start 2025-03-03T09:15:00+05:30 \
  --end 2025-03-03T10:00:00+05:30 \
  --limit 10
```

The JSON contains `bars` with UTC timestamps and OHLCV values, plus
`returned_count`. Duplicate timestamps remain separate rows and have stable
ordering. Choose a smaller range or limit for inspection.

## 3. Summarize an IST trading date

Use `intraday_stats` when you need the session open and close, high and low,
total volume, VWAP, and return. Pass the trading date as an IST calendar date,
not a timestamp.

```sh
uv run examples/002-analytics/intraday_stats.py \
  --symbol RELIANCE --date 2025-03-03
```

VWAP weights each candle's typical price `(high + low + close) / 3` by its
volume. Empty dates return `bar_count: 0` with unavailable metrics set to
`null`; zero total volume produces a `null` VWAP.

## 4. Find a period's price extremes

Use `get_price_extremes` to locate the high and low and their earliest matching
timestamps in a bounded range. The percentage range is measured against the
lowest low.

```sh
uv run examples/002-analytics/price_extremes.py \
  --symbol RELIANCE \
  --start 2025-03-01T00:00:00+05:30 \
  --end 2025-03-07T23:59:59+05:30
```

An empty range returns `null` metrics. The function's range limit still
applies even though this call does not take a row limit.

## 5. Analyze volume by hour or day

`get_volume_stats` reports candle-level totals, average, maximum and minimum,
along with time-ordered IST bucket totals. The result includes both
`average_volume` (per candle) and `average_bucket_volume` (per hourly or daily
bucket); keep these meanings distinct.

Daily buckets:

```sh
uv run examples/002-analytics/volume_stats.py \
  --symbol RELIANCE \
  --start 2025-03-01T00:00:00+05:30 \
  --end 2025-03-07T23:59:59+05:30 \
  --bucket daily
```

Hourly buckets:

```sh
uv run examples/002-analytics/volume_stats.py \
  --symbol RELIANCE \
  --start 2025-03-03T09:15:00+05:30 \
  --end 2025-03-03T15:30:00+05:30 \
  --bucket hourly
```

Hourly labels include the `+05:30` IST offset. Bucket output is chronological
and is limited by the configured maximum result size.

## 6. Calculate technical indicators

`compute_indicators` supports SMA, EMA, RSI, and ATR. SMA, EMA, and RSI use
closing prices. ATR uses high, low, and previous close. The function fetches
prior candles for warm-up, computes indicators before applying the output
range, and does not use future candles.

Request defaults for all four indicators:

```sh
uv run examples/002-analytics/compute_indicators.py \
  --symbol RELIANCE \
  --start 2025-03-03T09:15:00+05:30 \
  --end 2025-03-10T15:30:00+05:30
```

Request selected indicators with custom periods:

```sh
uv run examples/002-analytics/compute_indicators.py \
  --symbol RELIANCE \
  --start 2025-03-03T09:15:00+05:30 \
  --end 2025-03-10T15:30:00+05:30 \
  --indicators SMA RSI ATR --sma-period 20 --rsi-period 14 --atr-period 14
```

The output contains timestamped closes, requested indicator columns, the
effective `indicator_parameters`, and an `indicator_status` per indicator.
Initial values can be `null` until enough history exists. Status is `ready`,
`insufficient_history`, or `no_data`; periods are bounded by configuration.

## 7. Compare symbols

Use `compare_symbols` for a daily comparison across at least two distinct
symbols. It intersects the symbols' available IST trading dates and computes
returns only on those common dates. Missing dates are excluded rather than
treated as zero returns.

```sh
uv run examples/002-analytics/compare_symbols.py \
  --symbols RELIANCE TCS INFY \
  --start 2025-03-01T00:00:00+05:30 \
  --end 2025-03-31T23:59:59+05:30 \
  --interval daily
```

Each symbol result includes total return, average daily return, annualized
volatility (252 trading days), maximum drawdown, total and average daily
volume, average daily turnover, rank, and a readiness `status`. Fewer than two
common closes makes return metrics unavailable; volatility needs at least two
returns. Ranking is by total return, descending, with a deterministic symbol
tie-break.

## 8. Handle errors and limits

Examples print analytics exceptions as JSON with a stable `code` and
`message`. Invalid symbols, malformed timestamps, unsupported bucket or
interval names, and configured range or result limit violations use
`invalid_input`. Unavailable or unreadable processed data uses
`data_unavailable`. The Python API raises these as `AnalyticsError` subclasses;
see [result and error schemas](002-analytics-results.md) for field details.

The dataset path, timezone, date and row limits, DuckDB resources, and indicator
warm-up bounds are centralized in `src/server/config.py`. Public functions do
not accept SQL or filesystem paths.
