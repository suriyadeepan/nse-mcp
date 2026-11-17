"""Tests for DuckDB's local and S3 dataset configuration."""

from dataclasses import replace

import pytest

from src.server.config import ANALYTICS_CONFIG, load_analytics_config
from src.server.data import connect_duckdb, list_symbols, parquet_glob


def test_parquet_glob_uses_local_dataset_by_default(tmp_path):
    config = replace(ANALYTICS_CONFIG, processed_data_dir=tmp_path)

    assert parquet_glob(config) == f"{tmp_path}/**/*.parquet"


def test_data_source_is_selected_from_trusted_process_configuration():
    config = load_analytics_config({"PROCESSED_DATA_SOURCE": "s3"})

    assert config.processed_data_source == "s3"


def test_parquet_glob_builds_s3_url_from_trusted_config():
    config = replace(
        ANALYTICS_CONFIG,
        processed_data_source="s3",
        processed_data_s3_bucket="market-data-demo",
        processed_data_s3_prefix="/datasets/processed/",
    )

    assert parquet_glob(config) == (
        "s3://market-data-demo/datasets/processed/**/*.parquet"
    )


@pytest.mark.parametrize(
    "config, message",
    [
        (replace(ANALYTICS_CONFIG, processed_data_source="unknown"), "source"),
        (
            replace(
                ANALYTICS_CONFIG,
                processed_data_source="s3",
                processed_data_s3_bucket=None,
            ),
            "bucket",
        ),
        (
            replace(
                ANALYTICS_CONFIG,
                processed_data_source="s3",
                processed_data_s3_bucket="demo",
                processed_data_s3_prefix="/",
            ),
            "prefix",
        ),
    ],
)
def test_parquet_glob_rejects_incomplete_source_configuration(config, message):
    with pytest.raises(ValueError, match=message):
        parquet_glob(config)


def test_s3_connection_uses_credential_chain_without_inline_credentials(monkeypatch):
    import duckdb

    class FakeConnection:
        def __init__(self):
            self.statements = []
            self.closed = False

        def execute(self, statement):
            self.statements.append(statement)

        def close(self):
            self.closed = True

    fake = FakeConnection()
    monkeypatch.setattr(duckdb, "connect", lambda **_kwargs: fake)
    config = replace(
        ANALYTICS_CONFIG,
        processed_data_source="s3",
        processed_data_s3_bucket="market-data-demo",
    )

    assert connect_duckdb(config) is fake
    assert fake.statements == [
        "INSTALL httpfs",
        "LOAD httpfs",
        "CREATE SECRET s3_dataset (TYPE S3, PROVIDER credential_chain)",
    ]
    assert all("KEY_ID" not in statement and "SECRET '" not in statement for statement in fake.statements)


def test_s3_symbol_discovery_queries_hive_partition_values(monkeypatch):
    from src.server import data

    class FakeConnection:
        def __init__(self):
            self.query = None
            self.parameters = None
            self.closed = False

        def execute(self, query, parameters):
            self.query = query
            self.parameters = parameters
            return self

        def fetchall(self):
            return [("AAA",), ("BBB",)]

        def close(self):
            self.closed = True

    fake = FakeConnection()
    monkeypatch.setattr(data, "connect_duckdb", lambda _config: fake)
    config = replace(
        ANALYTICS_CONFIG,
        processed_data_source="s3",
        processed_data_s3_bucket="market-data-demo",
        processed_data_s3_prefix="datasets/processed",
    )

    assert list_symbols("unused-local-dir", config=config) == ["AAA", "BBB"]
    assert "FROM glob(?)" in fake.query
    assert "regexp_extract" in fake.query
    assert fake.parameters == [
        "s3://market-data-demo/datasets/processed/**/*.parquet"
    ]
    assert fake.closed
