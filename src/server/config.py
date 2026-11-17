"""Shared configuration for analytics over processed market data."""

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class AnalyticsConfig:
    """Dataset location, execution limits, and indicator warm-up defaults."""

    processed_data_dir: Path = Path("data/processed")
    market_timezone: str = "Asia/Kolkata"
    max_date_range_days: int = 3650
    max_returned_rows: int = 100_000
    duckdb_memory_limit: str = "1GB"
    duckdb_threads: int = 4
    indicator_warmup_default: int = 250
    indicator_warmup_limit: int = 10_000


ANALYTICS_CONFIG = AnalyticsConfig()
