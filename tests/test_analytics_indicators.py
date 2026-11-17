"""Tests for indicator warm-up and calculations."""

from dataclasses import replace
from datetime import date, datetime, timezone

import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from src.server import analytics, validation
from src.server.validation import AnalyticsInputError


@pytest.fixture
def indicator_dataset(tmp_path, monkeypatch):
    rows = [
        (datetime(2023, 12, 29, 3, 45, tzinfo=timezone.utc), 10.0),
        (datetime(2023, 12, 29, 3, 46, tzinfo=timezone.utc), 11.0),
        (datetime(2023, 12, 29, 3, 47, tzinfo=timezone.utc), 12.0),
        (datetime(2024, 1, 2, 3, 45, tzinfo=timezone.utc), 11.0),
        (datetime(2024, 1, 2, 3, 46, tzinfo=timezone.utc), 13.0),
        (datetime(2024, 1, 2, 3, 47, tzinfo=timezone.utc), 12.0),
        (datetime(2024, 1, 2, 3, 48, tzinfo=timezone.utc), 14.0),
        (datetime(2024, 1, 2, 3, 49, tzinfo=timezone.utc), 15.0),
    ]
    partitions = {}
    for row in rows:
        partitions.setdefault((row[0].year, row[0].month), []).append(row)
    for (year, month), partition_rows in partitions.items():
        path = (
            tmp_path
            / "interval=1m"
            / f"year={year}"
            / f"month={month:02}"
            / "symbol=AAA"
            / "part.parquet"
        )
        path.parent.mkdir(parents=True)
        pq.write_table(
            pa.table(
                {
                    "symbol": pa.array(["AAA"] * len(partition_rows), type=pa.string()),
                    "timestamp": pa.array(
                        [row[0] for row in partition_rows],
                        type=pa.timestamp("us", tz="UTC"),
                    ),
                    "trading_date": pa.array(
                        [row[0].date() for row in partition_rows],
                        type=pa.date32(),
                    ),
                    "open": pa.array(
                        [row[1] for row in partition_rows], type=pa.float64()
                    ),
                    "high": pa.array(
                        [row[1] + 1 for row in partition_rows], type=pa.float64()
                    ),
                    "low": pa.array(
                        [row[1] - 1 for row in partition_rows], type=pa.float64()
                    ),
                    "close": pa.array(
                        [row[1] for row in partition_rows], type=pa.float64()
                    ),
                    "volume": pa.array([100] * len(partition_rows), type=pa.int64()),
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


def _all_indicators(start, end):
    return analytics.compute_indicators(
        "AAA",
        start,
        end,
        ["SMA", "EMA", "RSI", "ATR"],
        {"SMA": 3, "EMA": 3, "RSI": 3, "ATR": 3},
    )


def test_indicators_use_prior_month_warmup_and_expected_values(indicator_dataset):
    result = _all_indicators("2024-01-02T03:45:00Z", "2024-01-02T03:48:00Z")

    assert result["returned_count"] == 4
    assert result["indicator_parameters"] == {
        "SMA": {"period": 3},
        "EMA": {"period": 3},
        "RSI": {"period": 3},
        "ATR": {"period": 3},
    }
    assert result["indicator_status"] == {
        "SMA": "ready",
        "EMA": "ready",
        "RSI": "ready",
        "ATR": "ready",
    }
    first = result["values"][0]
    assert first == {
        "timestamp": datetime(2024, 1, 2, 3, 45, tzinfo=timezone.utc),
        "close": 11.0,
        "SMA": pytest.approx(11.333333333333334),
        "EMA": 11.0,
        "RSI": pytest.approx(66.66666666666666),
        "ATR": 2.0,
    }


def test_indicators_have_initial_nulls_and_report_insufficient_history(
    indicator_dataset,
):
    result = analytics.compute_indicators(
        "AAA",
        "2023-12-29T03:45:00Z",
        "2023-12-29T03:46:00Z",
        ["SMA", "EMA", "RSI", "ATR"],
        {"SMA": 3, "EMA": 3, "RSI": 3, "ATR": 3},
    )

    assert result["indicator_status"] == {
        "SMA": "insufficient_history",
        "EMA": "insufficient_history",
        "RSI": "insufficient_history",
        "ATR": "insufficient_history",
    }
    assert all(
        row[name] is None
        for row in result["values"]
        for name in ("SMA", "EMA", "RSI", "ATR")
    )

    empty = analytics.compute_indicators(
        "AAA",
        "2024-01-03T00:00:00Z",
        "2024-01-03T01:00:00Z",
        ["SMA"],
    )
    assert empty["indicator_status"] == {"SMA": "no_data"}
    assert empty["values"] == []


def test_indicator_values_do_not_depend_on_future_candles(indicator_dataset):
    short = _all_indicators("2024-01-02T03:45:00Z", "2024-01-02T03:48:00Z")
    extended = _all_indicators("2024-01-02T03:45:00Z", "2024-01-02T03:49:00Z")
    assert short["values"] == extended["values"][: len(short["values"])]


def test_indicator_parameters_and_result_limits_are_validated(
    indicator_dataset, monkeypatch
):
    base = ("AAA", "2024-01-02T03:45:00Z", "2024-01-02T03:46:00Z", ["SMA"])
    with pytest.raises(AnalyticsInputError, match="period must be an integer"):
        analytics.compute_indicators(*base, {"SMA": 0})
    with pytest.raises(AnalyticsInputError, match="unrequested indicator"):
        analytics.compute_indicators(*base, {"EMA": 3})
    with pytest.raises(AnalyticsInputError, match="at least one indicator"):
        analytics.compute_indicators(
            "AAA", "2024-01-02T03:45:00Z", "2024-01-02T03:46:00Z", []
        )

    monkeypatch.setattr(
        analytics,
        "ANALYTICS_CONFIG",
        replace(analytics.ANALYTICS_CONFIG, max_returned_rows=1),
    )
    with pytest.raises(AnalyticsInputError, match="result count exceeds"):
        analytics.compute_indicators(
            "AAA", "2024-01-02T03:45:00Z", "2024-01-02T03:48:00Z", ["SMA"]
        )


def test_ema_warmup_cannot_exceed_configured_limit(indicator_dataset, monkeypatch):
    monkeypatch.setattr(
        analytics,
        "ANALYTICS_CONFIG",
        replace(
            analytics.ANALYTICS_CONFIG,
            indicator_warmup_default=10,
            indicator_warmup_limit=20,
        ),
    )
    monkeypatch.setattr(
        validation,
        "ANALYTICS_CONFIG",
        replace(validation.ANALYTICS_CONFIG, indicator_warmup_limit=20),
    )
    with pytest.raises(AnalyticsInputError, match="warm-up exceeds"):
        analytics.compute_indicators(
            "AAA",
            "2024-01-02T03:45:00Z",
            "2024-01-02T03:46:00Z",
            ["EMA"],
            {"EMA": 3},
        )
