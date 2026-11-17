#!/usr/bin/env python3
"""Market data ingestion for NIFTY50 minute bars.

Reads every ``data/raw/*.parquet`` file whose symbol is present in
``data/index/NIFTY50.csv``, validates each row, writes valid rows to
Hive-partitioned Parquet under ``data/processed/`` and rejected rows to
CSV under ``data/rejects/``.

The script is deterministic: identical input produces identical output.
Source files under ``data/raw/`` are never modified or deleted.

Run with::

    python scripts/ingestion.py
"""

from __future__ import annotations

import argparse
import csv
import json
import logging
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

# Reused across files.
import polars as pl
import pyarrow as pa
import pyarrow.parquet as pq

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

PRICE_COLUMNS = ["open", "high", "low", "close"]
OHLCV_COLUMNS = ["open", "high", "low", "close", "volume"]
REQUIRED_COLUMNS = ["date", *OHLCV_COLUMNS]

# NSE equity session boundaries in IST (inclusive): 09:15:00.000 - 15:30:00.000.
IST_SESSION_START_MILLISECONDS = (9 * 3600 + 15 * 60) * 1000
IST_SESSION_END_MILLISECONDS = (15 * 3600 + 30 * 60) * 1000

IST = "Asia/Kolkata"
UTC = "UTC"
INTERVAL = "1m"
INTERVAL_SECONDS = 60

# Inclusive bounds for positive, exactly 13-digit Unix milliseconds.
MIN_EPOCH_MS = 10**12
MAX_EPOCH_MS = 10**13 - 1
MAX_VOLUME = 2**63 - 1

# Deterministic, ordered list of rejection reasons.
REJECT_ORDER = [
    "null_or_nan",
    "non_numeric",
    "non_finite",
    "non_positive_price",
    "negative_volume",
    "non_integral_volume",
    "volume_out_of_range",
    "ohlc_inconsistent",
    "invalid_timestamp",
    "outside_trading_hours",
    "duplicate",
]

PROCESSED_SCHEMA = {
    "symbol": pl.Utf8,
    "timestamp": pl.Datetime(time_unit="us", time_zone=UTC),
    "trading_date": pl.Date,
    "open": pl.Float64,
    "high": pl.Float64,
    "low": pl.Float64,
    "close": pl.Float64,
    "volume": pl.Int64,
}
PROCESSED_ARROW_SCHEMA = pa.schema(
    [
        ("symbol", pa.string()),
        ("timestamp", pa.timestamp("us", tz=UTC)),
        ("trading_date", pa.date32()),
        ("open", pa.float64()),
        ("high", pa.float64()),
        ("low", pa.float64()),
        ("close", pa.float64()),
        ("volume", pa.int64()),
    ]
)

DEFAULTS = {
    "raw_dir": Path("data/raw"),
    "processed_dir": Path("data/processed"),
    "rejects_dir": Path("data/rejects"),
    "index_csv": Path("data/index/NIFTY50.csv"),
}

log = logging.getLogger("ingestion")


# ---------------------------------------------------------------------------
# Result containers
# ---------------------------------------------------------------------------


@dataclass
class FileResult:
    source_file: str
    symbol: str
    status: str  # "processed" | "empty" | "error"
    input_rows: int = 0
    valid_rows: int = 0
    rejected_rows: int = 0
    output_files: int = 0
    output_details: list[dict] = field(default_factory=list)
    error: str | None = None


@dataclass
class Summary:
    files_discovered: int = 0
    files_in_scope: int = 0
    files_out_of_scope: int = 0
    out_of_scope_files: list[str] = field(default_factory=list)
    files_processed: int = 0
    files_empty: int = 0
    files_error: int = 0
    total_input_rows: int = 0
    total_valid_rows: int = 0
    total_rejected_rows: int = 0
    reject_counts: dict[str, int] = field(default_factory=dict)
    files: list[FileResult] = field(default_factory=list)
    # symbol -> gap information
    gaps: dict[str, dict] = field(default_factory=dict)
    output_files: list[dict] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def setup_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)-7s %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S",
        stream=sys.stdout,
    )


