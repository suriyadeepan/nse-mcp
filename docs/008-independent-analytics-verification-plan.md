# Step 8: Independent Analytics Verification Plan

## Scope and approach

- **P001 — Deterministic remote comparison [R001, R002, R006]:** Add a small command that calls one fixed analytics tool directly through the remote MCP endpoint, bypassing OpenAI tool selection and repeated discovery workflows. Derive expected metrics independently from the same local Parquet partitions with PyArrow and straightforward Python calculations. Compare selected numeric fields using a configurable absolute tolerance and print expected, actual, difference, tolerance, and per-field PASS/FAIL. Use a fixed symbol/date/range represented in both local files and the deployed S3 prefix; confirm the chosen inputs during implementation from the local dataset and existing tool schemas.
- **P002 — Invalid symbol behavior [R003, R007]:** Call the remote endpoint with a deterministic invalid symbol. Pass only when the response is a clean validation rejection and contains no traceback, internal paths, credential values, or raw server internals.
- **P003 — Invocation log verification [R004, R008]:** Immediately before each MCP call, capture its Lambda request start timestamp. Capture the MCP response and any request/correlation identifier available in response metadata or transport headers. Query the configured Lambda CloudWatch log group within a bounded time window and match the invocation using the Lambda request ID or a unique request ID propagated into server logs. If the MCP transport exposes no reliable identifier, add narrowly scoped request-ID propagation/logging: send a unique non-secret ID with the MCP request and log that ID with the request in Lambda. Inspect only correlated invocation events for credential/token leakage. If no reliable ID can be obtained or propagated, report correlation as UNVERIFIED; do not claim a match.
- **P004 — Deterministic report and command [R005, R009]:** Provide one smoke-test command with independently reported statuses for analytics, invalid-input rejection, and CloudWatch. Each check records PASS, FAIL, NOT RUN, or UNVERIFIED with an explanation. Overall status is PASS only if all three pass, FAIL if an assertion fails, and INCOMPLETE if any required check is NOT RUN or UNVERIFIED. Keep output useful without emitting bearer tokens, raw authorization headers, or sensitive AWS responses.
- **P005 — Scope boundary [R010, R011]:** Do not test discovery, OpenAI selection, multi-tool flow, Langfuse, or external market data. No dataset upload, Terraform change, or infrastructure mutation is planned. A minimal non-secret request-ID log entry in the MCP server is in scope only if response metadata cannot provide reliable correlation; any image deployment requires a separately reviewed plan and explicit human approval.

## Affected files and dependencies

- `scripts/verify_remote_analytics.py` — new deterministic remote smoke-test command.
- `src/server/main.py` — only if needed, accept and safely log a unique request ID to correlate the request with Lambda invocation logs.
- `tests/test_verify_remote_analytics.py`, `tests/test_http.py` — automated coverage for numeric comparisons, invalid-input classification, status/report formatting, correlation and redaction.
- `pyproject.toml`, `uv.lock` — add a CLI entry only if needed; use existing `pyarrow`, `mcp`, and AWS CLI configuration. Do not add Pandas.
- `docs/008-independent-analytics-verification-requirements.md` — canonical scope and requirements.
- `docs/008-independent-analytics-verification-todo.md` — canonical task status after plan approval.
- `docs/008-independent-analytics-verification.md` — implementation journal for commands, failures, configuration and evidence; no task status duplication.
- `docs/tutorial-008-independent-analytics-verification.md` — create on completion with safe environment setup and repeatable command instructions.
- Existing remote endpoint/client configuration in `src/client/` and Lambda logging configuration in `terraform/` are interfaces to use, not planned redesign targets.

## Architecture compatibility

