"""Data access layer for the server.

Reads parquet files from the configured data directory. `data/raw` is a symlink
to an external market data repository and is not committed to this repo.
"""

from pathlib import Path


def list_symbols(data_dir: str | Path) -> list[str]:
    """Return the stems of every parquet file in `data_dir`."""
    root = Path(data_dir)
    if not root.is_dir():
        raise FileNotFoundError(f"data directory not found: {root}")
    return sorted(path.stem for path in root.glob("*.parquet"))


def symbol_path(data_dir: str | Path, symbol: str) -> Path:
    """Resolve the parquet file backing `symbol`."""
    return Path(data_dir) / f"{symbol}.parquet"


def read_parquet(path: str | Path):
    """Read a parquet file into a DataFrame.

    Requires `pyarrow` at runtime.
    """
    try:
        import pyarrow.parquet as pq
    except ImportError as exc:  # pragma: no cover - depends on environment
        raise RuntimeError("pyarrow is required to read market data") from exc
    return pq.read_table(path).to_pandas()