def load_scope_symbols(index_csv: Path) -> set[str]:
    """Return the set of NIFTY50 tickers to process."""
    symbols: set[str] = set()
    with index_csv.open(newline="", encoding="utf-8-sig") as fh:
        reader = csv.DictReader(fh)
        if not reader.fieldnames or "Ticker" not in reader.fieldnames:
            raise ValueError(f"index CSV must contain a Ticker column: {index_csv}")
        for row in reader:
            ticker = (row.get("Ticker") or "").strip()
            if ticker:
                symbols.add(ticker)
    if not symbols:
        raise ValueError(f"index CSV contains no tickers: {index_csv}")
    log.info("Loaded %d symbols from %s", len(symbols), index_csv)
    return symbols


def discover_files(
    raw_dir: Path, scope: set[str], candidates: list[Path] | None = None
) -> list[Path]:
    """Return sorted raw parquet files restricted to the scope symbols."""
    raw_files = sorted(
        candidates if candidates is not None else raw_dir.glob("*.parquet")
    )
    files = [p for p in raw_files if p.stem in scope]
    skipped = [p.name for p in raw_files if p.stem not in scope]
    if skipped:
        log.info(
            "Out-of-scope files ignored (%d): %s", len(skipped), ", ".join(skipped)
        )
    log.info(
        "Discovered %d raw Parquet files; %d match the NIFTY50 scope",
        len(raw_files),
        len(files),
    )
    return files


# ---------------------------------------------------------------------------
# Reading
# ---------------------------------------------------------------------------


def validate_raw_schema(schema: pa.Schema) -> None:
    """Raise a clear file-level error for missing or unsupported columns."""
    names = schema.names
    duplicates = sorted({name for name in names if names.count(name) > 1})
    if duplicates:
        raise ValueError(f"duplicate column names: {duplicates}")

    missing = [c for c in REQUIRED_COLUMNS if c not in names]
    if missing:
        raise ValueError(f"missing required columns: {missing}")

    for column in REQUIRED_COLUMNS:
        dtype = schema.field(column).type
        if pa.types.is_null(dtype):
            # All-null columns are still row-readable and can be rejected by
            # value validation rather than losing the whole file.
            continue
        if column == "date":
            supported = (
                pa.types.is_integer(dtype)
                or pa.types.is_floating(dtype)
                or pa.types.is_timestamp(dtype)
                or pa.types.is_string(dtype)
                or pa.types.is_large_string(dtype)
            )
        else:
            supported = (
                pa.types.is_integer(dtype)
                or pa.types.is_floating(dtype)
                or pa.types.is_decimal(dtype)
                or pa.types.is_string(dtype)
                or pa.types.is_large_string(dtype)
            )
        if not supported:
            raise ValueError(f"unsupported type for column {column!r}: {dtype}")


def read_raw(path: Path) -> pl.DataFrame:
    """Read a raw parquet file into a Polars DataFrame.

    Preserves the raw ``date`` values so malformed timestamps can be rejected
    row by row during validation. Raises on unreadable/corrupted files or
    missing required columns so the caller can log a file-level error.
    """
    # Validate readability and schema before loading row groups.
    parquet_file = pq.ParquetFile(path)
    validate_raw_schema(parquet_file.schema_arrow)

    table = pq.read_table(path)

    if table.num_rows == 0:
        # Return an empty frame with the expected shape.
        return pl.DataFrame(
            {"date": pl.Series([], dtype=pl.Int64)}
            | {c: pl.Series([], dtype=pl.Float64) for c in PRICE_COLUMNS}
            | {"volume": pl.Series([], dtype=pl.Int64)}
        )

    # Keep original types and values for row-level validation.
    keep = ["date", *OHLCV_COLUMNS]
    table = table.select(keep)
    date_type = table.schema.field("date").type
    if pa.types.is_timestamp(date_type) and date_type.tz is not None:
        # Polars rejects Arrow's fixed-offset timezone labels such as +05:30.
        # Timestamp values represent instants, so changing the Arrow timezone
        # metadata to UTC preserves the epoch while giving Polars a supported
        # timezone for the later IST conversion.
        date_index = table.schema.get_field_index("date")
        utc_type = pa.timestamp(date_type.unit, tz=UTC)
        table = table.set_column(
            date_index,
            table.schema.field(date_index).with_type(utc_type),
            table.column("date").cast(utc_type),
        )
    return pl.from_arrow(table)


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


