"""Data access helpers for local and S3-hosted processed Parquet datasets."""

from pathlib import Path

from .config import AnalyticsConfig, ANALYTICS_CONFIG


def parquet_glob(config: AnalyticsConfig = ANALYTICS_CONFIG) -> str:
    """Return the trusted local glob or S3 URL for the processed dataset."""
    if config.processed_data_source == "local":
        return str(config.processed_data_dir / "**" / "*.parquet")
    if config.processed_data_source != "s3":
        raise ValueError("processed data source must be 'local' or 's3'")
    bucket = config.processed_data_s3_bucket
    if not bucket:
        raise ValueError("S3 dataset bucket is not configured")
    prefix = config.processed_data_s3_prefix.strip("/")
    if not prefix:
        raise ValueError("S3 dataset prefix is not configured")
    return f"s3://{bucket}/{prefix}/**/*.parquet"


def connect_duckdb(config: AnalyticsConfig = ANALYTICS_CONFIG):
    """Open a bounded DuckDB connection, configuring AWS auth only for S3."""
    import duckdb

    connection = duckdb.connect(
        database=":memory:",
        config={
            "memory_limit": config.duckdb_memory_limit,
            "threads": str(config.duckdb_threads),
        },
    )
    if config.processed_data_source == "s3":
        try:
            connection.execute("INSTALL httpfs")
            connection.execute("LOAD httpfs")
            # DuckDB's AWS credential chain reads AWS CLI profiles locally and
            # Lambda execution-role credentials in the deployed runtime.
            connection.execute(
                "CREATE SECRET s3_dataset ("
                "TYPE S3, PROVIDER credential_chain)"
            )
        except Exception:
            connection.close()
            raise
    elif config.processed_data_source != "local":
        connection.close()
        raise ValueError("processed data source must be 'local' or 's3'")
    return connection


def list_symbols(
    data_dir: str | Path,
    *,
    config: AnalyticsConfig | None = None,
) -> list[str]:
    """Return symbols from local files or S3 Hive symbol partitions."""
    if config is not None and config.processed_data_source == "s3":
        connection = connect_duckdb(config)
        try:
            rows = connection.execute(
                "SELECT DISTINCT regexp_extract(file, 'symbol=([^/]+)/', 1) "
                "AS symbol FROM glob(?) WHERE symbol <> '' ORDER BY symbol",
                [parquet_glob(config)],
            ).fetchall()
            return [row[0] for row in rows]
        finally:
            connection.close()

    root = Path(data_dir)
    if not root.is_dir():
        raise FileNotFoundError(f"data directory not found: {root}")

    symbols = {path.stem for path in root.glob("*.parquet")}
    for parquet_path in root.rglob("*.parquet"):
        relative_parts = parquet_path.relative_to(root).parts
        for part in relative_parts:
            if part.startswith("symbol="):
                symbol = part.removeprefix("symbol=")
                if symbol:
                    symbols.add(symbol)
                break
    return sorted(symbols)


def symbol_path(data_dir: str | Path, symbol: str) -> Path:
    """Resolve the parquet file backing `symbol`."""
    return Path(data_dir) / f"{symbol}.parquet"


def read_parquet(path: str | Path):
    """Read a local parquet file into a DataFrame.

    Requires `pyarrow` at runtime.
    """
    try:
        import pyarrow.parquet as pq
    except ImportError as exc:  # pragma: no cover - depends on environment
        raise RuntimeError("pyarrow is required to read market data") from exc
    return pq.read_table(path).to_pandas()
