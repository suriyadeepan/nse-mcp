"""Tests for candle volume statistics and IST buckets."""

from dataclasses import replace
from datetime import date, datetime, timezone

import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from src.server import analytics, validation
from src.server.validation import AnalyticsInputError


@pytest.fixture
def volume_dataset(tmp_path, monkeypatch):
    rows = [
        (datetime(2024, 1, 2, 3, 45, tzinfo=timezone.utc), date(2024, 1, 2), 10),
        (datetime(2024, 1, 2, 3, 59, tzinfo=timezone.utc), date(2024, 1, 2), 20),
        (datetime(2024, 1, 2, 4, 0, tzinfo=timezone.utc), date(2024, 1, 2), 30),
        (datetime(2024, 1, 2, 4, 30, tzinfo=timezone.utc), date(2024, 1, 2), 40),
        (datetime(2024, 1, 2, 18, 31, tzinfo=timezone.utc), date(2024, 1, 3), 50),
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
                "open": pa.array([100.0] * len(rows), type=pa.float64()),
                "high": pa.array([101.0] * len(rows), type=pa.float64()),
                "low": pa.array([99.0] * len(rows), type=pa.float64()),
                "close": pa.array([100.0] * len(rows), type=pa.float64()),
                "volume": pa.array([row[2] for row in rows], type=pa.int64()),
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


def test_volume_stats_returns_candle_and_hourly_bucket_averages(volume_dataset):
    result = analytics.get_volume_stats(
        "AAA", "2024-01-02T03:45:00Z", "2024-01-02T18:31:00Z", "hourly"
    )

    assert result == {
        "total_volume": 150.0,
        "average_volume": 30.0,
        "maximum_volume": 50.0,
        "minimum_volume": 10.0,
        "average_bucket_volume": 50.0,
        "bar_count": 5,
        "volume_by_bucket": [
            {"bucket": "2024-01-02T09:00:00+05:30", "volume": 60.0},
            {"bucket": "2024-01-02T10:00:00+05:30", "volume": 40.0},
            {"bucket": "2024-01-03T00:00:00+05:30", "volume": 50.0},
        ],
    }


def test_volume_stats_daily_buckets_follow_ist_date(volume_dataset):
    result = analytics.get_volume_stats(
        "AAA", "2024-01-02T03:45:00Z", "2024-01-02T18:31:00Z", "daily"
    )

    assert result["average_volume"] == 30.0
    assert result["average_bucket_volume"] == 75.0
    assert result["volume_by_bucket"] == [
        {"bucket": "2024-01-02", "volume": 100.0},
        {"bucket": "2024-01-03", "volume": 50.0},
    ]


def test_volume_stats_empty_invalid_and_result_cap(volume_dataset, monkeypatch):
    empty = analytics.get_volume_stats(
        "AAA", "2024-01-04T00:00:00Z", "2024-01-04T01:00:00Z", "daily"
    )
    assert empty["bar_count"] == 0
    assert empty["total_volume"] is None
    assert empty["average_volume"] is None
    assert empty["volume_by_bucket"] == []

    with pytest.raises(AnalyticsInputError, match="bucket"):
        analytics.get_volume_stats(
            "AAA", "2024-01-02T00:00:00Z", "2024-01-02T01:00:00Z", "weekly"
        )
    monkeypatch.setattr(
        analytics,
        "ANALYTICS_CONFIG",
        replace(analytics.ANALYTICS_CONFIG, max_returned_rows=2),
    )
    with pytest.raises(AnalyticsInputError, match="bucket count exceeds"):
        analytics.get_volume_stats(
            "AAA", "2024-01-02T03:45:00Z", "2024-01-02T18:31:00Z", "hourly"
        )
