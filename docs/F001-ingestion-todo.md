# F001: Market data ingestion tasks

Scope: process only `data/raw/*.parquet` files whose filename stem appears in
`data/index/NIFTY50.csv` under `Ticker`. Never alter files in `data/raw/`.

The implementation in `scripts/ingestion.py` is partial. The checklist records
which tasks have been completed and verified.

Persistent tests for tasks 1 and 2 are in `tests/test_ingestion.py`; add or update
tests alongside each subsequent implementation task.

1. [x] **Lock down input scope.** Read `Ticker` values and discover matching
   raw Parquet files only; report out-of-scope files without processing them.
2. [x] **Check each Parquet file.** Handle unreadable files, missing required
   columns, inconsistent types, and empty files independently; log file-level
   errors and continue to the next in-scope file.
3. [x] **Normalize dates and timestamps.** Validate 13-digit epoch milliseconds,
   store timestamps as UTC-aware values, derive `trading_date` in `Asia/Kolkata`,
   and reject null or malformed dates.
4. [x] **Validate OHLCV values.** Reject null, NaN, non-numeric, or infinite
   values; require positive prices and non-negative integral volume; include all
   applicable reasons on each rejected row.
5. [x] **Check bar consistency and duplicates.** Apply the OHLC bounds and retain
   the first row for each timestamp within its file, rejecting later duplicates.
6. [x] **Validate NSE session times.** Check inclusive 09:15:00.000–15:30:00.000
   trading hours with the IST clock at millisecond precision; derive trading
   dates and chronology from IST-converted timestamps. Persistent boundary and
   IST-calendar tests are in `tests/test_ingestion.py`.
7. [x] **Report chronology and gaps.** Count out-of-order source rows and
   intraday missing one-minute intervals; compare bars only within the same
   IST trading date so overnight sessions, weekends, and NSE holidays are
   skipped. Include bounded gap details without rejecting valid rows.
   Persistent tests are in `tests/test_ingestion.py`.
8. [x] **Write processed Parquet.** Emit the consistent output schema with ZSTD
   level 3 under Hive partitions `interval/year/month/symbol`; combine all rows
   for each partition into one deterministic file. Persistent writer tests are
   in `tests/test_ingestion.py`.
9. [x] **Write rejects and file errors.** Emit deterministic per-symbol reject
   CSVs with source filename and all reasons, remove stale empty reject files,
   and reset the separate file error log for each run. Persistent coverage is in
   `tests/test_ingestion.py`.
10. [x] **Complete the run summary.** Report discovered/processed/error files,
    input/valid/rejected rows, rejection counts, gap details, output paths and
    per-file row counts, and duration. A subprocess test runs the script on
    representative fixtures; persistent coverage is in `tests/test_ingestion.py`.

## Bugs

- [x] `uv run scripts/ingestion.py` failed during project build because
  `uv_build` expects the `src/kite_mcp` package declared by the project. Restore
  its package initializer; verified with `uv run scripts/ingestion.py --help`.
- [x] Ingestion failed on Parquet timestamps with the fixed-offset timezone
  `+05:30`, which Polars could not parse. Normalize timezone-aware Arrow date
  columns to UTC before converting to Polars; regression coverage is in
  `tests/test_ingestion.py`.
