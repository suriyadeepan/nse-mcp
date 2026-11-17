"""Tests for ingestion input scoping and per-file Parquet handling."""

from datetime import date, datetime, timezone
import csv
import json
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pyarrow as pa
import pyarrow.parquet as pq
import polars as pl
import pytest

from scripts import ingestion


TIMESTAMP_MS = int(
    datetime(2024, 1, 2, 3, 45, tzinfo=timezone.utc).timestamp() * 1000
)


def write_bar(path: Path) -> None:
    pq.write_table(
        pa.table(
            {
                "date": pa.array([TIMESTAMP_MS], type=pa.int64()),
                "open": pa.array([100.0]),
                "high": pa.array([101.0]),
                "low": pa.array([99.0]),
                "close": pa.array([100.5]),
                "volume": pa.array([500], type=pa.int64()),
            }
        ),
        path,
    )


def write_rows_with_dates(path: Path, dates: pa.Array) -> None:
    row_count = len(dates)
    pq.write_table(
        pa.table(
            {
                "date": dates,
                "open": pa.array([100.0] * row_count),
                "high": pa.array([101.0] * row_count),
                "low": pa.array([99.0] * row_count),
                "close": pa.array([100.5] * row_count),
                "volume": pa.array([500] * row_count, type=pa.int64()),
            }
        ),
        path,
    )


def test_scope_uses_ticker_column_and_exact_parquet_stems(tmp_path):
    index_csv = tmp_path / "NIFTY50.csv"
    index_csv.write_text("Company,Ticker\nIssuer, ABC \nIssuer,ABC\nIssuer,XYZ\n")
    raw_dir = tmp_path / "raw"
    raw_dir.mkdir()
    candidates = [
        raw_dir / "ABC.parquet",
        raw_dir / "ABCD.parquet",
        raw_dir / "XYZ.parquet",
        raw_dir / "ABC.parquets",
    ]
    for path in candidates:
        path.touch()

    scope = ingestion.load_scope_symbols(index_csv)
    files = ingestion.discover_files(raw_dir, scope)

    assert scope == {"ABC", "XYZ"}
    assert [path.name for path in files] == ["ABC.parquet", "XYZ.parquet"]


def test_scope_csv_requires_ticker_column_and_symbols(tmp_path):
    index_csv = tmp_path / "NIFTY50.csv"
    index_csv.write_text("Symbol\nABC\n")
    with pytest.raises(ValueError, match="Ticker column"):
        ingestion.load_scope_symbols(index_csv)

    index_csv.write_text("Ticker\n , \n")
    with pytest.raises(ValueError, match="no tickers"):
        ingestion.load_scope_symbols(index_csv)


def test_read_raw_accepts_empty_file_with_expected_schema(tmp_path):
    path = tmp_path / "EMPTY.parquet"
    pq.write_table(
        pa.table(
            {
                "date": pa.array([], type=pa.int64()),
                "open": pa.array([], type=pa.float64()),
                "high": pa.array([], type=pa.float64()),
                "low": pa.array([], type=pa.float64()),
                "close": pa.array([], type=pa.float64()),
                "volume": pa.array([], type=pa.int64()),
            }
        ),
        path,
    )

    result = ingestion.read_raw(path)

    assert result.is_empty()
    assert result.columns == ingestion.REQUIRED_COLUMNS


def test_read_raw_rejects_missing_columns_and_unsupported_types(tmp_path):
    missing_path = tmp_path / "MISSING.parquet"
    pq.write_table(
        pa.table(
            {
                "date": pa.array([TIMESTAMP_MS]),
                "open": pa.array([1.0]),
                "high": pa.array([1.0]),
                "low": pa.array([1.0]),
                "close": pa.array([1.0]),
            }
        ),
        missing_path,
    )

    bad_type_path = tmp_path / "BADTYPE.parquet"
    schema = pa.schema(
        [
            ("date", pa.int64()),
            ("open", pa.list_(pa.int64())),
            ("high", pa.float64()),
            ("low", pa.float64()),
            ("close", pa.float64()),
            ("volume", pa.int64()),
        ]
    )
    pq.write_table(
        pa.Table.from_arrays(
            [
                pa.array([TIMESTAMP_MS], type=pa.int64()),
                pa.array([[1]], type=pa.list_(pa.int64())),
                pa.array([1.0]),
                pa.array([1.0]),
                pa.array([1.0]),
                pa.array([1], type=pa.int64()),
            ],
            schema=schema,
        ),
        bad_type_path,
    )

    with pytest.raises(ValueError, match="missing required columns"):
        ingestion.read_raw(missing_path)
    with pytest.raises(ValueError, match="unsupported type for column 'open'"):
        ingestion.read_raw(bad_type_path)


