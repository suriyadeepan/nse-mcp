# Tutorial 003: Manually verify the MCP server

This walkthrough checks the read-only requirements in task 6 and the MCP behavior in task 7. It uses the MCP Python client already installed by `uv sync`. Run commands from the repository root.

## 1. Prepare known data

The server reads Parquet files under `data/processed` and only accepts symbols found there. See which symbols and data dates are available:

```sh
uv run python -c 'from server.data import list_symbols; from server.config import ANALYTICS_CONFIG; print(ANALYTICS_CONFIG.processed_data_dir); print(sorted(list_symbols(ANALYTICS_CONFIG.processed_data_dir)))'
```

The examples below use `RELIANCE` and `TCS`, both NIFTY 50 constituents. Index membership can change; check the [official NIFTY 50 constituent page](https://www.niftyindices.com/indices/equity/broad-based-indices/NIFTY--50) and your local symbol list. Choose a date range present in your local data and an otherwise-valid range with no rows for the empty-result check.

## 2. Check the tool menu and schemas

Start the server over stdio:

```sh
uv run kite-mcp
```

It waits for MCP messages on stdin; it does not present a shell prompt. Connect using an MCP client or the MCP Inspector configured to launch `uv run kite-mcp`. Call `tools/list` and confirm the server advertises exactly these six tools, each with a description and an input schema:

| Tool | Required input fields |
| --- | --- |
| `get_bars` | `symbol`, `start_datetime`, `end_datetime`, `limit` |
| `intraday_stats` | `symbol`, `trading_date` |
| `get_price_extremes` | `symbol`, `start_datetime`, `end_datetime` |
| `get_volume_stats` | `symbol`, `start_datetime`, `end_datetime`, `bucket` |
| `compute_indicators` | `symbol`, `start_datetime`, `end_datetime`, `indicators` |
| `compare_symbols` | `symbols`, `start_datetime`, `end_datetime` |

Use timezone-aware ISO-8601 timestamps for the range fields. For example: `2024-01-01T00:00:00Z` and `2024-01-31T23:59:59Z`.

## 3. Call all six tools with valid input

Call each tool with these inputs, substituting dates with a range present in your local data:

```json
{"symbol":"RELIANCE","start_datetime":"2024-01-01T00:00:00Z","end_datetime":"2024-01-31T23:59:59Z","limit":10}
```

Use that input for `get_bars`. Expected: structured output with `bars` and `returned_count`.

```json
{"symbol":"RELIANCE","trading_date":"2024-01-15"}
```

Use that input for `intraday_stats`. Expected: structured session fields, including OHLC, volume, and bar count.

```json
{"symbol":"RELIANCE","start_datetime":"2024-01-01T00:00:00Z","end_datetime":"2024-01-31T23:59:59Z"}
```

Use that input for `get_price_extremes`. Expected: extreme prices and timestamps (or null values if the range is empty).

```json
{"symbol":"RELIANCE","start_datetime":"2024-01-01T00:00:00Z","end_datetime":"2024-01-31T23:59:59Z","bucket":"daily"}
```

Use that input for `get_volume_stats`. `bucket` may be `daily` or `hourly`.

```json
{"symbol":"RELIANCE","start_datetime":"2024-01-01T00:00:00Z","end_datetime":"2024-01-31T23:59:59Z","indicators":["SMA"]}
```

Use that input for `compute_indicators`. Supported names are `SMA`, `EMA`, `RSI`, and `ATR`.

```json
{"symbols":["RELIANCE","TCS"],"start_datetime":"2024-01-01T00:00:00Z","end_datetime":"2024-01-31T23:59:59Z"}
```

Use that input for `compare_symbols`. Expected: comparison fields for both symbols and their common dates.

For every call, confirm the client reports success and shows structured content rather than only an unstructured error.

## 4. Check invalid inputs and empty results

Try these invalid calls and confirm each returns an error without a traceback or internal query details:

- `get_bars` with `limit: 0`.
- `get_volume_stats` with `bucket: "weekly"`.
- `compute_indicators` with `indicators: ["NOT_AN_INDICATOR"]`.
- `compare_symbols` with only one symbol.
- Any tool with an extra field such as `"sql":"select 1"` or `"path":"/tmp/file"`.
- A syntactically valid but unlisted symbol such as `"MISSING"`.

Then repeat valid calls using a time range with no matching rows. Empty results should still be successful structured results: lists should be empty, counts zero, and unavailable numeric summaries null where appropriate. The server should not turn an empty dataset into a tool error.

## 5. Check execution errors safely

To exercise an actual data/query failure, temporarily move the processed-data directory out of the way, make one valid tool call, and restore it immediately afterward. For example, stop the stdio server, then:

```sh
mv data/processed data/processed.manual-backup
uv run kite-mcp
```

Call `get_bars` using a valid-looking input and confirm the client receives a clear analytics/data error, not a traceback or filesystem details. Stop the server, restore the directory, and verify restoration:

```sh
mv data/processed.manual-backup data/processed
```

Only do this if you have a `data/processed` directory and can safely restore it. If your dataset is disposable or important to another process, skip this step and use the automated execution-error test instead.

## 6. Repeat over Streamable HTTP

In one terminal, start the ASGI app:

```sh
uv run uvicorn server.main:app --host 127.0.0.1 --port 8000
```

Connect the MCP Inspector/client to `http://127.0.0.1:8000/mcp`. Repeat sections 2–5: discover all six tools, perform valid and invalid calls, check an empty range, and (if safe) check a data/query failure. Confirm the same structured results and safe errors appear over HTTP as over stdio.

## 7. Check the read-only boundary

The advertised schemas should contain only the fields listed in section 2. The extra-field probes in section 4 should be rejected. This checks that callers cannot supply arbitrary SQL or a filesystem path through the MCP interface.

For a stronger local check, inspect the implementation:

```sh
rg -n 'INSERT|UPDATE|DELETE|CREATE|DROP|COPY|write_|to_parquet|to_csv|open\(' src/server
```

Review every match rather than relying only on the search result: the analytics path should issue predefined read queries against configured Parquet data. Tool code should not accept SQL/path parameters or write to the database/filesystem. A text search is a review aid, not proof; check the actual call paths in `src/server/tools.py`, `src/server/analytics.py`, and `src/server/queries.py`.

## 8. Run the automated checks

After the manual checks, run the MCP integration tests and analytics tests:

```sh
uv run pytest -q tests/test_mcp_server.py tests/test_analytics_*.py tests/test_validation_schemas.py
```

Manual checks complement these tests. They help verify that real clients see consistent behavior through both transports; they do not replace automated regression coverage.
