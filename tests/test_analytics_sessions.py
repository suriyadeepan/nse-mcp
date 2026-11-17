"""Tests for IST session statistics and price extremes."""

from dataclasses import replace
from datetime import date, datetime, timezone

import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from src.server import analytics, validation
from src.server.validation import AnalyticsInputError


@pytest.fixture
def session_dataset(tmp_path, monkeypatch):
    rows = [
        (datetime(2024, 1, 1, 18, 29, tzinfo=timezone.utc), date(2024, 1, 1), 6, 8, 5, 7, 10),
        (datetime(2024, 1, 1, 18, 30, tzinfo=timezone.utc), date(2024, 1, 2), 10, 12, 9, 11, 100),
        (datetime(2024, 1, 2, 3, 45, tzinfo=timezone.utc), date(2024, 1, 2), 11, 15, 8, 12, 200),
        (datetime(2024, 1, 2, 3, 46, tzinfo=timezone.utc), date(2024, 1, 2), 12, 15, 10, 14, 0),
        (datetime(2024, 1, 2, 18, 30, tzinfo=timezone.utc), date(2024, 1, 3), 100, 110, 90, 105, 0),
    ]
    path = (
        tmp_path
        / "interval=1m"
        / "year=2024"
        / "month=01"
        / "symbol=AAA"
        / "part.parquet"
    )
    path.parent.mkdir(parents=True)
    pq.write_table(
        pa.table(
            {
                "symbol": pa.array(["AAA"] * len(rows), type=pa.string()),
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
        ),
        path,
    )
    monkeypatch.setattr(
        analytics,
        "ANALYTICS_CONFIG",
        replace(analytics.ANALYTICS_CONFIG, processed_data_dir=tmp_path),
    )
    monkeypatch.setattr(
        validation,
        "ANALYTICS_CONFIG",
        replace(validation.ANALYTICS_CONFIG, processed_data_dir=tmp_path),
    )
    return tmp_path


def test_intraday_stats_uses_ist_trading_date_and_calculates_session_values(
    session_dataset,
):
    result = analytics.intraday_stats("AAA", "2024-01-02")

    assert result == {
        "open": 10.0,
        "close": 14.0,
        "high": 15.0,
        "low": 8.0,
        "total_volume": 300,
        "vwap": pytest.approx(11.333333333333334),
        "absolute_return": 4.0,
        "percentage_return": pytest.approx(40.0),
        "bar_count": 3,
        "first_timestamp": datetime(2024, 1, 1, 18, 30, tzinfo=timezone.utc),
        "last_timestamp": datetime(2024, 1, 2, 3, 46, tzinfo=timezone.utc),
    }


def test_intraday_stats_empty_and_zero_volume_are_explicit(session_dataset):
    empty = analytics.intraday_stats("AAA", "2024-01-04")
    assert empty["bar_count"] == 0
    assert empty["open"] is None
    assert empty["total_volume"] is None
    assert empty["vwap"] is None
    assert empty["first_timestamp"] is None

    zero_volume = analytics.intraday_stats("AAA", date(2024, 1, 3))
    assert zero_volume["bar_count"] == 1
    assert zero_volume["total_volume"] == 0
    assert zero_volume["vwap"] is None


def test_price_extremes_use_earliest_timestamp_for_tied_prices(session_dataset):
    result = analytics.get_price_extremes(
        "AAA", "2024-01-01T18:30:00Z", "2024-01-02T03:46:00Z"
    )

    assert result == {
        "highest_high": 15.0,
        "highest_high_timestamp": datetime(2024, 1, 2, 3, 45, tzinfo=timezone.utc),
        "lowest_low": 8.0,
        "lowest_low_timestamp": datetime(2024, 1, 2, 3, 45, tzinfo=timezone.utc),
        "range_absolute": 7.0,
        "range_percentage": 87.5,
    }


def test_price_extremes_empty_and_invalid_inputs(session_dataset):
    empty = analytics.get_price_extremes(
        "AAA", "2024-01-04T00:00:00Z", "2024-01-04T01:00:00Z"
    )
    assert empty["highest_high"] is None
    assert empty["range_absolute"] is None

    with pytest.raises(AnalyticsInputError, match="unknown symbol"):
        analytics.get_price_extremes(
            "BAD", "2024-01-02T00:00:00Z", "2024-01-02T01:00:00Z"
        )
