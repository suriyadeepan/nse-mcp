"""Tests for analytics query templates and shared input validation."""

from dataclasses import replace
from datetime import date, datetime, timedelta, timezone

import duckdb
import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from src.server import validation
from src.server.data import list_symbols
from src.server.queries import BARS_BEFORE_START_SQL, BARS_IN_RANGE_SQL, DAILY_BARS_SQL
from src.server.validation import (
    AnalyticsDataError,
    AnalyticsError,
    AnalyticsInputError,
    validate_bucket,
    validate_datetime,
    validate_datetime_range,
    validate_indicators,
    validate_interval,
    validate_limit,
    validate_symbol,
    validate_symbols,
    validate_trading_date,
)


def _write_partition(root, symbol, year, month, rows):
    path = (
        root
        / "interval=1m"
        / f"year={year}"
        / f"month={month:02}"
        / f"symbol={symbol}"
        / "part.parquet"
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    table = pa.table(
        {
            "symbol": pa.array([symbol] * len(rows), type=pa.string()),
            "timestamp": pa.array(
                [row[0] for row in rows], type=pa.timestamp("us", tz="UTC")
            ),
            "trading_date": pa.array([row[1] for row in rows], type=pa.date32()),
            "open": pa.array([row[2] for row in rows], type=pa.float64()),
            "high": pa.array([row[3] for row in rows], type=pa.float64()),
            "low": pa.array([row[4] for row in rows], type=pa.float64()),
            "close": pa.array([row[5] for row in rows], type=pa.float64()),
            "volume": pa.array([row[6] for row in rows], type=pa.int64()),
        }
    )
    pq.write_table(table, path)
    return path


@pytest.fixture
def processed_dataset(tmp_path):
    _write_partition(
        tmp_path,
        "AAA",
        2023,
        12,
        [(datetime(2023, 12, 29, 8, tzinfo=timezone.utc), date(2023, 12, 29), 90, 95, 89, 92, 10)],
    )
    _write_partition(
        tmp_path,
        "AAA",
        2024,
        1,
        [
            (datetime(2024, 1, 2, 3, 45, tzinfo=timezone.utc), date(2024, 1, 2), 100, 102, 99, 101, 100),
            (datetime(2024, 1, 2, 3, 46, tzinfo=timezone.utc), date(2024, 1, 2), 101, 103, 100, 102, 200),
            (datetime(2024, 1, 3, 3, 45, tzinfo=timezone.utc), date(2024, 1, 3), 102, 104, 101, 103, 300),
        ],
    )
    _write_partition(
        tmp_path,
        "BBB",
        2024,
        1,
        [(datetime(2024, 1, 2, 3, 45, tzinfo=timezone.utc), date(2024, 1, 2), 500, 505, 499, 503, 50)],
    )
    return tmp_path


def test_symbol_allowlist_reads_hive_and_legacy_flat_files(processed_dataset):
    (processed_dataset / "LEGACY.parquet").touch()

    assert list_symbols(processed_dataset) == ["AAA", "BBB", "LEGACY"]


def test_symbol_validation_uses_configured_allowlist(processed_dataset, monkeypatch):
    monkeypatch.setattr(
        validation,
        "ANALYTICS_CONFIG",
        replace(validation.ANALYTICS_CONFIG, processed_data_dir=processed_dataset),
    )

    assert validate_symbol("AAA") == "AAA"
    assert validate_symbols(["AAA", "BBB"], minimum=2) == ("AAA", "BBB")
    with pytest.raises(AnalyticsInputError, match="unknown symbol"):
        validate_symbol("AAA' OR 1=1 --")
    with pytest.raises(AnalyticsInputError, match="duplicates"):
        validate_symbols(["AAA", "AAA"])
    with pytest.raises(AnalyticsInputError, match="at least 2"):
        validate_symbols(["AAA"], minimum=2)


def test_analytics_errors_have_stable_public_schemas(processed_dataset, monkeypatch):
    invalid = AnalyticsInputError("bad request")
    assert isinstance(invalid, AnalyticsError)
    assert invalid.as_dict() == {"code": "invalid_input", "message": "bad request"}

    missing_data = processed_dataset / "not-present"
    monkeypatch.setattr(
        validation,
        "ANALYTICS_CONFIG",
        replace(validation.ANALYTICS_CONFIG, processed_data_dir=missing_data),
    )
    with pytest.raises(AnalyticsDataError) as caught:
        validate_symbol("AAA")
    assert caught.value.as_dict() == {
        "code": "data_unavailable",
        "message": "processed analytics data is unavailable",
    }


def test_datetime_and_date_validation_normalize_and_bound_inputs():
    india_offset = timezone(timedelta(hours=5, minutes=30))
    local = datetime(2024, 1, 2, 9, 15, tzinfo=india_offset)
    assert validate_datetime(local, name="start_datetime") == datetime(
        2024, 1, 2, 3, 45, tzinfo=timezone.utc
    )
    assert validate_datetime("2024-01-02T09:15:00+05:30", name="start") == datetime(
        2024, 1, 2, 3, 45, tzinfo=timezone.utc
    )
    assert validate_trading_date("2024-01-02") == date(2024, 1, 2)

    with pytest.raises(AnalyticsInputError, match="timezone offset"):
        validate_datetime(datetime(2024, 1, 2), name="start_datetime")
    with pytest.raises(AnalyticsInputError, match="on or after"):
        validate_datetime_range("2024-01-03T00:00:00Z", "2024-01-02T00:00:00Z")
    with pytest.raises(AnalyticsInputError, match="maximum of 1 days"):
        validate_datetime_range(
            "2024-01-01T00:00:00Z", "2024-01-03T00:00:00Z", max_days=1
        )
    with pytest.raises(AnalyticsInputError, match="calendar date"):
        validate_trading_date(datetime(2024, 1, 2))


def test_limits_and_enumerated_inputs_are_canonicalized():
    assert validate_limit(25, maximum=25) == 25
    assert validate_bucket("HOURLY") == "hourly"
    assert validate_interval("Daily") == "daily"
    assert validate_indicators(["sma", "ATR"]) == ("SMA", "ATR")

    for invalid in (0, -1, True, 26):
        with pytest.raises(AnalyticsInputError):
            validate_limit(invalid, maximum=25)
    with pytest.raises(AnalyticsInputError, match="bucket"):
        validate_bucket("weekly")
    with pytest.raises(AnalyticsInputError, match="interval"):
        validate_interval("hourly")
    with pytest.raises(AnalyticsInputError, match="indicator"):
        validate_indicators(["MACD"])


def test_predefined_queries_bind_values_and_aggregate_rows(processed_dataset):
    glob = str(processed_dataset / "**" / "*.parquet")
    connection = duckdb.connect(":memory:")
    try:
        in_range = connection.sql(
            BARS_IN_RANGE_SQL,
            params=[
                glob,
                "AAA",
                "2024",
                "2024",
                "01",
                "2024",
                "2024",
                "01",
                "2024-01-02T03:45:00+00:00",
                "2024-01-02T03:46:00+00:00",
                10,
            ],
        ).to_arrow_table().to_pylist()
        assert [row["timestamp"] for row in in_range] == [
            datetime(2024, 1, 2, 3, 45, tzinfo=timezone.utc),
            datetime(2024, 1, 2, 3, 46, tzinfo=timezone.utc),
        ]

        warmup = connection.sql(
            BARS_BEFORE_START_SQL,
            params=[
                glob,
                "AAA",
                "2023",
                "2023",
                "12",
                "2024",
                "2024",
                "01",
                "2024-01-02T03:45:00+00:00",
                1,
            ],
        ).to_arrow_table().to_pylist()
        assert warmup[0]["timestamp"] == datetime(
            2023, 12, 29, 8, tzinfo=timezone.utc
        )

        daily = connection.sql(
            DAILY_BARS_SQL,
            params=[
                glob,
                "AAA",
                "2024",
                "2024",
                "01",
                "2024",
                "2024",
                "01",
                date(2024, 1, 2),
                date(2024, 1, 3),
            ],
        ).to_arrow_table().to_pylist()
        assert daily == [
            {
                "symbol": "AAA",
                "trading_date": date(2024, 1, 2),
                "open": 100.0,
                "high": 103.0,
                "low": 99.0,
                "close": 102.0,
                "volume": 300,
            },
            {
                "symbol": "AAA",
                "trading_date": date(2024, 1, 3),
                "open": 102.0,
                "high": 104.0,
                "low": 101.0,
                "close": 103.0,
                "volume": 300,
            },
        ]

        injected_symbol = connection.sql(
            BARS_IN_RANGE_SQL,
            params=[
                glob,
                "AAA' OR 1=1 --",
                "2024",
                "2024",
                "01",
                "2024",
                "2024",
                "01",
                "2024-01-02T03:45:00+00:00",
                "2024-01-02T03:46:00+00:00",
                10,
            ],
        ).fetchall()
        assert injected_symbol == []
    finally:
        connection.close()
