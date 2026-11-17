"""Shared configuration for analytics over processed market data."""

from dataclasses import dataclass
import os
from pathlib import Path
from collections.abc import Mapping


@dataclass(frozen=True)
class AnalyticsConfig:
    """Dataset location, execution limits, and indicator warm-up defaults."""

    processed_data_dir: Path = Path("data/processed")
    # Deployment-controlled location. These values must never come from tool
    # arguments, user prompts, or model-generated input.
    processed_data_s3_bucket: str | None = None
    processed_data_s3_prefix: str = "data/processed"
    processed_data_source: str = "local"
    market_timezone: str = "Asia/Kolkata"
    max_date_range_days: int = 3650
    max_returned_rows: int = 100_000
    duckdb_memory_limit: str = "1GB"
    duckdb_threads: int = 4
    indicator_default_period: int = 14
    indicator_warmup_default: int = 250
    indicator_warmup_limit: int = 10_000


def load_analytics_config(environ: Mapping[str, str] | None = None) -> AnalyticsConfig:
    """Load deployment settings from trusted process configuration."""
    settings = os.environ if environ is None else environ
    return AnalyticsConfig(
        processed_data_s3_bucket=settings.get("PROCESSED_DATA_S3_BUCKET",
                                              "nse-mcp-data"),
        processed_data_s3_prefix=settings.get(
            "PROCESSED_DATA_S3_PREFIX", "data/processed"
        ),
        processed_data_source=settings.get("PROCESSED_DATA_SOURCE", "local"),
    )


ANALYTICS_CONFIG = load_analytics_config()
