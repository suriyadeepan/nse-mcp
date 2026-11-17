"""Tests for daily multi-symbol performance and risk comparisons."""

from dataclasses import replace
from datetime import date, datetime, timezone

import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from src.server import analytics, validation
from src.server.validation import AnalyticsInputError


@pytest.fixture
def comparison_dataset(tmp_path, monkeypatch):
    rows = [
        ("AAA", date(2024, 1, 1), 100.0, 10),
        ("AAA", date(2024, 1, 2), 110.0, 20),
        ("AAA", date(2024, 1, 4), 99.0, 30),
        ("BBB", date(2024, 1, 1), 200.0, 5),
        ("BBB", date(2024, 1, 2), 220.0, 10),
        # This date is missing for AAA and must not become a zero return.
        ("BBB", date(2024, 1, 3), 230.0, 15),
        ("BBB", date(2024, 1, 4), 242.0, 20),
    ]
    for symbol in ("AAA", "BBB"):
        symbol_rows = [row for row in rows if row[0] == symbol]
        path = (
            tmp_path
            / "interval=1m"
            / "year=2024"
            / "month=01"
            / f"symbol={symbol}"
            / "part.parquet"
        )
        path.parent.mkdir(parents=True)
        pq.write_table(
            pa.table(
                {
                    "symbol": pa.array([row[0] for row in symbol_rows]),
                    "timestamp": pa.array(
                        [
                            datetime.combine(row[1], datetime.min.time()).replace(
                                hour=3, minute=45, tzinfo=timezone.utc
                            )
                            for row in symbol_rows
                        ],
                        type=pa.timestamp("us", tz="UTC"),
                    ),
                    "trading_date": pa.array(
                        [row[1] for row in symbol_rows], type=pa.date32()
                    ),
                    "open": pa.array([row[2] for row in symbol_rows]),
                    "high": pa.array([row[2] + 1 for row in symbol_rows]),
                    "low": pa.array([row[2] - 1 for row in symbol_rows]),
                    "close": pa.array([row[2] for row in symbol_rows]),
                    "volume": pa.array([row[3] for row in symbol_rows]),
                }
            ),
            path,
        )
        boundary_path = (
            tmp_path
            / "interval=1m"
            / "year=2024"
            / "month=02"
            / f"symbol={symbol}"
            / "part.parquet"
        )
        boundary_path.parent.mkdir(parents=True)
        boundary_close = 50.0 if symbol == "AAA" else 75.0
        pq.write_table(
            pa.table(
                {
                    "symbol": [symbol],
                    "timestamp": pa.array(
                        [datetime(2024, 2, 1, 3, 45, tzinfo=timezone.utc)],
                        type=pa.timestamp("us", tz="UTC"),
                    ),
                    "trading_date": pa.array([date(2024, 2, 1)], type=pa.date32()),
                    "open": [boundary_close],
                    "high": [boundary_close + 1],
                    "low": [boundary_close - 1],
                    "close": [boundary_close],
                    "volume": [1],
                }
            ),
            boundary_path,
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


def test_compare_symbols_uses_common_dates_and_calculates_metrics(comparison_dataset):
    result = analytics.compare_symbols(
        ["AAA", "BBB"],
        "2024-01-01T00:00:00Z",
        "2024-01-04T23:59:59Z",
    )

    assert result["common_trading_dates"] == [
        date(2024, 1, 1),
        date(2024, 1, 2),
        date(2024, 1, 4),
    ]
    assert result["common_trading_days"] == 3
    by_symbol = {row["symbol"]: row for row in result["symbols"]}
    assert by_symbol["AAA"] == {
        "symbol": "AAA",
        "rank": 2,
        "status": "ready",
        "common_trading_days": 3,
        "total_return_pct": pytest.approx(-1.0),
        "average_daily_return_pct": pytest.approx(0.0),
        "annualized_volatility_pct": pytest.approx((0.02**0.5) * (252**0.5) * 100),
        "maximum_drawdown_pct": pytest.approx(-10.0),
        "total_volume": 60.0,
        "average_daily_volume": 20.0,
        "average_daily_turnover": pytest.approx(2056.6666666666665),
    }
    assert by_symbol["BBB"]["rank"] == 1
    assert by_symbol["BBB"]["total_return_pct"] == pytest.approx(21.0)
    assert by_symbol["BBB"]["average_daily_return_pct"] == pytest.approx(10.0)
    assert by_symbol["BBB"]["annualized_volatility_pct"] == pytest.approx(0.0)
    assert by_symbol["BBB"]["maximum_drawdown_pct"] == pytest.approx(0.0)
    assert by_symbol["BBB"]["average_daily_turnover"] == pytest.approx(2680.0)


def test_compare_symbols_marks_single_common_close_insufficient(comparison_dataset):
    result = analytics.compare_symbols(
        ["AAA", "BBB"], "2024-01-01T00:00:00Z", "2024-01-01T18:29:59Z"
    )

    assert result["common_trading_dates"] == [date(2024, 1, 1)]
    for row in result["symbols"]:
        assert row["status"] == "insufficient_history"
        assert row["rank"] is None
        assert row["total_return_pct"] is None
        assert row["average_daily_return_pct"] is None
        assert row["annualized_volatility_pct"] is None
        assert row["maximum_drawdown_pct"] is None
        assert row["average_daily_volume"] is not None

    two_days = analytics.compare_symbols(
        ["AAA", "BBB"], "2024-01-01T00:00:00Z", "2024-01-02T18:29:59Z"
    )
    assert two_days["common_trading_days"] == 2
    assert two_days["symbols"][0]["status"] == "insufficient_history"
    assert two_days["symbols"][0]["annualized_volatility_pct"] is None
    assert two_days["symbols"][0]["total_return_pct"] is not None


def test_compare_symbols_prunes_partitions_for_ist_date_boundaries(comparison_dataset):
    result = analytics.compare_symbols(
        ["AAA", "BBB"], "2024-01-31T18:30:00Z", "2024-01-31T23:59:59Z"
    )

    assert result["common_trading_dates"] == [date(2024, 2, 1)]
    assert result["common_trading_days"] == 1


def test_compare_symbols_handles_empty_intersection_and_validates_inputs(
    comparison_dataset,
):
    empty = analytics.compare_symbols(
        ["AAA", "BBB"], "2024-02-02T00:00:00Z", "2024-02-03T00:00:00Z"
    )
    assert empty["common_trading_dates"] == []
    assert all(row["common_trading_days"] == 0 for row in empty["symbols"])
    assert all(row["status"] == "insufficient_history" for row in empty["symbols"])

    with pytest.raises(AnalyticsInputError, match="at least 2"):
        analytics.compare_symbols(["AAA"], "2024-01-01T00:00:00Z", "2024-01-02T00:00:00Z")
    with pytest.raises(AnalyticsInputError, match="unknown symbol"):
        analytics.compare_symbols(
            ["AAA", "BAD"], "2024-01-01T00:00:00Z", "2024-01-02T00:00:00Z"
        )
    with pytest.raises(AnalyticsInputError, match="duplicates"):
        analytics.compare_symbols(
            ["AAA", "AAA"], "2024-01-01T00:00:00Z", "2024-01-02T00:00:00Z"
        )
    with pytest.raises(AnalyticsInputError, match="interval"):
        analytics.compare_symbols(
            ["AAA", "BBB"],
            "2024-01-01T00:00:00Z",
            "2024-01-02T00:00:00Z",
            "monthly",
        )
