# DuckDB Analytics Layer TODO

The requested `src/market_os/server/` location maps to this repository's existing
`src/server/` package. Processed data is written under Hive partitions
`interval/year/month/symbol`; current symbol discovery only checks top-level
Parquet files, so allowlist discovery must account for that layout.

1. [x] Add centralized analytics configuration and the DuckDB dependency; reuse the existing server package and processed-data conventions.
2. [ ] Add predefined parameterized DuckDB queries and shared validation for symbols, timestamps, ranges, limits, and enumerated inputs.
3. [ ] Implement `get_bars()` with ascending UTC timestamps, OHLCV schema, and configured bounds.
4. [ ] Implement `intraday_stats()` and `get_price_extremes()` with IST trading dates, correct aggregation, deterministic ties, and safe empty/zero-volume results.
5. [ ] Implement `get_volume_stats()` with chronological IST hourly/daily buckets and clearly defined candle versus bucket averages.
6. [ ] Implement `compute_indicators()` with configurable periods, sufficient prior-candle warm-up, explicit null/insufficient-history behavior, and no look-ahead.
7. [ ] Implement daily `compare_symbols()` metrics and return ranking using common trading dates, 252-day volatility annualization, and missing-data-safe returns.
8. [ ] Define consistent documented result/error schemas; keep calculations and filtering in DuckDB over partition-pruned Parquet scans, with no caller SQL or path inputs.
9. [ ] Add synthetic Parquet tests for calculations, empty/invalid inputs, duplicates and gaps, IST/session boundaries, indicator warm-up/look-ahead, symbol history mismatches, limits, and SQL injection; run relevant tests and record limitations.
