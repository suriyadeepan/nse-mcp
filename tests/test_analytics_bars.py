"""Tests for the public get_bars analytics function."""

from dataclasses import replace
from datetime import datetime, timezone

import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from src.server import analytics, validation
from src.server.validation import AnalyticsInputError


@pytest.fixture
def bars_dataset(tmp_path, monkeypatch):
    rows = [
        (datetime(2024, 1, 2, 3, 45, tzinfo=timezone.utc), 100, 102, 99, 101, 100),
        (datetime(2024, 1, 2, 3, 45, tzinfo=timezone.utc), 101, 103, 100, 102, 200),
        (datetime(2024, 1, 2, 3, 46, tzinfo=timezone.utc), 102, 104, 101, 103, 300),
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
                "trading_date": pa.array(
                    [row[0].date() for row in rows],
                    type=pa.date32(),
                ),
                "open": pa.array([row[1] for row in rows], type=pa.float64()),
                "high": pa.array([row[2] for row in rows], type=pa.float64()),
                "low": pa.array([row[3] for row in rows], type=pa.float64()),
                "close": pa.array([row[4] for row in rows], type=pa.float64()),
                "volume": pa.array([row[5] for row in rows], type=pa.int64()),
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


def test_get_bars_returns_ordered_ohlcv_with_count(bars_dataset):
    result = analytics.get_bars(
        "AAA",
        "2024-01-02T09:15:00+05:30",
        "2024-01-02T09:16:00+05:30",
        10,
    )

    assert result["returned_count"] == 3
    assert [bar["timestamp"] for bar in result["bars"]] == [
        datetime(2024, 1, 2, 3, 45, tzinfo=timezone.utc),
        datetime(2024, 1, 2, 3, 45, tzinfo=timezone.utc),
        datetime(2024, 1, 2, 3, 46, tzinfo=timezone.utc),
    ]
    assert all(bar["timestamp"].tzinfo is timezone.utc for bar in result["bars"])
    assert result["bars"][0] == {
        "timestamp": datetime(2024, 1, 2, 3, 45, tzinfo=timezone.utc),
        "open": 100.0,
        "high": 102.0,
        "low": 99.0,
        "close": 101.0,
        "volume": 100,
    }
    assert set(result["bars"][0]) == {
        "timestamp",
        "open",
        "high",
        "low",
        "close",
        "volume",
    }


def test_get_bars_applies_limit_and_returns_empty_range(bars_dataset):
    limited = analytics.get_bars(
        "AAA", "2024-01-02T03:45:00Z", "2024-01-02T03:46:00Z", 2
    )
    assert limited["returned_count"] == 2
    assert len(limited["bars"]) == 2

    empty = analytics.get_bars(
        "AAA", "2024-01-02T03:50:00Z", "2024-01-02T03:51:00Z", 10
    )
    assert empty == {"bars": [], "returned_count": 0}


def test_get_bars_rejects_invalid_inputs_and_excessive_limit(bars_dataset, monkeypatch):
    with pytest.raises(AnalyticsInputError, match="unknown symbol"):
        analytics.get_bars(
            "AAA' OR 1=1 --", "2024-01-02T03:45:00Z", "2024-01-02T03:46:00Z", 10
        )
    with pytest.raises(AnalyticsInputError, match="ISO-8601"):
        analytics.get_bars(
            "AAA",
            "2024-01-02T03:45:00Z' OR 1=1 --",
            "2024-01-02T03:46:00Z",
            10,
        )
    with pytest.raises(AnalyticsInputError, match="on or after"):
        analytics.get_bars(
            "AAA", "2024-01-02T03:46:00Z", "2024-01-02T03:45:00Z", 10
        )

    monkeypatch.setattr(
        validation,
        "ANALYTICS_CONFIG",
        replace(validation.ANALYTICS_CONFIG, max_date_range_days=1),
    )
    with pytest.raises(AnalyticsInputError, match="exceeds the configured maximum"):
        analytics.get_bars(
            "AAA", "2024-01-01T00:00:00Z", "2024-01-03T00:00:00Z", 10
        )

    monkeypatch.setattr(
        validation,
        "ANALYTICS_CONFIG",
        replace(validation.ANALYTICS_CONFIG, max_returned_rows=2),
    )
    with pytest.raises(AnalyticsInputError, match="cannot exceed"):
        analytics.get_bars(
            "AAA", "2024-01-02T03:45:00Z", "2024-01-02T03:46:00Z", 3
        )
