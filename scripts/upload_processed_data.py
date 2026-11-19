"""Validate and upload the complete processed dataset to S3."""

from __future__ import annotations

import argparse
from pathlib import Path
import subprocess


def dataset_inventory(data_dir: str | Path) -> tuple[list[Path], set[str]]:
    """Return Parquet files and symbols found in Hive partition paths."""
    root = Path(data_dir)
    if not root.is_dir():
        raise FileNotFoundError(f"processed dataset directory not found: {root}")
    files = sorted(root.rglob("*.parquet"))
    symbols = {
        part.removeprefix("symbol=")
        for parquet in files
        for part in parquet.relative_to(root).parts
        if part.startswith("symbol=") and part.removeprefix("symbol=")
    }
    return files, symbols


def validate_dataset(data_dir: str | Path) -> list[Path]:
    """Reject empty datasets before uploading."""
    files, _symbols = dataset_inventory(data_dir)
    if not files:
        raise ValueError("processed dataset contains no Parquet files")
    return files


def upload_dataset(data_dir: str | Path, bucket: str, prefix: str) -> None:
    """Use AWS CLI sync to retain local partition paths as S3 object keys."""
    source = Path(data_dir)
    validate_dataset(source)
    destination = (
        f"s3://{bucket}/{prefix.strip('/')}" if prefix.strip("/") else f"s3://{bucket}"
    )
    subprocess.run(
        [
            "aws",
            "s3",
            "sync",
            str(source),
            destination,
            "--exclude",
            "*.DS_Store",
        ],
        check=True,
    )


def delete_dataset(bucket: str, prefix: str) -> None:
    """Remove only the configured dataset prefix from S3."""
    normalized_prefix = prefix.strip("/")
    if not bucket or "/" in bucket or not normalized_prefix:
        raise ValueError("bucket and a non-empty dataset prefix are required")
    subprocess.run(
        ["aws", "s3", "rm", f"s3://{bucket}/{normalized_prefix}", "--recursive"],
        check=True,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", default="data/processed")
    parser.add_argument("--bucket", default=None)
    parser.add_argument("--prefix", default="data/processed")
    parser.add_argument("--delete", action="store_true")
    args = parser.parse_args()
    import os

    bucket = args.bucket or os.environ.get("S3_BUCKET")
    prefix = os.environ.get("S3_PREFIX", args.prefix)
    if not bucket:
        parser.error("--bucket or S3_BUCKET is required")
    if args.delete:
        delete_dataset(bucket, prefix)
    else:
        upload_dataset(args.data_dir, bucket, prefix)


if __name__ == "__main__":
    main()