def test_timestamp_is_utc_aware_and_trading_date_uses_ist(tmp_path):
    path = tmp_path / "TIMESTAMP.parquet"
    write_bar(path)

    valid, rejects, _ = ingestion.validate(
        ingestion.read_raw(path), "TIMESTAMP", path.name
    )

    assert rejects.is_empty()
    assert valid.get_column("timestamp").dtype.time_zone == "UTC"
    assert valid.get_column("timestamp").to_list() == [
        datetime(2024, 1, 2, 3, 45, tzinfo=timezone.utc)
    ]
    assert valid.get_column("trading_date").to_list() == [date(2024, 1, 2)]


def test_nse_session_bounds_are_checked_in_ist_to_millisecond_precision():
    ist = ZoneInfo("Asia/Kolkata")
    local_times = [
        datetime(2024, 1, 2, 9, 14, 59, 999_000, tzinfo=ist),
        datetime(2024, 1, 2, 9, 15, tzinfo=ist),
        datetime(2024, 1, 2, 15, 30, tzinfo=ist),
        datetime(2024, 1, 2, 15, 30, 0, 1_000, tzinfo=ist),
    ]
    epoch_ms = [int(value.timestamp() * 1000) for value in local_times]
    df = pl.DataFrame(
        {
            "date": epoch_ms,
            "open": [100.0] * 4,
            "high": [101.0] * 4,
            "low": [99.0] * 4,
            "close": [100.5] * 4,
            "volume": [1] * 4,
        }
    )

    valid, rejects, _ = ingestion.validate(df, "SESSION", "SESSION.parquet")

    assert valid.get_column("timestamp").to_list() == [
        datetime(2024, 1, 2, 3, 45, tzinfo=timezone.utc),
        datetime(2024, 1, 2, 10, 0, tzinfo=timezone.utc),
    ]
    assert valid.get_column("trading_date").to_list() == [date(2024, 1, 2)] * 2
    assert rejects.get_column("reject_reason").to_list() == [
        "outside_trading_hours",
        "outside_trading_hours",
    ]


def test_weekend_date_extraction_uses_ist_calendar_day():
    # Friday 18:45 UTC is Saturday 00:15 in India.
    friday_utc = datetime(2024, 1, 5, 18, 45, tzinfo=timezone.utc)
    valid = pl.DataFrame(
        {
            "timestamp": [
                friday_utc,
                datetime(2024, 1, 5, 18, 46, tzinfo=timezone.utc),
            ],
        },
        schema={"timestamp": pl.Datetime(time_unit="us", time_zone="UTC")},
    )

    gap_info = ingestion.compute_gaps(valid, "WEEKEND")

    assert gap_info["weekend_rows"] == 2


def test_compute_gaps_reports_intraday_missing_intervals_and_details():
    ist = ZoneInfo("Asia/Kolkata")
    local_times = [
        datetime(2024, 1, 2, 9, 15, tzinfo=ist),
        datetime(2024, 1, 2, 9, 18, tzinfo=ist),
    ]
    valid = pl.DataFrame(
        {
            "timestamp": [value.astimezone(timezone.utc) for value in local_times],
        },
        schema={"timestamp": pl.Datetime(time_unit="us", time_zone="UTC")},
    )

    gap_info = ingestion.compute_gaps(valid, "GAP")

    assert gap_info["gap_events"] == 1
    assert gap_info["missing_intraday_intervals"] == 2
    assert gap_info["dates_with_gaps"] == 1
    assert gap_info["gap_details"] == [
        {
            "trading_date": "2024-01-02",
            "from_ist": "2024-01-02T09:15:00+05:30",
            "to_ist": "2024-01-02T09:18:00+05:30",
            "missing_intervals": 2,
        }
    ]
    assert not gap_info["gap_details_truncated"]


