# Tutorial: Run market data ingestion

The script reads `data/raw/*.parquet` files whose filename stem matches a
`Ticker` in `data/index/NIFTY50.csv`. Keep the raw files unchanged.

From the repository root, run:

```sh
python scripts/ingestion.py
```

The script writes valid bars to `data/processed/`, partitioned by interval,
year, month, and symbol. Rejected rows go to `data/rejects/SYMBOL.csv`; file
errors are recorded separately in `data/rejects/file_errors.log`. A JSON run
summary, including row counts and output paths, is printed to the terminal.

You can override the default paths when working with another dataset:

```sh
python scripts/ingestion.py \
  --raw-dir /path/to/raw \
  --processed-dir /path/to/processed \
  --rejects-dir /path/to/rejects \
  --index-csv /path/to/NIFTY50.csv
```

The command exits with status `1` if any in-scope file has a read, validation,
or output error; check the summary and `file_errors.log` for details.
