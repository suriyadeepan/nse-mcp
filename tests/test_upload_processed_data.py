"""Tests for preserving the processed dataset layout during S3 upload."""

from pathlib import Path

import pytest

from scripts import upload_processed_data


def test_inventory_keeps_partitioned_parquet_files_and_symbols(tmp_path: Path):
    data_dir = tmp_path / "processed"
    parquet = data_dir / "interval=1m" / "year=2026" / "month=03" / "symbol=AAA" / "part-0.parquet"
    parquet.parent.mkdir(parents=True)
    parquet.touch()

    files, symbols = upload_processed_data.dataset_inventory(data_dir)

    assert files == [parquet]
    assert symbols == {"AAA"}


def test_upload_uses_sync_to_preserve_relative_partition_paths(tmp_path: Path, monkeypatch):
    data_dir = tmp_path / "processed"
    parquet = data_dir / "interval=1m" / "year=2026" / "month=03" / "symbol=AAA" / "part-0.parquet"
    parquet.parent.mkdir(parents=True)
    parquet.touch()
    commands = []
    monkeypatch.setattr(
        upload_processed_data.subprocess,
        "run",
        lambda command, check: commands.append((command, check)),
    )

    upload_processed_data.upload_dataset(data_dir, "market-data", "/dataset/processed/")

    assert commands == [
        (
            [
                "aws",
                "s3",
                "sync",
                str(data_dir),
                "s3://market-data/dataset/processed",
                "--exclude",
                "*.DS_Store",
            ],
            True,
        )
    ]


def test_upload_rejects_empty_dataset_before_calling_aws_cli(tmp_path: Path, monkeypatch):
    data_dir = tmp_path / "processed"
    data_dir.mkdir()
    monkeypatch.setattr(
        upload_processed_data.subprocess,
        "run",
        lambda *_args, **_kwargs: pytest.fail("AWS CLI must not run for empty datasets"),
    )

    with pytest.raises(ValueError, match="no Parquet files"):
        upload_processed_data.upload_dataset(data_dir, "market-data", "data/processed")


def test_delete_removes_only_normalized_dataset_prefix(monkeypatch):
    commands = []
    monkeypatch.setattr(
        upload_processed_data.subprocess,
        "run",
        lambda command, check: commands.append((command, check)),
    )

    upload_processed_data.delete_dataset("market-data", "/dataset/processed/")

    assert commands == [
        (["aws", "s3", "rm", "s3://market-data/dataset/processed", "--recursive"], True)
    ]


@pytest.mark.parametrize("bucket,prefix", [("market-data", "/"), ("market/data", "dataset")])
def test_delete_rejects_bucket_wide_or_malformed_scope(bucket, prefix, monkeypatch):
    monkeypatch.setattr(
        upload_processed_data.subprocess,
        "run",
        lambda *_args, **_kwargs: pytest.fail("AWS CLI must not run for unsafe delete scope"),
    )

    with pytest.raises(ValueError):
        upload_processed_data.delete_dataset(bucket, prefix)