def test_compute_gaps_skips_overnight_weekends_and_nse_holidays():
    ist = ZoneInfo("Asia/Kolkata")
    # October 2, 2024 was an NSE trading holiday. Date changes close the
    # session comparison, so neither that holiday nor the weekend is a gap.
    local_times = [
        datetime(2024, 10, 1, 15, 29, tzinfo=ist),
        datetime(2024, 10, 3, 9, 15, tzinfo=ist),
        datetime(2024, 10, 4, 9, 15, tzinfo=ist),
        datetime(2024, 10, 5, 9, 15, tzinfo=ist),
        datetime(2024, 10, 7, 9, 15, tzinfo=ist),
    ]
    valid = pl.DataFrame(
        {
            "timestamp": [value.astimezone(timezone.utc) for value in local_times],
        },
        schema={"timestamp": pl.Datetime(time_unit="us", time_zone="UTC")},
    )

    gap_info = ingestion.compute_gaps(valid, "CLOSED_DAYS")

    assert gap_info["gap_events"] == 0
    assert gap_info["missing_intraday_intervals"] == 0
    assert gap_info["gap_details"] == []
    assert gap_info["weekend_rows"] == 1


def test_compute_gaps_counts_out_of_order_rows_in_source_order():
    ist = ZoneInfo("Asia/Kolkata")
    local_times = [
        datetime(2024, 1, 2, 9, 15, tzinfo=ist),
        datetime(2024, 1, 2, 9, 17, tzinfo=ist),
        datetime(2024, 1, 2, 9, 16, tzinfo=ist),
        datetime(2024, 1, 2, 9, 18, tzinfo=ist),
    ]
    valid = pl.DataFrame(
        {
            "timestamp": [value.astimezone(timezone.utc) for value in local_times],
        },
        schema={"timestamp": pl.Datetime(time_unit="us", time_zone="UTC")},
    )

    gap_info = ingestion.compute_gaps(valid, "OUT_OF_ORDER")

    assert gap_info["out_of_order_rows"] == 1
    assert gap_info["gap_events"] == 0


def test_string_dates_require_13_digits_and_reject_null_or_malformed_rows(tmp_path):
    path = tmp_path / "STRING_DATES.parquet"
    write_rows_with_dates(
        path,
        pa.array(
            ["1704167100000", "17041671000", "17041671000000", "bad", None],
            type=pa.string(),
        ),
    )

    valid, rejects, _ = ingestion.validate(
        ingestion.read_raw(path), "STRING_DATES", path.name
    )

    assert valid.height == 1
    assert rejects.get_column("reject_reason").to_list() == [
        "invalid_timestamp",
        "invalid_timestamp",
        "invalid_timestamp",
        "null_or_nan;invalid_timestamp",
    ]
    assert rejects.get_column("date_raw").to_list() == [
        "17041671000",
        "17041671000000",
        "bad",
        None,
    ]


def test_float_dates_must_be_finite_and_integral_milliseconds(tmp_path):
    path = tmp_path / "FLOAT_DATES.parquet"
    write_rows_with_dates(
        path,
        pa.array(
            [float(TIMESTAMP_MS), float(TIMESTAMP_MS) + 0.5, float("nan"), float("inf")],
            type=pa.float64(),
        ),
    )

    valid, rejects, _ = ingestion.validate(
        ingestion.read_raw(path), "FLOAT_DATES", path.name
    )

    assert valid.height == 1
    assert rejects.height == 3
    assert rejects.get_column("reject_reason").to_list() == [
        "invalid_timestamp",
        "null_or_nan;invalid_timestamp",
        "invalid_timestamp",
    ]


