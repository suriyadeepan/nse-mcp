# Tutorial: Verify Remote Analytics Independently

This command checks the deployed `intraday_stats` MCP tool against values calculated independently from the local Parquet dataset. It also checks invalid-symbol rejection and scans the matching Lambda log events for credential-like content.

## Prerequisites

- Run commands from the repository root with the selected local partition available at `data/processed/interval=1m/year=2025/month=01/symbol=INFY/part.parquet`.
- Have a reachable deployed MCP endpoint and a current Terraform state containing its `mcp_endpoint_url` output.
- Have the matching bearer token in the protected, ignored `.env` file as `MCP_BEARER_TOKEN`. Do not paste the token into a command or print it.
- Have AWS CLI credentials configured for the deployment account and permission to call `logs:FilterLogEvents` on `/aws/lambda/kite-mcp` in `ap-south-1`.
- Use the project `uv` environment. No Terraform apply, deployment, dataset upload, or data mutation is part of this check.

If infrastructure is down or Terraform output is unavailable, the live check cannot run. Arrange any restoration separately before using this tutorial; the smoke command does not restore infrastructure.

## Run the smoke check

From the repository root:

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

The script reads `MCP_SERVER_URL`, `MCP_BEARER_TOKEN`, and `MCP_LAMBDA_LOG_GROUP` from the environment. It calls `intraday_stats` for `INFY` on `2025-01-01`, computes expected metrics from local PyArrow rows, submits a fixed invalid symbol, and queries CloudWatch for events containing each call's propagated request ID. Log lookup is bounded to the call's start time (with a two-minute lead-in) through query time; it retries briefly for CloudWatch ingestion delay.

The default absolute numeric tolerance is `1e-6`. Change it with `--tolerance VALUE`; each metric passes when its absolute difference is less than or equal to that value. Missing, nonnumeric, boolean, or non-finite metric values fail. The script does not print the endpoint, bearer token, raw error response, or raw CloudWatch events.

To run with a different local data root or endpoint, use `--data-dir PATH` or `--server ENDPOINT`. Keep credentials in environment variables; do not pass the bearer token as a command-line argument.

## Read the result

The JSON report contains separate `analytics`, `invalid_symbol`, and `cloudwatch` results. Individual checks use:

- `PASS`: the check's assertion succeeded.
- `FAIL`: the result contradicted an assertion, such as a metric outside tolerance, an accepted invalid symbol, or credential-like content in a correlated log event.
- `NOT RUN`: a prerequisite or query was unavailable, such as local data, the endpoint, AWS CLI, log configuration, or CloudWatch access.
- `UNVERIFIED`: the check ran but could not establish reliable evidence, such as finding no correlated log event.

Overall `PASS` means every required check passed. Overall `FAIL` means at least one assertion failed. Overall `INCOMPLETE` means required evidence was unavailable or unverified and no assertion failed. Exit codes are `0` for PASS, `1` for FAIL, and `2` for INCOMPLETE.

## Observed result

The authorized live run recorded in the [verification journal](008-independent-analytics-verification.md) passed all checks. For the selected date, 8 numeric metrics matched exactly and VWAP differed by about `2.27e-13`, within the `1e-6` tolerance. The invalid symbol was rejected cleanly, and both invocations had correlated CloudWatch events with no credential-like content. Automated regression coverage also passed with 31 tests using `uv run --with pytest`.