def _numeric_series(
    df: pl.DataFrame, col: str
) -> tuple[pl.Series, pl.Series]:
    """Return (float_series, non_numeric_mask) for an OHLCV column.

    ``non_numeric_mask`` flags rows where the original value was present but
    could not be interpreted as a number.
    """
    raw = df.get_column(col)
    original_null = raw.is_null()

    if raw.dtype.is_numeric():
        cast = raw.cast(pl.Float64, strict=False)
        # A numeric column that produced null from a non-null input is
        # treated as non-numeric (e.g. overflow), otherwise fine.
        non_numeric = original_null.not_() & cast.is_null()
    else:
        cast = raw.cast(pl.Float64, strict=False)
        non_numeric = original_null.not_() & cast.is_null()

    return cast, non_numeric


def _build_reason(df: pl.DataFrame, masks: dict[str, pl.Expr]) -> pl.Expr:
    """Combine boolean masks into a deterministic ';'-joined reason string."""
    parts = [
        pl.when(masks[name].fill_null(False))
        .then(pl.lit(name))
        .otherwise(pl.lit(""))
        for name in REJECT_ORDER
    ]
    return (
        pl.concat_str(parts, separator=";")
        .str.replace_all(r";{2,}", ";")
        .str.strip_chars(";")
    )


def _timestamp_epoch_ms(df: pl.DataFrame) -> tuple[pl.Expr, pl.Expr]:
    """Return epoch-millisecond and validity expressions for raw ``date``."""
    value = pl.col("date")
    dtype = df.schema["date"]

    if isinstance(dtype, pl.Datetime):
        epoch_ms = value.dt.epoch("ms")
        if dtype.time_unit == "us":
            exact_millisecond = value.dt.epoch("us") % 1_000 == 0
        elif dtype.time_unit == "ns":
            exact_millisecond = value.dt.epoch("ns") % 1_000_000 == 0
        else:
            exact_millisecond = pl.lit(True)
        valid = (
            value.is_not_null()
            & exact_millisecond
            & (epoch_ms >= MIN_EPOCH_MS)
            & (epoch_ms <= MAX_EPOCH_MS)
        )
        return epoch_ms.cast(pl.Int64, strict=False), valid.fill_null(False)

    if dtype.is_integer():
        epoch_ms = value.cast(pl.Int64, strict=False)
        valid = (epoch_ms >= MIN_EPOCH_MS) & (epoch_ms <= MAX_EPOCH_MS)
        return epoch_ms, valid.fill_null(False)

    if dtype.is_float():
        numeric = value.cast(pl.Float64, strict=False)
        epoch_ms = numeric.cast(pl.Int64, strict=False)
        valid = (
            numeric.is_finite()
            & (numeric.floor() == numeric)
            & (epoch_ms >= MIN_EPOCH_MS)
            & (epoch_ms <= MAX_EPOCH_MS)
        )
        return epoch_ms, valid.fill_null(False)

    if dtype == pl.String:
        has_13_digits = value.str.contains(r"^[0-9]{13}$").fill_null(False)
        epoch_ms = value.cast(pl.Int64, strict=False)
        valid = has_13_digits & (epoch_ms >= MIN_EPOCH_MS) & (epoch_ms <= MAX_EPOCH_MS)
        return epoch_ms, valid.fill_null(False)

    # Null-typed columns and unsupported in-memory inputs are invalid per row.
    return pl.lit(None, dtype=pl.Int64), pl.lit(False)