def test_timestamp_typed_dates_reject_submillisecond_values(tmp_path):
    path = tmp_path / "ARROW_TIMESTAMPS.parquet"
    write_rows_with_dates(
        path,
        pa.array(
            [
                datetime(2024, 1, 2, 3, 45, tzinfo=timezone.utc),
                datetime(2024, 1, 2, 3, 45, 0, 500, tzinfo=timezone.utc),
            ],
            type=pa.timestamp("us", tz="UTC"),
        ),
    )

    valid, rejects, _ = ingestion.validate(
        ingestion.read_raw(path), "ARROW_TIMESTAMPS", path.name
    )

    assert valid.height == 1
    assert valid.get_column("timestamp").dtype.time_zone == "UTC"
    assert rejects.get_column("reject_reason").to_list() == ["invalid_timestamp"]


def test_fixed_offset_timestamp_timezone_is_normalized_before_polars_read(tmp_path):
    path = tmp_path / "FIXED_OFFSET.parquet"
    write_rows_with_dates(
        path,
        pa.array(
            [datetime(2024, 1, 2, 3, 45, tzinfo=timezone.utc)],
            type=pa.timestamp("ms", tz="+05:30"),
        ),
    )

    raw = ingestion.read_raw(path)
    valid, rejects, _ = ingestion.validate(raw, "FIXED_OFFSET", path.name)

    assert raw.get_column("date").dtype.time_zone == "UTC"
    assert rejects.is_empty()
    assert valid.get_column("timestamp").to_list() == [
        datetime(2024, 1, 2, 3, 45, tzinfo=timezone.utc)
    ]
    assert valid.get_column("trading_date").to_list() == [date(2024, 1, 2)]


def test_ohlcv_validation_rejects_invalid_values_and_all_applicable_reasons(tmp_path):
    path = tmp_path / "INVALID_OHLCV.parquet"
    defaults = {
        "open": "100",
        "high": "101",
        "low": "99",
        "close": "100.5",
        "volume": "0",
    }
    cases = [
        ("valid_zero_volume", {}),
        ("null_price", {"open": None}),
        ("nan_price", {"high": "nan"}),
        ("infinite_price", {"low": "-inf"}),
        ("non_numeric_price", {"open": "bad"}),
        ("zero_price", {"low": "0"}),
        ("negative_price", {"open": "-1", "low": "-2"}),
        ("negative_volume", {"volume": "-1"}),
        ("infinite_volume", {"volume": "inf"}),
        ("negative_infinite_volume", {"volume": "-inf"}),
        ("nan_volume", {"volume": "nan"}),
        ("non_numeric_volume", {"volume": "bad"}),
        ("null_volume", {"volume": None}),
        ("fractional_volume", {"volume": "1.5"}),
        ("volume_out_of_range", {"volume": "9223372036854775808"}),
        ("high_below_open", {"high": "99"}),
        ("low_above_close", {"high": "102", "low": "101"}),
        ("close_above_high", {"close": "inf"}),
    ]
    rows = []
    for offset, (name, changes) in enumerate(cases):
        row = defaults | changes
        row["date"] = TIMESTAMP_MS + offset * 60_000
        rows.append((name, row))

    pq.write_table(
        pa.table(
            {
                "date": pa.array([row["date"] for _, row in rows], type=pa.int64()),
                **{
                    column: pa.array(
                        [row[column] for _, row in rows], type=pa.string()
                    )
                    for column in ingestion.OHLCV_COLUMNS
                },
            }
        ),
        path,
    )

    valid, rejects, _ = ingestion.validate(
        ingestion.read_raw(path), "INVALID_OHLCV", path.name
    )
    reasons_by_row = dict(
        zip(
            rejects.get_column("row_number").to_list(),
            rejects.get_column("reject_reason").to_list(),
        )
    )
    row_numbers = {name: i + 1 for i, (name, _) in enumerate(rows)}

    assert valid.height == 1
    assert valid.get_column("volume").to_list() == [0]
    assert "null_or_nan" in reasons_by_row[row_numbers["null_price"]]
    assert "null_or_nan" in reasons_by_row[row_numbers["nan_price"]]
    assert "non_finite" in reasons_by_row[row_numbers["infinite_price"]]
    assert "non_numeric" in reasons_by_row[row_numbers["non_numeric_price"]]
    assert "non_positive_price" in reasons_by_row[row_numbers["zero_price"]]
    assert "non_positive_price" in reasons_by_row[row_numbers["negative_price"]]
    assert "negative_volume" in reasons_by_row[row_numbers["negative_volume"]]
    assert "non_finite" in reasons_by_row[row_numbers["infinite_volume"]]
    assert reasons_by_row[row_numbers["negative_infinite_volume"]] == (
        "non_finite;negative_volume"
    )
    assert "null_or_nan" in reasons_by_row[row_numbers["nan_volume"]]
    assert "non_numeric" in reasons_by_row[row_numbers["non_numeric_volume"]]
    assert "null_or_nan" in reasons_by_row[row_numbers["null_volume"]]
    assert "non_integral_volume" in reasons_by_row[row_numbers["fractional_volume"]]
    assert "volume_out_of_range" in reasons_by_row[
        row_numbers["volume_out_of_range"]
    ]
    assert "ohlc_inconsistent" in reasons_by_row[row_numbers["high_below_open"]]
    assert "ohlc_inconsistent" in reasons_by_row[row_numbers["low_above_close"]]
    assert reasons_by_row[row_numbers["close_above_high"]] == (
        "non_finite;ohlc_inconsistent"
    )


