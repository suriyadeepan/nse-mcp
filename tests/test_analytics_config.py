"""Tests for shared analytics configuration and the DuckDB dependency."""

import duckdb

from src.server.config import ANALYTICS_CONFIG, AnalyticsConfig, load_analytics_config


def test_analytics_defaults_follow_processed_data_conventions():
    config = ANALYTICS_CONFIG

    assert config.processed_data_dir.as_posix() == "data/processed"
    assert config.market_timezone == "Asia/Kolkata"
    assert config.max_date_range_days > 0
    assert config.max_returned_rows > 0
    assert config.duckdb_memory_limit
    assert config.duckdb_threads > 0
    assert config.indicator_default_period > 0
    assert config.indicator_warmup_default > 0
    assert config.indicator_warmup_default <= config.indicator_warmup_limit


def test_analytics_configuration_is_immutable():
    config = AnalyticsConfig()

    try:
        config.duckdb_threads = 1
    except AttributeError:
        pass
    else:
        raise AssertionError("analytics configuration should be immutable")


def test_s3_dataset_location_comes_from_deployment_configuration():
    config = load_analytics_config(
        {
            "PROCESSED_DATA_S3_BUCKET": "market-data-demo",
            "PROCESSED_DATA_S3_PREFIX": "datasets/processed",
        }
    )

    assert config.processed_data_s3_bucket == "market-data-demo"
    assert config.processed_data_s3_prefix == "datasets/processed"


def test_s3_dataset_location_uses_configured_bucket_and_processed_prefix():
    config = load_analytics_config({})

    assert config.processed_data_s3_bucket == "nse-mcp-data"
    assert config.processed_data_s3_prefix == "data/processed"


def test_duckdb_dependency_can_open_configured_connection():
    config = ANALYTICS_CONFIG
    connection = duckdb.connect(
        ":memory:",
        config={
            "memory_limit": config.duckdb_memory_limit,
            "threads": str(config.duckdb_threads),
        },
    )
    try:
        assert connection.execute("SELECT 42").fetchone() == (42,)
    finally:
        connection.close()
