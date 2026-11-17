"""Tests for the S3 partition pruning verification command."""

from dataclasses import replace

import pytest

from src.server.config import ANALYTICS_CONFIG
from scripts import verify_s3_partitions


class FakeConnection:
    def __init__(self, result, plan="File Filters: symbol, year, month"):
        self.result = result
        self.plan = plan
        self.calls = []
        self.closed = False

    def execute(self, query, parameters):
        self.calls.append((query, parameters))
        return self

    def fetchone(self):
        return self.result if len(self.calls) == 1 else ("explain", self.plan)

    def close(self):
        self.closed = True


def setup_command(monkeypatch, connection, argv=None, source="s3"):
    config = replace(
        ANALYTICS_CONFIG,
        processed_data_source=source,
        processed_data_s3_bucket="market-data-demo",
        processed_data_s3_prefix="datasets/processed",
    )
    monkeypatch.setattr(verify_s3_partitions, "load_analytics_config", lambda: config)
    monkeypatch.setattr(
        verify_s3_partitions, "connect_duckdb", lambda _config: connection
    )
    monkeypatch.setattr("sys.argv", ["verify_s3_partitions", *(argv or [])])


def test_verifier_checks_partition_values_and_prints_pruning_plan(monkeypatch, capsys):
    connection = FakeConnection(
        (3600, "2026-08-03", "2026-08-14", ["RELIANCE"], [2026], [8]),
        "File Filters: year=2026, month=8, symbol=RELIANCE; Scanning Files: 1/2781",
    )
    setup_command(monkeypatch, connection)

    verify_s3_partitions.main()

    output = capsys.readouterr().out
    assert "Verified 3,600 one-minute bars for RELIANCE, 2026-08" in output
    assert "Scanning Files: 1/2781" in output
    assert len(connection.calls) == 2
    assert connection.calls[0][1] == [
        "s3://market-data-demo/datasets/processed/**/*.parquet",
        "1m",
        2026,
        8,
        "RELIANCE",
    ]
    assert "year = ? AND month = ? AND symbol = ?" in connection.calls[0][0]
    assert connection.closed


@pytest.mark.parametrize(
    "result, message",
    [
        ((0, None, None, [], [], []), "No RELIANCE one-minute bars"),
        ((1, "2026-08-03", "2026-08-03", ["OTHER"], [2026], [8]),
         "outside the requested partitions"),
    ],
)
def test_verifier_fails_when_data_missing_or_partition_values_mismatch(
    monkeypatch, result, message
):
    connection = FakeConnection(result)
    setup_command(monkeypatch, connection)

    with pytest.raises(SystemExit, match=message):
        verify_s3_partitions.main()

    assert connection.closed


def test_verifier_requires_s3_source(monkeypatch, capsys):
    setup_command(monkeypatch, FakeConnection(None), source="local")

    with pytest.raises(SystemExit) as error:
        verify_s3_partitions.main()

    assert error.value.code == 2
    assert "set PROCESSED_DATA_SOURCE=s3" in capsys.readouterr().err