def test_ohlc_consistency_checks_all_three_bounds(tmp_path):
    path = tmp_path / "BAD_OHLC.parquet"
    cases = [
        {"open": 100.0, "high": 99.0, "low": 98.0, "close": 100.5},
        {"open": 100.0, "high": 102.0, "low": 101.0, "close": 100.5},
        {"open": 100.0, "high": 99.0, "low": 101.0, "close": 100.5},
    ]
    pq.write_table(
        pa.table(
            {
                "date": pa.array(
                    [TIMESTAMP_MS + i * 60_000 for i in range(len(cases))],
                    type=pa.int64(),
                ),
                **{
                    column: pa.array([row[column] for row in cases])
                    for column in ingestion.PRICE_COLUMNS
                },
                "volume": pa.array([1, 1, 1], type=pa.int64()),
            }
        ),
        path,
    )

    valid, rejects, _ = ingestion.validate(
        ingestion.read_raw(path), "BAD_OHLC", path.name
    )

    assert valid.is_empty()
    assert rejects.get_column("reject_reason").to_list() == [
        "ohlc_inconsistent",
        "ohlc_inconsistent",
        "ohlc_inconsistent",
    ]


def test_duplicate_timestamps_keep_first_occurrence_per_file(tmp_path):
    first_path = tmp_path / "FIRST.parquet"
    timestamp = TIMESTAMP_MS
    pq.write_table(
        pa.table(
            {
                "date": pa.array(
                    [timestamp, timestamp, timestamp + 60_000, timestamp + 60_000],
                    type=pa.int64(),
                ),
                "open": pa.array([100.0] * 4),
                "high": pa.array([101.0] * 4),
                "low": pa.array([99.0] * 4),
                "close": pa.array([100.5] * 4),
                "volume": pa.array([10, 20, 30, 40], type=pa.int64()),
            }
        ),
        first_path,
    )

    valid, rejects, _ = ingestion.validate(
        ingestion.read_raw(first_path), "DUPLICATE", first_path.name
    )

    assert valid.get_column("volume").to_list() == [10, 30]
    assert rejects.get_column("row_number").to_list() == [2, 4]
    assert rejects.get_column("reject_reason").to_list() == ["duplicate", "duplicate"]

    second_path = tmp_path / "SECOND.parquet"
    write_bar(second_path)
    second_valid, second_rejects, _ = ingestion.validate(
        ingestion.read_raw(second_path), "DUPLICATE", second_path.name
    )
    assert second_valid.height == 1
    assert second_rejects.is_empty()


