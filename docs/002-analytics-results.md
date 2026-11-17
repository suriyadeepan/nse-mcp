# Analytics result and error schemas

The six functions in `src.server.analytics` return dictionaries with stable,
documented keys. Timestamps are timezone-aware UTC instants; trading dates and
volume bucket labels use `Asia/Kolkata`. Numerical metrics that cannot be
calculated are `null` (`None` in Python), never a fabricated zero. Empty
queries return the corresponding empty or null-valued result described below.

| Function | Result keys |
| --- | --- |
| `get_bars` | `bars`: ordered rows with `timestamp`, `open`, `high`, `low`, `close`, `volume`; `returned_count` |
| `intraday_stats` | `open`, `close`, `high`, `low`, `total_volume`, `vwap`, `absolute_return`, `percentage_return`, `bar_count`, `first_timestamp`, `last_timestamp` |
| `get_price_extremes` | `highest_high`, `highest_high_timestamp`, `lowest_low`, `lowest_low_timestamp`, `range_absolute`, `range_percentage` |
| `get_volume_stats` | `total_volume`, `average_volume`, `maximum_volume`, `minimum_volume`, `average_bucket_volume`, `volume_by_bucket`, `bar_count` |
| `compute_indicators` | `values`: rows with `timestamp`, `close`, and only requested indicator columns (`SMA`, `EMA`, `RSI`, `ATR`); `indicator_parameters`; `indicator_status`; `returned_count` |
| `compare_symbols` | `common_trading_dates`, `common_trading_days`, `symbols`: per-symbol performance, risk, activity, rank, and `status` fields |

An empty session returns `bar_count: 0` and null statistics. Empty range
queries return no bars or indicator rows; aggregate metrics are null. A
zero-volume session has a volume of zero and a null VWAP. Indicator columns
remain null until enough prior candles are available; their status is
`no_data`, `insufficient_history`, or `ready`. Symbol comparison metrics that
need returns are null until enough common closes exist; each symbol's status
reports whether return and risk calculations are ready.

Input and configured-limit failures raise `AnalyticsInputError`, a `ValueError`
subclass. Processed-data discovery or DuckDB scan failures raise
`AnalyticsDataError`. Both derive from `AnalyticsError` and provide
`as_dict()` with this stable shape:

```python
{"code": "invalid_input", "message": "..."}
{"code": "data_unavailable", "message": "..."}
```

Callers can branch on `code`; the exception text is also the `message`. The
public functions accept symbols, dates, limits, indicator options, and bucket
or interval names. They do not accept SQL or filesystem paths. Queries are
predefined in `src.server.queries`, bind all caller values as parameters, and
filter partitioned Parquet data in DuckDB.

## Current limits

- Symbol comparison currently supports only the `daily` interval and compares
  the intersection of trading dates present for every requested symbol.
- Duplicate timestamps are retained as separate candles; stable OHLCV sort keys
  make their ordering deterministic, but the analytics layer does not dedupe or
  repair processed data.
- Indicator warm-up is capped by configuration. Results that cannot satisfy a
  requested period are returned with null indicator values and an explicit
  status rather than being extrapolated.
