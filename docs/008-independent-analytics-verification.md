# Step 8: Independent Analytics Verification Journal

## Deterministic analytics input

Selected the `intraday_stats` MCP tool with `symbol=INFY` and `trading_date=2025-01-01`. The existing Pydantic schema accepts a nonempty listed symbol and a `YYYY-MM-DD` date; the registered MCP tool uses structured output. The corresponding local partition is `data/processed/interval=1m/year=2025/month=01/symbol=INFY/part.parquet`, which contains the required raw columns (`symbol`, UTC `timestamp`, `trading_date`, `open`, `high`, `low`, `close`, and `volume`). The inclusive IST date has 375 local rows.

Expected values for the selected tool will be computed directly from PyArrow rows, without Pandas or the server's DuckDB query. Sort by `(timestamp, open, high, low, close, volume)` so duplicate timestamps have deterministic ordering. The session open is the first row's `open`; close is the last row's `close`; high and low are the maximum `high` and minimum `low`; total volume is the sum of `volume`; VWAP is `sum(((high + low + close) / 3) * volume) / sum(volume)`; absolute return is `close - open`; percentage return is `(close / open - 1) * 100` when open is nonzero; bar count is row count. Earliest and latest timestamps are the first and last timestamps under that ordering.

A local PyArrow calculation produced: open `1834.3`, close `1845.1`, high `1852.9`, low `1834.3`, total volume `1833614`, VWAP `1845.1790253564818`, absolute return `10.799999999999955`, percentage return `0.5887804612113579`, bar count `375`, first timestamp `2025-01-01T03:45:00Z`, and last timestamp `2025-01-01T09:59:00Z`. These are local reference values only, not a live comparison.

## Compatibility and initial deployment snapshot

The configured deployment defaults to S3 prefix `data/processed`, matching the local Hive partition layout. At initial implementation, the repo recorded that the demo Lambda resources had been manually destroyed. The selected symbol/date were confirmed in local data and the remote tool's input schema; live availability had not been checked. This was a point-in-time snapshot, later superseded by the authorized restoration and live run below.

Automated verification at implementation: `uv run python -c 'import pyarrow.parquet as pq; ...'` (local partition schema, rows, and metrics inspected successfully). At that point, live remote analytics, invalid-input, and CloudWatch checks had not been run.

## Deterministic comparison command

Implemented `scripts/verify_remote_analytics.py`. It calls `intraday_stats` directly through the existing MCP Streamable HTTP client API, without listing tools, OpenAI selection, Pandas, or the server DuckDB query. Expected values are computed from PyArrow rows using the formulas and deterministic ordering above. Numeric result fields are compared with a configurable absolute tolerance (default `1e-6`); missing, boolean, or non-finite actual values fail. JSON output includes fixed inputs, expected and actual values, differences, tolerance, and per-field status. Connection/tool failures produce a generic reason rather than raw exception text.

Usage: `uv run python scripts/verify_remote_analytics.py [--server ENDPOINT] [--data-dir PATH] [--tolerance VALUE]`. The endpoint and optional bearer token are read from `MCP_SERVER_URL` and `MCP_BEARER_TOKEN`; the script does not print either. No live comparison had been run at this implementation stage; the later live run is recorded below.

Command check: `uv run python scripts/verify_remote_analytics.py --help` completed successfully. No remote request was made.

## Invalid-symbol rejection

The command submits `__KITE_INVALID_SYMBOL__` to `intraday_stats` at the same configured MCP endpoint. It passes only when the tool returns an error with a recognized clean validation message (`unknown symbol` or `invalid symbol`). Acceptance, unrecognized errors, traceback/internal detail, bearer credentials, and credential-like fields fail. The report includes only a fixed status and reason; it never includes the response text. Analytics actual values are also restricted to the expected numeric fields and invalid/non-numeric values are omitted from emitted actual values.

Regression coverage at this implementation stage: `uv run --with pytest pytest tests/test_verify_remote_analytics.py` — 9 passed. `uv run pytest ...` initially could not find pytest in the project environment; the `--with pytest` overlay enabled the prescribed uv run without changing project dependencies or the lockfile. The live invalid-symbol result was not yet available; it is recorded in the later live-verification section.

## Request correlation and CloudWatch lookup