def test_unsigned_volume_must_fit_processed_int64_schema():
    df = pa.table(
        {
            "date": pa.array([TIMESTAMP_MS, TIMESTAMP_MS + 60_000], type=pa.int64()),
            "open": pa.array([100.0, 100.0]),
            "high": pa.array([101.0, 101.0]),
            "low": pa.array([99.0, 99.0]),
            "close": pa.array([100.5, 100.5]),
            "volume": pa.array(
                [ingestion.MAX_VOLUME, ingestion.MAX_VOLUME + 1], type=pa.uint64()
            ),
        }
    )
    input_df = pl.from_arrow(df)

    valid, rejects, _ = ingestion.validate(
        input_df, "UINT_VOLUME", "UINT_VOLUME.parquet"
    )

    assert valid.get_column("volume").to_list() == [ingestion.MAX_VOLUME]
    assert rejects.get_column("reject_reason").to_list() == ["volume_out_of_range"]


def test_write_processed_groups_rows_into_typed_zstd_hive_partitions(
    tmp_path, monkeypatch
):
    processed_dir = tmp_path / "processed"
    utc = timezone.utc
    valid = pl.DataFrame(
        {
            "symbol": ["OTHER"] * 4,
            "timestamp": [
                datetime(2024, 1, 2, 3, 47, tzinfo=utc),
                datetime(2024, 2, 1, 3, 45, tzinfo=utc),
                datetime(2024, 1, 2, 3, 45, tzinfo=utc),
                datetime(2024, 1, 2, 3, 46, tzinfo=utc),
            ],
            "trading_date": [
                date(2024, 1, 2),
                date(2024, 2, 1),
                date(2024, 1, 2),
                date(2024, 1, 2),
            ],
            "open": [100.0, 101.0, 99.0, 100.0],
            "high": [101.0, 102.0, 100.0, 101.0],
            "low": [99.0, 100.0, 98.0, 99.0],
            "close": [100.5, 101.5, 99.5, 100.5],
            "volume": [10, 20, 30, 40],
        }
    )

    write_options = []
    original_write_table = pq.write_table

    def capture_write_options(table, file, **options):
        write_options.append(options.copy())
        return original_write_table(table, file, **options)

    monkeypatch.setattr(pq, "write_table", capture_write_options)
    output_details = ingestion.write_processed(valid, "ABC", processed_dir)

    paths = sorted(processed_dir.rglob("*.parquet"))
    assert len(output_details) == 2
    assert len(paths) == 2  # Three January rows share a single partition file.
    assert paths[0].relative_to(processed_dir).as_posix() == (
        "interval=1m/year=2024/month=01/symbol=ABC/part.parquet"
    )
    assert paths[1].relative_to(processed_dir).as_posix() == (
        "interval=1m/year=2024/month=02/symbol=ABC/part.parquet"
    )
    assert len(write_options) == 2
    assert all(options["compression"] == "zstd" for options in write_options)
    assert all(options["compression_level"] == 3 for options in write_options)
    assert output_details == [
        {
            "path": "interval=1m/year=2024/month=01/symbol=ABC/part.parquet",
            "rows": 3,
        },
        {
            "path": "interval=1m/year=2024/month=02/symbol=ABC/part.parquet",
            "rows": 1,
        },
    ]

    january_path = paths[0]
    january = pq.read_table(january_path)
    assert january.column("symbol").to_pylist() == ["ABC"] * 3
    assert january.column("timestamp").to_pylist() == [
        datetime(2024, 1, 2, 3, 45, tzinfo=utc),
        datetime(2024, 1, 2, 3, 46, tzinfo=utc),
        datetime(2024, 1, 2, 3, 47, tzinfo=utc),
    ]
    assert january.schema == pa.schema(
        [
            ("symbol", pa.string()),
            ("timestamp", pa.timestamp("us", tz="UTC")),
            ("trading_date", pa.date32()),
            ("open", pa.float64()),
            ("high", pa.float64()),
            ("low", pa.float64()),
            ("close", pa.float64()),
            ("volume", pa.int64()),
        ]
    )
    metadata = pq.read_metadata(january_path)
    assert all(
        metadata.row_group(0).column(i).compression == "ZSTD"
        for i in range(metadata.num_columns)
    )


