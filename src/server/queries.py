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
ORDER BY timestamp ASC, open ASC, high ASC, low ASC, close ASC, volume ASC
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

INTRADAY_STATS_SQL = """
SELECT
  first(open ORDER BY timestamp, open, high, low, close, volume) AS open,
  last(close ORDER BY timestamp, open, high, low, close, volume) AS close,
  max(high) AS high,
  min(low) AS low,
  CAST(sum(volume) AS DOUBLE) AS total_volume,
  sum(((high + low + close) / 3.0) * volume) / nullif(sum(volume), 0) AS vwap,
  last(close ORDER BY timestamp, open, high, low, close, volume)
    - first(open ORDER BY timestamp, open, high, low, close, volume)
    AS absolute_return,
  CASE
    WHEN first(open ORDER BY timestamp, open, high, low, close, volume) != 0
    THEN (
      last(close ORDER BY timestamp, open, high, low, close, volume)
      / first(open ORDER BY timestamp, open, high, low, close, volume) - 1
    ) * 100
  END AS percentage_return,
  count(*) AS bar_count,
  first(timestamp ORDER BY timestamp, open, high, low, close, volume)
    AS first_timestamp,
  last(timestamp ORDER BY timestamp, open, high, low, close, volume)
    AS last_timestamp
FROM read_parquet(?, hive_partitioning = true)
WHERE symbol = ?
  AND year = ?
  AND month = ?
  AND trading_date = ?
"""

PRICE_EXTREMES_SQL = """
WITH filtered AS (
  SELECT timestamp, high, low, open, close, volume
  FROM read_parquet(?, hive_partitioning = true)
  WHERE symbol = ?
    AND (year > ? OR (year = ? AND month >= ?))
    AND (year < ? OR (year = ? AND month <= ?))
    AND timestamp >= CAST(? AS TIMESTAMPTZ)
    AND timestamp <= CAST(? AS TIMESTAMPTZ)
)
SELECT
  max(high) AS highest_high,
  first(timestamp ORDER BY high DESC, timestamp ASC, open, low, close, volume)
    AS highest_high_timestamp,
  min(low) AS lowest_low,
  first(timestamp ORDER BY low ASC, timestamp ASC, open, high, close, volume)
    AS lowest_low_timestamp,
  max(high) - min(low) AS range_absolute,
  CASE WHEN min(low) > 0
    THEN (max(high) - min(low)) / min(low) * 100
  END AS range_percentage
FROM filtered
"""
