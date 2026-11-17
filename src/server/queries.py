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

VOLUME_STATS_SQL = """
WITH filtered AS (
  SELECT timestamp, volume
  FROM read_parquet(?, hive_partitioning = true)
  WHERE symbol = ?
    AND (year > ? OR (year = ? AND month >= ?))
    AND (year < ? OR (year = ? AND month <= ?))
    AND timestamp >= CAST(? AS TIMESTAMPTZ)
    AND timestamp <= CAST(? AS TIMESTAMPTZ)
), buckets AS (
  SELECT
    date_trunc(?, timezone(?, timestamp)) AS bucket,
    CAST(sum(volume) AS DOUBLE) AS bucket_volume
  FROM filtered
  GROUP BY bucket
), totals AS (
  SELECT
    CAST(sum(volume) AS DOUBLE) AS total_volume,
    CAST(avg(volume) AS DOUBLE) AS average_volume,
    CAST(max(volume) AS DOUBLE) AS maximum_volume,
    CAST(min(volume) AS DOUBLE) AS minimum_volume,
    count(*) AS bar_count
  FROM filtered
), bucket_totals AS (
  SELECT CAST(avg(bucket_volume) AS DOUBLE) AS average_bucket_volume
  FROM buckets
)
SELECT
  totals.total_volume,
  totals.average_volume,
  totals.maximum_volume,
  totals.minimum_volume,
  totals.bar_count,
  bucket_totals.average_bucket_volume,
  buckets.bucket,
  buckets.bucket_volume
FROM totals
CROSS JOIN bucket_totals
LEFT JOIN buckets ON true
ORDER BY buckets.bucket ASC
LIMIT ?
"""

INDICATOR_CALCULATIONS_SQL = """
WITH RECURSIVE prior_bars AS (
  SELECT timestamp, open, high, low, close, volume, false AS is_output
  FROM read_parquet(?, hive_partitioning = true)
  WHERE symbol = ?
    AND (year < ? OR (year = ? AND month <= ?))
    AND timestamp < CAST(? AS TIMESTAMPTZ)
  ORDER BY timestamp DESC, open DESC, high DESC, low DESC, close DESC, volume DESC
  LIMIT ?
), requested_bars AS (
  SELECT timestamp, open, high, low, close, volume, true AS is_output
  FROM read_parquet(?, hive_partitioning = true)
  WHERE symbol = ?
    AND (year > ? OR (year = ? AND month >= ?))
    AND (year < ? OR (year = ? AND month <= ?))
    AND timestamp >= CAST(? AS TIMESTAMPTZ)
    AND timestamp <= CAST(? AS TIMESTAMPTZ)
  ORDER BY timestamp ASC, open ASC, high ASC, low ASC, close ASC, volume ASC
  LIMIT ?
), input_bars AS (
  SELECT * FROM prior_bars
  UNION ALL
  SELECT * FROM requested_bars
), ordered AS (
  SELECT
    *,
    row_number() OVER (
      ORDER BY timestamp, open, high, low, close, volume
    ) AS rn,
    lag(close) OVER (
      ORDER BY timestamp, open, high, low, close, volume
    ) AS previous_close
  FROM input_bars
), changes AS (
  SELECT
    *,
    CASE WHEN previous_close IS NULL OR close IS NULL THEN NULL
      ELSE greatest(close - previous_close, 0)
    END AS gain,
    CASE WHEN previous_close IS NULL OR close IS NULL THEN NULL
      ELSE greatest(previous_close - close, 0)
    END AS loss,
    CASE WHEN previous_close IS NULL OR high IS NULL OR low IS NULL THEN NULL
      ELSE greatest(
        high - low,
        abs(high - previous_close),
        abs(low - previous_close)
      )
    END AS true_range
  FROM ordered
), windowed AS (
  SELECT
    *,
    CASE WHEN rn >= ? THEN avg(close) OVER (
      ORDER BY rn ROWS BETWEEN ? PRECEDING AND CURRENT ROW
    ) END AS sma_value,
    avg(gain) OVER (
      ORDER BY rn ROWS BETWEEN ? PRECEDING AND CURRENT ROW
    ) AS average_gain,
    avg(loss) OVER (
      ORDER BY rn ROWS BETWEEN ? PRECEDING AND CURRENT ROW
    ) AS average_loss,
    count(gain) OVER (
      ORDER BY rn ROWS BETWEEN ? PRECEDING AND CURRENT ROW
    ) AS gain_count,
    count(loss) OVER (
      ORDER BY rn ROWS BETWEEN ? PRECEDING AND CURRENT ROW
    ) AS loss_count,
    avg(true_range) OVER (
      ORDER BY rn ROWS BETWEEN ? PRECEDING AND CURRENT ROW
    ) AS atr_raw,
    count(true_range) OVER (
      ORDER BY rn ROWS BETWEEN ? PRECEDING AND CURRENT ROW
    ) AS true_range_count
  FROM changes
), ema_values(rn, ema_value) AS (
  SELECT ?, avg(close)
  FROM ordered
  WHERE rn <= ?
  UNION ALL
  SELECT next_bar.rn,
    ? * next_bar.close + (1 - ?) * ema_values.ema_value
  FROM ema_values
  JOIN ordered AS next_bar ON next_bar.rn = ema_values.rn + 1
), calculated AS (
  SELECT
    windowed.*,
    ema_values.ema_value,
    CASE WHEN gain_count = ? AND loss_count = ? THEN
      CASE
        WHEN average_loss = 0 AND average_gain = 0 THEN 50.0
        WHEN average_loss = 0 THEN 100.0
        ELSE 100.0 - 100.0 / (1.0 + average_gain / average_loss)
      END
    END AS rsi_value,
    CASE WHEN true_range_count = ? THEN atr_raw END AS atr_value
  FROM windowed
  LEFT JOIN ema_values USING (rn)
)
SELECT timestamp, close, sma_value, ema_value, rsi_value, atr_value
FROM calculated
WHERE is_output
ORDER BY rn
LIMIT ?
"""