def test_run_ignores_out_of_scope_and_continues_after_file_errors(tmp_path):
    raw_dir = tmp_path / "raw"
    raw_dir.mkdir()
    processed_dir = tmp_path / "processed"
    rejects_dir = tmp_path / "rejects"
    index_csv = tmp_path / "NIFTY50.csv"
    index_csv.write_text("Ticker\nVALID\nMISSING\nBADTYPE\nEMPTY\nCORRUPT\n")

    write_bar(raw_dir / "VALID.parquet")
    pq.write_table(
        pa.table(
            {
                "date": pa.array([TIMESTAMP_MS]),
                "open": pa.array([1.0]),
                "high": pa.array([1.0]),
                "low": pa.array([1.0]),
                "close": pa.array([1.0]),
            }
        ),
        raw_dir / "MISSING.parquet",
    )
    schema = pa.schema(
        [
            ("date", pa.int64()),
            ("open", pa.list_(pa.int64())),
            ("high", pa.float64()),
            ("low", pa.float64()),
            ("close", pa.float64()),
            ("volume", pa.int64()),
        ]
    )
    pq.write_table(
        pa.Table.from_arrays(
            [
                pa.array([TIMESTAMP_MS], type=pa.int64()),
                pa.array([[1]], type=pa.list_(pa.int64())),
                pa.array([1.0]),
                pa.array([1.0]),
                pa.array([1.0]),
                pa.array([1], type=pa.int64()),
            ],
            schema=schema,
        ),
        raw_dir / "BADTYPE.parquet",
    )
    pq.write_table(
        pa.table(
            {
                "date": pa.array([], type=pa.int64()),
                "open": pa.array([], type=pa.float64()),
                "high": pa.array([], type=pa.float64()),
                "low": pa.array([], type=pa.float64()),
                "close": pa.array([], type=pa.float64()),
                "volume": pa.array([], type=pa.int64()),
            }
        ),
        raw_dir / "EMPTY.parquet",
    )
    (raw_dir / "CORRUPT.parquet").write_bytes(b"not parquet")
    out_of_scope = raw_dir / "OUTSIDE.parquet"
    out_of_scope.write_bytes(b"out of scope and unreadable")
    out_of_scope_before = out_of_scope.read_bytes()

    args = SimpleNamespace(
        raw_dir=str(raw_dir),
        processed_dir=str(processed_dir),
        rejects_dir=str(rejects_dir),
        index_csv=str(index_csv),
    )
    summary = ingestion.run(args)

    assert summary.files_discovered == 6
    assert summary.files_in_scope == 5
    assert summary.files_out_of_scope == 1
    assert summary.out_of_scope_files == ["OUTSIDE.parquet"]
    assert summary.files_processed == 1
    assert summary.files_empty == 1
    assert summary.files_error == 3
    assert len(list(processed_dir.rglob("*.parquet"))) == 1
    assert out_of_scope.read_bytes() == out_of_scope_before

    errors = (rejects_dir / "file_errors.log").read_text()
    for filename in ("MISSING.parquet", "BADTYPE.parquet", "CORRUPT.parquet"):
        assert filename in errors
    assert "OUTSIDE.parquet" not in errors


def test_run_counts_output_write_failure_as_file_error(tmp_path, monkeypatch):
    raw_dir = tmp_path / "raw"
    raw_dir.mkdir()
    write_bar(raw_dir / "WRITEFAIL.parquet")
    index_csv = tmp_path / "NIFTY50.csv"
    index_csv.write_text("Ticker\nWRITEFAIL\n")

    def fail_write(*args, **kwargs):
        raise OSError("disk full")

    monkeypatch.setattr(ingestion, "write_processed", fail_write)
    rejects_dir = tmp_path / "rejects"
    summary = ingestion.run(
        SimpleNamespace(
            raw_dir=str(raw_dir),
            processed_dir=str(tmp_path / "processed"),
            rejects_dir=str(rejects_dir),
            index_csv=str(index_csv),
        )
    )

    assert summary.files_processed == 0
    assert summary.files_error == 1
    assert summary.files[0].status == "error"
    assert summary.files[0].error == "OSError: disk full"
    assert "WRITEFAIL.parquet\tOSError: disk full" in (
        rejects_dir / "file_errors.log"
    ).read_text()


