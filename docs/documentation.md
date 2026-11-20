# Project documentation

This page summarizes the implemented features and their constraints. The original feature requirements, plans, task lists, and journals remain in `docs/` as the detailed record; task status stays canonical in each feature TODO.

## System overview

```text
raw Parquet + NIFTY50 index
        │ scripts/ingestion.py
        ▼
processed Parquet (interval/year/month/symbol)
        │ DuckDB, partition-pruned reads
        ▼
six analytics functions ── MCP server (stdio or Streamable HTTP)
                                  │ runtime tool discovery
                                  ▼
                         OpenAI client + optional Langfuse

Remote option: Lambda container + Function URL ── read-only S3 dataset
```

The local client and OpenAI agent remain outside Lambda. The server exposes the same analytics tools locally and remotely.

## Data ingestion

`scripts/ingestion.py` processes only raw Parquet files named by `Ticker` in `data/index/NIFTY50.csv`; it leaves raw files unchanged. It validates schema, timestamps, NSE session times and OHLCV values, then writes deterministic ZSTD Parquet partitions under `data/processed/`. Rejected rows and file errors are reported separately. See [ingestion tasks](F001-ingestion-todo.md) and [ingestion tutorial](tutorial-001-ingestion.md).

## Analytics API

`src/server/analytics.py` provides:

| Function | Purpose |
| --- | --- |
| `get_bars` | Ordered OHLCV candles for a bounded range |
| `intraday_stats` | Session OHLC, volume, VWAP and returns |
| `get_price_extremes` | High, low and their timestamps |
| `get_volume_stats` | Candle metrics and IST hourly/daily volume buckets |
| `compute_indicators` | SMA, EMA, RSI and ATR with prior-candle warm-up |
| `compare_symbols` | Daily comparison over common trading dates |

Timestamps are UTC-aware; trading dates and buckets use `Asia/Kolkata`. Unavailable metrics are `null`, never fabricated zeroes. Empty inputs return documented empty/null results. Invalid arguments and unavailable data use stable `invalid_input` and `data_unavailable` errors. Queries are predefined and parameterized; callers cannot supply SQL or filesystem paths. See [analytics result schemas](002-analytics-results.md), [analytics tasks](002-analytics-todo.md), and [analytics tutorial](tutorial-002-analytics.md).

## MCP server and client

The MCP server registers six read-only tools with typed schemas and supports stdio and Streamable HTTP at `/mcp`. The client discovers tools and schemas at runtime, converts them to OpenAI tool definitions, validates model arguments, executes calls, and supports bounded multi-tool conversations. The tool catalogue is not duplicated in client code.

Local client configuration uses `OPENAI_API_KEY`; remote connections use `MCP_SERVER_URL` and `MCP_BEARER_TOKEN`. The client retains a localhost default. Credentials are not written to logs or trace payloads. Optional Langfuse traces cover the query, model calls, MCP tool inputs/results and final answer, with credential redaction.

Related records: [server tasks](003-mcpserver-todo.md), [client tasks](004-mcpclient-todo.md), [Langfuse tasks](005-langfuse-todo.md), and [tutorials](tutorial.md).

## AWS deployment and remote verification

The active Terraform root is `terraform/`. It defines an ARM64 Lambda container, Function URL, scoped execution role/policy, invoke permissions and CloudWatch log group. The processed S3 bucket is a read-only input; Terraform's `removed` blocks use `destroy = false` for legacy bucket resources. Dataset upload is a separate, explicit operation.

The disposable Lambda deployment was torn down after the approved 2026-11-20 plan. Verification recorded seven demo resources destroyed, empty Terraform state, targeted AWS resource absence, and the preserved `data/processed/` baseline of 2,781 objects / 326,546,421 bytes. The remote endpoint is therefore not currently available; remote tutorials require a separately restored deployment.

Step 7 verified authenticated runtime discovery of all six tools, single- and multi-tool queries, and complete Langfuse traces. Step 8 verified remote analytics against independent local PyArrow results, invalid-symbol rejection, and correlated CloudWatch logs. Step 9 assembled the demo flow and recorded the approved teardown. See the detailed [Step 6](006-aws_lambda.md), [Step 7](007-remote-mcp-client.md), [Step 8](008-independent-analytics-verification.md), and [Step 9](009-demo-preparation.md) journals.

Before any Terraform apply or destroy, inspect the exact saved plan. Destroy requires explicit human approval of that plan; reject S3 deletion or unexpected resource actions. The S3 bucket and processed data must remain intact.

## Feature document map

| Feature | Detailed source documents |
| --- | --- |
| Ingestion | `F001-ingestion-todo.md`, `tutorial-001-ingestion.md` |
| Analytics | `002-analytics-results.md`, `002-analytics-todo.md`, `tutorial-002-analytics.md` |
| MCP server | `003-mcpserver-todo.md`, `tutorial-003-mcpserver.md` |
| MCP client | `004-mcpclient-todo.md`, `tutorial-004-mcpclient.md` |
| Langfuse | `005-langfuse-todo.md`, `tutorial-005-langfuse.md` |
| Lambda deployment | `006-aws_lambda-todo.md`, `006-aws_lambda.md` |
| Remote MCP client | `007-remote-mcp-client-requirements.md`, `007-remote-mcp-client-plan.md`, `007-remote-mcp-client-todo.md`, `007-remote-mcp-client.md`, `tutorial-007-remote-mcp-client.md` |
| Independent verification | `008-independent-analytics-verification-requirements.md`, `008-independent-analytics-verification-plan.md`, `008-independent-analytics-verification-todo.md`, `008-independent-analytics-verification.md`, `tutorial-008-independent-analytics-verification.md` |
| Demo preparation and teardown | `009-demo-preparation-requirements.md`, `009-demo-preparation-plan.md`, `009-demo-preparation-todo.md`, `009-demo-preparation.md` |

The original files are retained for full requirements, decisions, task lineage, commands and evidence. See [the consolidated tutorial](tutorial.md) for the user workflow.
