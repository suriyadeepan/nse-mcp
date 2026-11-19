# Step 8: Independent Analytics Verification Requirements

## Objective

**R001 — Verify remote analytics against local data:** Verify that remote MCP analytics results are numerically correct against expected values derived independently from the local Parquet dataset.

## Requirements

- **R002 — Verify analytical correctness (T001):** Run one deterministic analytics query through the remote MCP client against the deployed S3 dataset. Independently calculate expected values from local Parquet data. Compare corresponding numeric fields using a configurable tolerance. Report expected values, actual values, differences and PASS/FAIL.
- **R003 — Verify invalid-input rejection (T002):** Submit an invalid symbol through the remote MCP endpoint. Confirm the server rejects it cleanly without exposing internal details or credentials.
- **R004 — Verify runtime logging (T003):** Confirm CloudWatch contains the corresponding Lambda invocation. Capture the Lambda request start timestamp immediately before each MCP call, capture the MCP response and its request/correlation identifier if available, and query CloudWatch within a bounded time window. Match using the Lambda request ID from response metadata or a unique request identifier propagated into logs. Ensure logs do not expose bearer tokens or other credentials. If no reliable identifier is available, report correlation as UNVERIFIED rather than claiming a match.
- **R005 — Produce verification report (T004):** Add a small deterministic smoke-test command. Report PASS/FAIL separately for analytical correctness, invalid-input rejection and CloudWatch verification. Clearly distinguish PASS, FAIL, NOT RUN and UNVERIFIED checks. Never fabricate passing results.

## Acceptance criteria

- **R006:** Remote analytics values match independently calculated local Parquet values within the configured tolerance.
- **R007:** Invalid symbols are rejected cleanly.
- **R008:** CloudWatch confirms the corresponding Lambda invocation using a reliable correlation identifier; absent one, correlation is reported as UNVERIFIED.
- **R009:** The verification report records actual results and failures.

## Scope exclusions

- **R010:** No repeated MCP discovery, OpenAI tool-selection, multi-tool workflow or Langfuse testing; these are covered by Step 7.
- **R011:** No external market-data requests; use only the existing dataset.

## Repository observations

- The analytics service reads processed Parquet data through `src/server/data.py` and `src/server/analytics.py`; `src/server/queries.py` contains the DuckDB query implementations.
- Local processed Parquet data exists under `data/processed`; deployment uses the configured S3 prefix in Terraform.
- PyArrow is already a project dependency and `src/server/data.py` uses it to read local Parquet files. No Pandas ground-truth function or Pandas dependency is needed for this feature.
- The Step 7 remote MCP client and Lambda Function URL configuration already exist.
- Terraform defines the Lambda log group as `/aws/lambda/${var.lambda_function_name}`. The user reports that the demo Lambda resources have since been manually destroyed. Live checks require a separate, explicitly approved restoration; this feature plan does not authorize restoration or deployment.