def test_cli_writes_deterministic_rejects_logs_and_complete_summary(tmp_path):
    data_dir = tmp_path / "data"
    raw_dir = data_dir / "raw"
    raw_dir.mkdir(parents=True)
    processed_dir = data_dir / "processed"
    rejects_dir = data_dir / "rejects"
    index_csv = data_dir / "index" / "NIFTY50.csv"
    index_csv.parent.mkdir(parents=True)
    index_csv.write_text("Ticker\nBAD\nBROKEN\nEMPTY\nGOOD\n")

    write_bar(raw_dir / "GOOD.parquet")
    pq.write_table(
        pa.table(
            {
                "date": pa.array([TIMESTAMP_MS], type=pa.int64()),
                "open": pa.array([0.0]),
                "high": pa.array([0.0]),
                "low": pa.array([1.0]),
                "close": pa.array([1.0]),
                "volume": pa.array([-3], type=pa.int64()),
            }
        ),
        raw_dir / "BAD.parquet",
    )
    pq.write_table(
        pa.table(
            {
                "date": pa.array([], type=pa.int64()),
                "open": pa.array([], type=pa.float64()),
                "high": pa.array([], type=pa.float64()),
                "low": pa.array([], type=pa.float64()),
                "close": pa.array([], type=pa.float64()),
                "volume": pa.array([], type=pa.int64()),
            }
        ),
        raw_dir / "EMPTY.parquet",
    )
    (raw_dir / "BROKEN.parquet").write_bytes(b"not parquet")
    (raw_dir / "OUTSIDE.parquet").write_bytes(b"not in scope")

    command = [sys.executable, str(Path(ingestion.__file__).resolve())]

    def run_cli():
        return subprocess.run(
            command, capture_output=True, text=True, check=False, cwd=tmp_path
        )

    first = run_cli()
    assert first.returncode == 1  # The unreadable file is reported as an error.
    summary_start = first.stdout.index("INGESTION SUMMARY")
    summary = json.loads(first.stdout[first.stdout.index("{", summary_start) :])
    assert summary["files_discovered"] == 5
    assert summary["files_in_scope"] == 4
    assert summary["files_out_of_scope"] == 1
    assert summary["files_processed"] == 2
    assert summary["files_empty"] == 1
    assert summary["files_error"] == 1
    assert summary["total_input_rows"] == 2
    assert summary["total_valid_rows"] == 1
    assert summary["total_rejected_rows"] == 1
    assert summary["reject_counts_by_category"] == {
        "negative_volume": 1,
        "non_positive_price": 1,
        "ohlc_inconsistent": 1,
    }
    assert summary["duration_seconds"] >= 0
    assert [result["status"] for result in summary["file_results"]] == [
        "processed",
        "error",
        "empty",
        "processed",
    ]
    assert summary["file_results"][1]["source_file"] == "BROKEN.parquet"
    assert "Parquet" in summary["file_results"][1]["error"]
    assert summary["output_files"] == [
        {
            "symbol": "GOOD",
            "path": "interval=1m/year=2024/month=01/symbol=GOOD/part.parquet",
            "rows": 1,
        }
    ]

    reject_path = rejects_dir / "BAD.csv"
    reject_bytes = reject_path.read_bytes()
    with reject_path.open(newline="", encoding="utf-8") as handle:
        reject_row = next(csv.DictReader(handle))
    assert reject_row["source_file"] == "BAD.parquet"
    assert reject_row["reject_reason"] == (
        "non_positive_price;negative_volume;ohlc_inconsistent"
    )
    error_log = (rejects_dir / "file_errors.log").read_bytes()
    assert b"BROKEN.parquet" in error_log
    assert b"OUTSIDE.parquet" not in error_log

    second = run_cli()
    assert second.returncode == 1
    assert reject_path.read_bytes() == reject_bytes
    assert (rejects_dir / "file_errors.log").read_bytes() == error_log

    # If the latest input has no rejects, remove a stale prior-run reject CSV.
    write_bar(raw_dir / "BAD.parquet")
    third = run_cli()
    assert third.returncode == 1
    assert not reject_path.exists()