def validate(
    df: pl.DataFrame, symbol: str, source_file: str
) -> tuple[pl.DataFrame, pl.DataFrame, dict]:
    """Validate rows.

    Returns ``(valid, rejects, gap_info)`` where ``valid`` uses the processed
    schema and ``rejects`` is a CSV-ready frame (original values + reason).
    """
    n = df.height

    # Preserve original row order for determinism / traceability.
    df = df.with_row_index("_row", offset=1)

    # --- Numeric coercion -------------------------------------------------
    cast_cols: dict[str, pl.Series] = {}
    non_numeric_any = pl.Series([False] * n)
    for col in OHLCV_COLUMNS:
        cast, non_numeric = _numeric_series(df, col)
        cast_cols[col] = cast
        non_numeric_any = non_numeric_any | non_numeric

    work = df
    for col in OHLCV_COLUMNS:
        work = work.with_columns(cast_cols[col].alias(f"_{col}"))

    # --- Timestamp handling (UTC -> IST) ----------------------------------
    # Materialise non-numeric mask as a column.
    work = work.with_columns(non_numeric_any.alias("_non_numeric"))

    epoch_expr, timestamp_valid = _timestamp_epoch_ms(work)
    work = work.with_columns(
        [epoch_expr.alias("_epoch_ms"), timestamp_valid.alias("_valid_timestamp")]
    )
    work = work.with_columns(
        pl.from_epoch(pl.col("_epoch_ms"), time_unit="ms")
        .dt.replace_time_zone(UTC)
        .alias("timestamp")
    )
    work = work.with_columns(
        pl.col("timestamp").dt.convert_time_zone(IST).alias("_ist")
    )

    invalid_ts = ~pl.col("_valid_timestamp")

    # --- Trading-hours check (IST clock time) -----------------------------
    ist = pl.col("_ist")
    milliseconds_since_midnight = (
        ist.dt.hour().cast(pl.Int32) * 3_600_000
        + ist.dt.minute().cast(pl.Int32) * 60_000
        + ist.dt.second().cast(pl.Int32) * 1_000
        + ist.dt.millisecond().cast(pl.Int32)
    )
    outside_hours = pl.col("_valid_timestamp") & ~(
        (milliseconds_since_midnight >= IST_SESSION_START_MILLISECONDS)
        & (milliseconds_since_midnight <= IST_SESSION_END_MILLISECONDS)
    )

    # --- Masks ------------------------------------------------------------
    null_cols = [pl.col("date").is_null(), *[pl.col(c).is_null() for c in OHLCV_COLUMNS]]
    nan_cols = [pl.col(f"_{c}").is_nan() for c in OHLCV_COLUMNS]
    if df.schema["date"].is_float():
        nan_cols.append(pl.col("date").is_nan())
    null_or_nan = pl.any_horizontal([*null_cols, *nan_cols])

    non_finite = pl.any_horizontal(
        [pl.col(f"_{c}").is_infinite() for c in OHLCV_COLUMNS]
    )

    non_positive = pl.any_horizontal(
        [pl.col(f"_{c}") <= 0 for c in PRICE_COLUMNS]
    )

    volume = pl.col("_volume")
    negative_volume = volume < 0
    non_integral_volume = (
        volume.is_finite() & (volume.floor() != volume)
    )
    volume_i64 = volume.cast(pl.Int64, strict=False)
    if df.schema["volume"].is_unsigned_integer():
        volume_out_of_range = pl.col("volume") > pl.lit(MAX_VOLUME, dtype=pl.UInt64)
    elif df.schema["volume"].is_integer():
        volume_out_of_range = pl.lit(False)
    else:
        volume_out_of_range = (
            volume.is_finite()
            & (volume.floor() == volume)
            & volume_i64.is_null()
        )

    o = pl.col("_open")
    h = pl.col("_high")
    low = pl.col("_low")
    c = pl.col("_close")
    ohlc_bad = (
        (h < pl.max_horizontal(o, c))
        | (low > pl.min_horizontal(o, c))
        | (h < low)
    )

    duplicate = pl.col("_valid_timestamp") & ~pl.col("_epoch_ms").is_first_distinct()

    masks = {
        "null_or_nan": null_or_nan,
        "non_numeric": pl.col("_non_numeric"),
        "non_finite": non_finite,
        "non_positive_price": non_positive,
        "negative_volume": negative_volume,
        "non_integral_volume": non_integral_volume,
        "volume_out_of_range": volume_out_of_range,
        "ohlc_inconsistent": ohlc_bad,
        "invalid_timestamp": invalid_ts,
        "outside_trading_hours": outside_hours,
        "duplicate": duplicate,
    }

    reason_expr = _build_reason(work, masks)
    reject_mask = pl.any_horizontal([m.fill_null(False) for m in masks.values()])

    work = work.with_columns(
        [
            reason_expr.alias("reject_reason"),
            reject_mask.alias("_reject"),
            pl.col("_ist").dt.date().alias("trading_date"),
        ]
    )

    valid = work.filter(~pl.col("_reject"))
    rejects = work.filter(pl.col("_reject"))

    # --- Build processed frame -------------------------------------------
    valid_proc = valid.select(
        [
            pl.lit(symbol).alias("symbol"),
            pl.col("timestamp").cast(PROCESSED_SCHEMA["timestamp"]),
            pl.col("trading_date"),
            pl.col("_open").cast(pl.Float64).alias("open"),
            pl.col("_high").cast(pl.Float64).alias("high"),
            pl.col("_low").cast(pl.Float64).alias("low"),
            pl.col("_close").cast(pl.Float64).alias("close"),
            (
                pl.col("volume").cast(pl.Int64, strict=False)
                if df.schema["volume"].is_integer()
                else volume_i64
            ).alias("volume"),
        ]
    )

    # --- Build rejects frame (original values + reason) ------------------
    rejects_out = rejects.select(
        [
            pl.lit(source_file).alias("source_file"),
            pl.lit(symbol).alias("symbol"),
            pl.col("_row").alias("row_number"),
            pl.col("date").cast(pl.Utf8).alias("date_raw"),
            pl.col("open"),
            pl.col("high"),
            pl.col("low"),
            pl.col("close"),
            pl.col("volume"),
            pl.col("reject_reason"),
        ]
    )

    gap_info = compute_gaps(valid_proc, symbol)
    return valid_proc, rejects_out, gap_info