The MCP response does not provide a dependable Lambda request ID through the existing client API. The command generates a UUID for each tool call, sends it as `X-Kite-Request-Id`, records the UTC start timestamp immediately before `client.call_tool`, and retains response request IDs from `x-amzn-requestid` / `x-amz-apigw-id` headers when present. The request ID is logged by `RequestCorrelationMiddleware` only after bearer authentication and only when it is a UUID; no authorization data or arbitrary header values are logged. Tool calls use the MCP SDK's declared `arguments` object wrapper, as confirmed by the existing HTTP integration test.

CloudWatch lookup uses AWS CLI `logs filter-log-events` for the configured `MCP_LAMBDA_LOG_GROUP`, or `/aws/lambda/$MCP_LAMBDA_FUNCTION_NAME`, bounded from two minutes before the call start through query time. Only events containing the exact propagated UUID are scanned. A match passes only if no bearer token or credential-like text is found. Missing configuration/CLI/access reports NOT RUN; an executed query with no correlated events reports UNVERIFIED. AWS errors and raw event text are never emitted.

Regression verification: `uv run --with pytest pytest tests/test_verify_remote_analytics.py tests/test_http.py` — 16 passed. `uv run python scripts/verify_remote_analytics.py --help` succeeded; `git diff --check` passed. The first combined HTTP test attempt exposed MCP ASGI host validation and a shared server lifespan constraint in the test setup; the regression now uses an isolated MCP app with its configured localhost host, and the focused suite passes. No remote MCP request or AWS query was made; live correlation remains unverified for T007.

## Unified report and regression coverage

The command emits independent `analytics`, `invalid_symbol`, and `cloudwatch` checks, each with `PASS`, `FAIL`, `NOT RUN`, or `UNVERIFIED` plus a reason. Analytics reports expected/actual numeric values and per-field differences. `PASS` is returned only when all required checks pass; assertion failures produce overall `FAIL`; unavailable or unverified required evidence produces `INCOMPLETE` unless another check already failed. Exit codes are 0 for PASS, 1 for FAIL, and 2 for INCOMPLETE. Remote connection/tool unavailability is reported without exception text, and the command continues to report the other checks where possible.

Normal repeat command (from the repository root, after the prerequisites described in the tutorial are available):

```sh
(
  set -eu
  set -a
  . ./.env
  set +a
  export MCP_SERVER_URL="$(terraform -chdir=terraform output -raw mcp_endpoint_url)"
  export MCP_LAMBDA_LOG_GROUP=/aws/lambda/kite-mcp
  export AWS_REGION=ap-south-1
  export AWS_DEFAULT_REGION="$AWS_REGION"
  uv run python scripts/verify_remote_analytics.py
)
```

The protected `.env` supplies `MCP_BEARER_TOKEN`; the endpoint is read from Terraform output rather than copied into a command. The smoke script emits only verification results and non-secret request metadata. If the deployment or Terraform output is unavailable, do not restore or deploy infrastructure as part of this verification command; arrange that operation separately.

Automated regression coverage at this implementation stage included independent PyArrow formulas and tie ordering, tolerance boundaries, missing/boolean/non-finite numbers, clean and unsafe invalid-symbol responses, propagated/request response IDs, CloudWatch correlation and credential scanning, unavailable logs, overall status transitions, and redacted report behavior. Commands: `uv run --with pytest pytest tests/test_verify_remote_analytics.py tests/test_http.py` — 30 passed; `uv run python scripts/verify_remote_analytics.py --help` succeeded; `git diff --check` passed. The project environment does not include pytest, so the temporary `--with pytest` uv overlay was used without changing `pyproject.toml` or `uv.lock`. At that stage no live remote or AWS verification had been performed; subsequent live evidence is recorded below.

## Live verification attempt and prerequisite status

T007 prerequisite inspection found the selected local Parquet partition present. AWS CLI is installed locally (`aws-cli/2.40.2`). `MCP_SERVER_URL` is present in the repository's `.env`, but it is not exported in this shell; the verification script does not load `.env` automatically. No Lambda log group or function name is configured in the shell or repository environment files. The user reported the Lambda resources were destroyed. The smoke command was not run: it would require a live MCP request and CloudWatch query, and the prior instruction for this work was to avoid live MCP/AWS queries while the deployment is down. AWS credentials/access and remote deployment/log availability therefore remain unchecked.

Live results are recorded separately from automated evidence:

