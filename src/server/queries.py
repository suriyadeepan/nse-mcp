"""Predefined parameterized SQL for analytics over Hive-partitioned Parquet.

Each query's first parameter is the internally configured Parquet glob. The
remaining values are bound by DuckDB; callers must not build SQL from input.
The range queries also constrain Hive year/month strings (`YYYY`, `MM`) for
partition pruning.
"""

BARS_IN_RANGE_SQL = """
SELECT timestamp, open, high, low, close, volume
FROM read_parquet(?, hive_partitioning = true)
WHERE symbol = ?
  AND (year > ? OR (year = ? AND month >= ?))
  AND (year < ? OR (year = ? AND month <= ?))
  AND timestamp >= CAST(? AS TIMESTAMPTZ)
  AND timestamp <= CAST(? AS TIMESTAMPTZ)
ORDER BY timestamp ASC
LIMIT ?
"""

BARS_BEFORE_START_SQL = """
SELECT timestamp, open, high, low, close, volume
FROM read_parquet(?, hive_partitioning = true)
WHERE symbol = ?
  AND (year > ? OR (year = ? AND month >= ?))
  AND (year < ? OR (year = ? AND month <= ?))
  AND timestamp < CAST(? AS TIMESTAMPTZ)
ORDER BY timestamp DESC
LIMIT ?
"""

DAILY_BARS_SQL = """
SELECT
  symbol,
  trading_date,
  arg_min(open, timestamp) AS open,
  max(high) AS high,
  min(low) AS low,
  arg_max(close, timestamp) AS close,
  sum(volume) AS volume
FROM read_parquet(?, hive_partitioning = true)
WHERE symbol = ?
  AND (year > ? OR (year = ? AND month >= ?))
  AND (year < ? OR (year = ? AND month <= ?))
  AND trading_date >= ?
  AND trading_date <= ?
GROUP BY symbol, trading_date
ORDER BY symbol ASC, trading_date ASC
"""