# ---------------------------------------------------------------------------
# Chronological integrity
# ---------------------------------------------------------------------------


def compute_gaps(valid: pl.DataFrame, symbol: str) -> dict:
    """Report intraday missing minutes and source-order anomalies.

    Bars are compared only within the same IST trading date. This skips the
    non-trading periods between sessions, including weekends and exchange
    holidays, without treating them as missing minute bars.
    """
    info = {
        "symbol": symbol,
        "valid_rows": valid.height,
        "gap_events": 0,
        "missing_intraday_intervals": 0,
        "dates_with_gaps": 0,
        "out_of_order_rows": 0,
        "weekend_rows": 0,
        "gap_details": [],
        "gap_details_truncated": False,
    }
    if valid.is_empty():
        return info

    df = valid.with_columns(
        pl.col("timestamp").dt.convert_time_zone(IST).alias("_ist")
    )
    ist = df.get_column("_ist")
    # Weekend rows (Saturday=5, Sunday=6 in Polars weekday ISO Mon=1..Sun=7).
    weekday = ist.dt.weekday()
    info["weekend_rows"] = int((weekday >= 6).sum())
    if valid.height < 2:
        return info

    # Count a source row as out of order when it follows a later timestamp.
    source_epoch = ist.dt.epoch("ms")
    info["out_of_order_rows"] = int(
        (source_epoch.diff().drop_nulls() < 0).sum()
    )

    # Use IST timestamps for ordering and local-date comparisons. A date change
    # crosses a closed market session, so gaps are measured within each date.
    df = df.sort("_ist")
    ist = df.get_column("_ist")
    epoch = ist.dt.epoch("ms")
    diffs = epoch.diff().drop_nulls()
    dates = ist.dt.date()
    same_day = (dates == dates.shift(1)).slice(1).fill_null(False)
    gap_mask = (diffs > INTERVAL_SECONDS * 1000) & same_day
    gap_indices = [i + 1 for i, is_gap in enumerate(gap_mask.to_list()) if is_gap]

    info["gap_events"] = len(gap_indices)
    if gap_indices:
        gap_diffs = diffs.filter(gap_mask)
        # Count expected one-minute timestamps absent between each pair, also
        # handling unexpected non-minute-aligned gaps deterministically.
        info["missing_intraday_intervals"] = int(
            ((gap_diffs - 1) // (INTERVAL_SECONDS * 1000)).sum()
        )
        gap_dates = [dates[i] for i in gap_indices]
        info["dates_with_gaps"] = len(set(gap_dates))
        info["gap_date_examples"] = sorted({str(day) for day in gap_dates[:20]})

        gap_details = []
        for i in gap_indices[:100]:
            delta_ms = epoch[i] - epoch[i - 1]
            gap_details.append(
                {
                    "trading_date": str(dates[i]),
                    "from_ist": ist[i - 1].isoformat(),
                    "to_ist": ist[i].isoformat(),
                    "missing_intervals": (delta_ms - 1)
                    // (INTERVAL_SECONDS * 1000),
                }
            )
        info["gap_details"] = gap_details
        info["gap_details_truncated"] = len(gap_indices) > len(gap_details)

    return info


# ---------------------------------------------------------------------------
# Writing
# ---------------------------------------------------------------------------


def write_processed(
    valid: pl.DataFrame, symbol: str, processed_dir: Path
) -> list[dict]:
    """Write one schema-stable Parquet file per populated Hive partition.

    Rows are grouped before writing, so multiple bars for one partition share
    one object instead of producing a small file per row. Re-running with the
    same input deterministically replaces each partition's ``part.parquet``.
    Return portable relative paths and row counts for the run summary.
    """
    if valid.height == 0:
        return []

    df = valid.with_columns(
        [
            pl.lit(symbol).alias("symbol"),
            pl.lit(INTERVAL).alias("interval"),
            pl.col("trading_date").dt.year().alias("year"),
            pl.col("trading_date").dt.month().alias("month"),
        ]
    )

    part_cols = ["interval", "year", "month", "symbol"]
    partitions = df.partition_by(
        part_cols, as_dict=True, include_key=True, maintain_order=True
    )

    output_details = []
    for key, part in sorted(partitions.items(), key=lambda item: item[0]):
        interval, year, month, sym = key
        out_dir = (
            processed_dir
            / f"interval={interval}"
            / f"year={year}"
            / f"month={month:02d}"
            / f"symbol={sym}"
        )
        out_dir.mkdir(parents=True, exist_ok=True)
        out_path = out_dir / "part.parquet"
        part = part.select(list(PROCESSED_SCHEMA.keys())).sort(
            "timestamp", maintain_order=True
        )
        part = part.cast(PROCESSED_SCHEMA)
        arrow_part = part.to_arrow().cast(PROCESSED_ARROW_SCHEMA)
        pq.write_table(
            arrow_part,
            out_path,
            compression="zstd",
            compression_level=3,
            write_statistics=True,
        )
        output_details.append(
            {"path": out_path.relative_to(processed_dir).as_posix(), "rows": part.height}
        )

    return output_details


def write_rejects(rejects: pl.DataFrame, symbol: str, rejects_dir: Path) -> None:
    """Write rejected rows to ``<symbol>.csv`` if any."""
    out_path = rejects_dir / f"{symbol}.csv"
    if rejects.height == 0:
        out_path.unlink(missing_ok=True)
        return
    rejects_dir.mkdir(parents=True, exist_ok=True)
    rejects.write_csv(out_path)


def append_file_errors(path: Path, lines: list[str]) -> None:
    if not lines:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8", newline="\n") as fh:
        for line in lines:
            fh.write(line + "\n")


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------


def process_file(path: Path, processed_dir: Path, rejects_dir: Path) -> FileResult:
    symbol = path.stem
    result = FileResult(source_file=path.name, symbol=symbol, status="error")
    try:
        df = read_raw(path)
    except Exception as exc:  # noqa: BLE001 - file-level error handling
        result.error = f"{type(exc).__name__}: {exc}"
        log.error("FILE ERROR %s: %s", path.name, result.error)
        return result

    result.input_rows = df.height
    if df.height == 0:
        result.status = "empty"
        log.warning("EMPTY FILE %s", path.name)
        return result

    try:
        valid, rejects, gap_info = validate(df, symbol, path.name)
    except Exception as exc:  # noqa: BLE001 - file-level error handling
        result.error = f"{type(exc).__name__}: {exc}"
        log.error("VALIDATION ERROR %s: %s", path.name, result.error)
        return result

    # Reject counts by category (a row may count under several categories).
    if rejects.height:
        counts: dict[str, int] = {}
        for reason in rejects.get_column("reject_reason").to_list():
            for token in reason.split(";"):
                if token:
                    counts[token] = counts.get(token, 0) + 1
        result._reject_counts = counts  # type: ignore[attr-defined]

    result.valid_rows = valid.height
    result.rejected_rows = rejects.height

    try:
        result.output_details = write_processed(valid, symbol, processed_dir)
        result.output_files = len(result.output_details)
        write_rejects(rejects, symbol, rejects_dir)
    except Exception as exc:  # noqa: BLE001 - output error handling
        result.error = f"{type(exc).__name__}: {exc}"
        log.error("WRITE ERROR %s: %s", path.name, result.error)
        return result

    result.status = "processed"
    # Attach gap info for the summary.
    result._gap_info = gap_info  # type: ignore[attr-defined]

    log.info(
        "PROCESSED %s: in=%d valid=%d rejected=%d files=%d",
        path.name,
        result.input_rows,
        result.valid_rows,
        result.rejected_rows,
        result.output_files,
    )
    return result


def run(args: argparse.Namespace) -> Summary:
    raw_dir = Path(args.raw_dir)
    processed_dir = Path(args.processed_dir)
    rejects_dir = Path(args.rejects_dir)
    index_csv = Path(args.index_csv)

    processed_dir.mkdir(parents=True, exist_ok=True)
    rejects_dir.mkdir(parents=True, exist_ok=True)

    scope = load_scope_symbols(index_csv)
    raw_files = sorted(raw_dir.glob("*.parquet"))
    files = discover_files(raw_dir, scope, raw_files)
    out_of_scope = [p.name for p in raw_files if p.stem not in scope]
    summary = Summary(
        files_discovered=len(raw_files),
        files_in_scope=len(files),
        files_out_of_scope=len(out_of_scope),
        out_of_scope_files=out_of_scope,
    )

    file_error_log = rejects_dir / "file_errors.log"
    # Each run owns a fresh deterministic error log; prior-run errors must not
    # accumulate or make identical ingestions produce different artifacts.
    with file_error_log.open("w", encoding="utf-8", newline="\n"):
        pass
    for path in files:
        result = process_file(path, processed_dir, rejects_dir)
        summary.files.append(result)
        summary.total_input_rows += result.input_rows
        summary.total_valid_rows += result.valid_rows
        summary.total_rejected_rows += result.rejected_rows

        if result.status == "processed":
            summary.files_processed += 1
            counts = getattr(result, "_reject_counts", {})
            for reason, cnt in counts.items():
                summary.reject_counts[reason] = (
                    summary.reject_counts.get(reason, 0) + cnt
                )
            gap_info = getattr(result, "_gap_info", None)
            if gap_info and (
                gap_info["gap_events"]
                or gap_info["out_of_order_rows"]
                or gap_info["weekend_rows"]
            ):
                summary.gaps[result.symbol] = gap_info
            summary.output_files.extend(
                {"symbol": result.symbol, **detail}
                for detail in result.output_details
            )
        elif result.status == "empty":
            summary.files_empty += 1
        else:
            summary.files_error += 1
            append_file_errors(
                file_error_log,
                [f"{result.source_file}\t{result.error}"],
            )

    return summary


def print_summary(summary: Summary, duration: float) -> None:
    out = {
        "duration_seconds": round(duration, 2),
        "files_discovered": summary.files_discovered,
        "files_in_scope": summary.files_in_scope,
        "files_out_of_scope": summary.files_out_of_scope,
        "out_of_scope_files": summary.out_of_scope_files,
        "files_processed": summary.files_processed,
        "files_empty": summary.files_empty,
        "files_error": summary.files_error,
        "total_input_rows": summary.total_input_rows,
        "total_valid_rows": summary.total_valid_rows,
        "total_rejected_rows": summary.total_rejected_rows,
        "file_results": [
            {
                "source_file": result.source_file,
                "symbol": result.symbol,
                "status": result.status,
                "input_rows": result.input_rows,
                "valid_rows": result.valid_rows,
                "rejected_rows": result.rejected_rows,
                "output_files": result.output_files,
                "error": result.error,
            }
            for result in summary.files
        ],
        "reject_counts_by_category": dict(
            sorted(summary.reject_counts.items())
        ),
        "symbols_with_gaps": len(summary.gaps),
        "gap_details": summary.gaps,
        "output_files": summary.output_files,
    }
    log.info("=" * 60)
    log.info("INGESTION SUMMARY")
    log.info("=" * 60)
    print(json.dumps(out, indent=2, default=str))


def parse_args(argv: list[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Validate and process NIFTY50 raw parquet data.")
    p.add_argument("--raw-dir", default=str(DEFAULTS["raw_dir"]))
    p.add_argument("--processed-dir", default=str(DEFAULTS["processed_dir"]))
    p.add_argument("--rejects-dir", default=str(DEFAULTS["rejects_dir"]))
    p.add_argument("--index-csv", default=str(DEFAULTS["index_csv"]))
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    setup_logging()
    args = parse_args(argv if argv is not None else sys.argv[1:])
    start = time.perf_counter()
    summary = run(args)
    duration = time.perf_counter() - start
    print_summary(summary, duration)
    return 0 if summary.files_error == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