- Analytics comparison: **NOT RUN** — deployment availability was not probed; no actual remote values or differences were produced. Local expected values remain the reference values listed above.
- Invalid-symbol request: **NOT RUN** — no remote MCP request was sent.
- CloudWatch correlation and credential scan: **NOT RUN** — no AWS query was sent, and no log group/function configuration is available in the environment.

The endpoint URL, bearer token, account identity, and credentials were not printed or queried. To obtain live evidence later, first restore the deployment through a separately reviewed and explicitly approved infrastructure plan, configure the endpoint and log group, then run `uv run python scripts/verify_remote_analytics.py` with the protected environment configured. No restoration, deployment, or infrastructure operation was performed for T007.

## Live verification after authorized restoration

The user authorized restoring the infrastructure and running live verification. Terraform planned and created 7 resources (Lambda, Function URL, log group, execution role and inline policy, and two Function URL permissions), with no destroys. The role policy grants `s3:ListBucket` limited by `s3:prefix` to `data/processed` and its descendants, `s3:GetObject` only under `data/processed/*`, and `logs:CreateLogGroup`, `logs:CreateLogStream`, and `logs:PutLogEvents` for this Lambda log group. The Function URL is publicly invokable at the AWS layer (`AuthType=NONE`); application bearer authentication remains enabled.

Two in-place Lambda updates followed. First, `MCP_FUNCTION_URL_HOST` was changed to the newly generated Function URL host after an initialize request returned HTTP 421; the configured host had referred to the previous URL. Second, the Lambda image was updated to include the tested request-correlation middleware. The final image is `025232685609.dkr.ecr.ap-south-1.amazonaws.com/kite-mcp@sha256:c948fb845c5016afa80c1b9dc2b753f76a2c19aa6ce762fb696a11f1c3fac605`. The first build included an OCI image index with an attestation, which Lambda rejected; rebuilding for `linux/arm64` with `--provenance=false --sbom=false` produced a Docker v2 image manifest Lambda accepted. No dataset or Terraform source files were changed; deployment inputs in the ignored local `terraform/terraform.tfvars` now match the restored endpoint and final image.

The smoke command was run with `MCP_SERVER_URL` from Terraform output, `MCP_LAMBDA_LOG_GROUP=/aws/lambda/kite-mcp`, the protected `.env` bearer token, and `AWS_REGION=ap-south-1` / `AWS_DEFAULT_REGION=ap-south-1`. The AWS region was required because the CLI had no default configured. The CloudWatch filter now quotes UUIDs and retries up to five times at two-second intervals to allow for log ingestion delay; a manual query of earlier invocations confirmed that exact-ID events appeared after the initial query. The final live run completed at `2026-11-19 23:30 UTC` with overall **PASS**:

| Metric | Local expected | Remote actual | Absolute difference | Result |
| --- | ---: | ---: | ---: | --- |
| open | 1834.3 | 1834.3 | 0 | PASS |
| close | 1845.1 | 1845.1 | 0 | PASS |
| high | 1852.9 | 1852.9 | 0 | PASS |
| low | 1834.3 | 1834.3 | 0 | PASS |
| total_volume | 1833614 | 1833614.0 | 0 | PASS |
| vwap | 1845.1790253564818 | 1845.1790253564816 | 2.2737367544323206e-13 | PASS |
| absolute_return | 10.799999999999955 | 10.799999999999955 | 0 | PASS |
| percentage_return | 0.5887804612113579 | 0.5887804612113579 | 0 | PASS |
| bar_count | 375 | 375 | 0 | PASS |

The configured absolute tolerance was `1e-6`. The fixed invalid symbol `__KITE_INVALID_SYMBOL__` was cleanly rejected (**PASS**). CloudWatch found and scanned the correlated events for both calls (**PASS**); no bearer token or credential-like content was found. Propagated IDs were `28720413-8fe2-4085-93d8-4c4efa2ca00c` for analytics and `10d6c1f2-d5f0-475c-8701-91e4709bd9f9` for invalid-symbol rejection. Their call start times were `2026-11-19T23:29:56.562277+00:00` and `2026-11-19T23:29:58.881653+00:00`, respectively. The report’s service response IDs were captured separately; CloudWatch matching used the propagated IDs.

The filter-quoting and delayed-ingestion behavior are covered by persistent regression tests. `uv run --with pytest pytest tests/test_verify_remote_analytics.py tests/test_http.py` — **31 passed**. No credentials, raw CloudWatch messages, or authorization headers were recorded here.