| Area | Status | Evidence and implication |
| --- | --- | --- |
| Smoke-test runtime | VERIFIED | `pyproject.toml` requires Python `>=3.15`; `uv` is the prescribed runner. The command runs locally and does not change the Lambda runtime. |
| Local CPU / OS | ASSUMED | Repository is used from the developer host; the script uses existing Python packages and no new native extension. Validate through the prescribed `uv` environment. |
| Remote MCP transport | VERIFIED | Step 7 implements authenticated Streamable HTTP using MCP 2.x; reuse that protocol/configuration for direct tool calls without OpenAI. |
| Local Parquet reader | VERIFIED | PyArrow is already a dependency; `src/server/data.py` uses it for local Parquet access. Expected values will use PyArrow and explicit Python calculations, not the server's DuckDB analytics query. |
| Lambda deployment target | VERIFIED | `Dockerfile.lambda` uses the AWS Lambda Python 3.14 base image and Terraform configures ARM64. Any minimal server logging instrumentation uses the existing target and requires a separately reviewed image update before live use. |
| Native dependencies | VERIFIED | No new native dependency is planned; existing PyArrow and MCP packages are reused. |
| CloudWatch interface | VERIFIED | Terraform provisions `/aws/lambda/${var.lambda_function_name}`; AWS CLI is the planned read-only access method, subject to local credentials and permissions. |
| Deployment availability | DESTROYED | The user reports that the demo Lambda resources were manually destroyed. Live checks require separate authorization to restore/deploy; this plan authorizes neither. Report affected checks as NOT RUN until the endpoint and log group are available. |
| Automated compatibility checks | PLANNED | `uv run pytest tests/test_verify_remote_analytics.py` plus existing focused MCP/client tests; verify locally installed AWS CLI behavior with a mocked or injected log-reader in unit coverage. |

## Risks and mitigations

- **P006 — Dataset drift [R002]:** Local and S3 datasets could differ. Select a fixed partition and verify local files are present; record the compared symbol, date/range and returned row count. Report a mismatch as failure rather than adjusting expected values.
- **P007 — Metric definition mismatch [R002]:** Derive a small set of transparent metrics from raw rows (for example, count, minimum/maximum, or sums) and compare them to fields with the same meaning in the MCP result. Document formulas and use deterministic tie handling if timestamps are compared.
- **P008 — Tolerance masks errors [R002, R006]:** Use an explicit configurable absolute tolerance with a conservative default and include it in every comparison. Reject non-finite values and missing corresponding fields.
- **P009 — Log correlation/leakage [R004, R008]:** Capture start time immediately before each MCP call and retain response metadata. Prefer a Lambda request ID exposed by the MCP transport; otherwise propagate and log a unique non-secret request ID. Query only the bounded time window. If neither source provides a reliable match, record UNVERIFIED. Scan correlated log text for the configured token and credential patterns without echoing matches.
- **P010 — Unavailable endpoint, AWS access or data [R002–R005]:** Distinguish prerequisite failures from failed assertions and report NOT RUN with a concrete reason; never convert unavailable evidence to PASS.
- **P011 — Secret handling [R003–R005]:** Read endpoint/token/function configuration from environment or existing protected local config. Never log request headers, token values, raw AWS credential material, or unsanitized response exceptions.

## Acceptance and validation

- **P012 [R002, R006]:** One fixed remote analytics invocation is compared field by field against independent calculations from local Parquet rows, with configurable tolerance and visible actual numeric differences.
- **P013 [R003, R007]:** A remote invalid-symbol call is rejected cleanly; sanitized output and regression coverage establish that internal details and credentials are absent.
- **P014 [R004, R008]:** CloudWatch shows the matching Lambda invocation using a reliable request/correlation identifier, and inspected invocation events contain no bearer token or other credentials. Report UNVERIFIED if no reliable identifier exists; report NOT RUN if logs or deployment are unavailable.
- **P015 [R005, R009]:** One command emits separate analytics, invalid-input, and CloudWatch statuses, PASS/FAIL/NOT RUN/UNVERIFIED distinctions, and a truthful overall result.
- **P016 [R010, R011]:** Review confirms no repeated discovery, OpenAI tool-selection, multi-tool, Langfuse, external market-data, Terraform apply, or dataset mutation work was added.
- **P017 [R002–R009]:** Run automated tests with `uv`, then run the command against the live endpoint and S3-backed Lambda when available. Record the exact safe command, actual output, deployment/log evidence and any unavailable checks in the implementation journal. Automated tests and live verification remain separate evidence.

## Approval boundary

This plan covers remote MCP calls, read-only CloudWatch inspection, and (only if needed) a narrow non-secret request-ID logging change. The user reports that Lambda resources were manually destroyed. This plan does not authorize restoration, Terraform apply, deployment, IAM/security changes, or dataset mutation. Any restoration or image deployment requires a separately reviewed plan and explicit human approval. Until then, live checks must report NOT RUN.
