# Step 7: Remote MCP Client Integration & E2E Demo Plan

## Scope and approach

- **P001 — Remote configuration [R001]:** Use `MCP_SERVER_URL` and `MCP_BEARER_TOKEN` for protected Streamable HTTP connections. Preserve the implemented `--server` override and localhost fallback. Send the token only as an authorization header and keep it out of errors, logs and traces.
- **P002 — Dynamic tool workflow [R002, R003]:** Retain runtime `list_tools()` discovery, schema-derived OpenAI definitions, JSON Schema argument validation, MCP execution, and bounded multi-round conversations. Do not introduce a hardcoded tool catalogue or tool-specific client branches.
- **P003 — Trace coverage [R005, R010]:** Retain Langfuse observations for the user query, OpenAI requests/responses, MCP tool inputs/results, and final response. Verify configured credentials and URL credentials are redacted.
- **P004 — Live remote verification [R004, R006–R009, R012]:** After Step 6 resources are restored, exercise all six discovered analytics tools and representative natural-language queries against the S3-backed dataset, including a multi-tool query. Record selected tools, arguments, results, final answers, and trace evidence in the journal.
- **P005 — Scope boundary [R011]:** Keep S3 contents and IAM design unchanged. The user approved a narrow exception for T010: make the permitted Function URL hostname configurable, add restored/unexpected-host regression coverage, build and publish the corrected ARM64 Lambda image, and update the existing Terraform image and hostname configuration. Do not make unrelated Lambda or Terraform changes.

## Existing implementation and remaining evidence

The client implements authenticated Streamable HTTP sessions for discovery and execution, dynamic schemas, argument validation, a bounded multi-tool loop, and redacted Langfuse tracing. The Step 7 journal records automated regression and compatibility evidence, the configured-host correction, deployment, and completed live remote verification. The existing TODO is the canonical task/status source and remains authoritative for task progress.

## Affected files and dependencies

- `src/client/main.py`, `src/client/discovery.py`, `src/client/agent.py` — existing connection, discovery, execution and trace implementation.
- `src/server/main.py`, `terraform/main.tf`, `terraform/variables.tf` — configured Function URL host allowlist and deployment wiring for the approved T010 fix.
- `tests/test_client.py`, `tests/test_langfuse.py`, `tests/test_http.py` — automated regression coverage, including restored-host acceptance and unrelated-host rejection.
- `docs/007-remote-mcp-client-requirements.md` — canonical requirements.
- `docs/007-remote-mcp-client-todo.md` — canonical status; update only when task evidence changes.
- `docs/007-remote-mcp-client.md` — durable decisions, commands, failures, and automated/live evidence.
- `docs/tutorial-007-remote-mcp-client.md` — create when the remote workflow is verified.
- `docs/006-aws_lambda.md`, `terraform/` — existing Step 6 deployment configuration and its restoration plan; no redesign is in scope.
- No new runtime dependency is planned. The lockfile records MCP 2.3.0 and `httpx2` 2.16.2.

## Architecture compatibility

| Area | Status | Evidence and implication |
| --- | --- | --- |
| Client runtime | VERIFIED | `pyproject.toml` and `uv.lock` require Python `>=3.15`; the journal records `uv run python --version` as Python 3.15.2. |
| Client OS/CPU | VERIFIED | The existing plan records development host `Darwin arm64`; no native client extension is introduced. |
| MCP transport/auth | VERIFIED | Locked MCP 2.3.0 supports a configured `httpx2.AsyncClient` in `streamable_http_client`; its headers carry the bearer token. Existing client tests cover authenticated discovery and execution. |
| Server runtime/target | VERIFIED | Step 6 documents the Lambda image as Python 3.14 on ARM64 and its Streamable HTTP `/mcp` endpoint. The restored Lambda is active and uses the configured-host correction. |
| Native dependencies | VERIFIED | Client changes use existing Python dependencies and add no native libraries. |
| Deployment prerequisite | VERIFIED | Step 6 resources are restored. The corrected image receives the exact Function URL hostname through `MCP_FUNCTION_URL_HOST`; the narrow image update plan changed only the Lambda image and hostname environment value, with no IAM, Function URL, or S3 changes. |
| Automated compatibility checks | VERIFIED | Host validation, authenticated client behavior, Langfuse redaction, and Terraform configuration tests pass. Live endpoint, S3-backed analytics, and Langfuse trace evidence are recorded in the journal. |

## Risks and mitigations

- **P006 — Credential exposure [R001, R005]:** Keep credentials in environment configuration and HTTP headers; preserve sanitization and redaction tests. Never copy secrets into docs or command history.
- **P007 — Session mismatch [R003]:** Discovery and execution use separate MCP sessions; live verification must confirm both use the same resolved endpoint and authorization settings.
- **P008 — Missing deployment [R004, R012]:** Run live queries only after Step 6 restoration. The user approved the restoration and the later narrowly scoped image/configuration update; the latter plan must contain no IAM, URL, or S3 changes.
- **P009 — External service variability [R004, R005]:** Keep automated tests distinct from live AWS/OpenAI/Langfuse checks and record actual results without implying unverified success.

## Acceptance and validation

- **P010 [R001, R006]:** Connect to the remote `/mcp` endpoint using environment configuration; verify authentication and sanitized failure behavior.
- **P011 [R002, R007]:** Discover all six analytics tools at runtime and verify definitions come from returned schemas.
- **P012 [R003, R008, R009]:** Verify schema-checked arguments, remote results returned to OpenAI, natural-language answers, and at least one multi-tool conversation.
- **P013 [R005, R010]:** Inspect Langfuse for the complete query/model/tool/result/final-answer trace and absence of credentials.
- **P014 [R004, R012]:** Record exact commands, tool selections, arguments, results, final answers, trace evidence, and failures in the journal. Separate automated checks from live checks.
- **P015 [R006, R011, R012]:** Read the exact Function URL hostname from Terraform-provided Lambda configuration, allow the restored hostname while rejecting unrelated hosts, test both cases, and deploy a digest-pinned corrected ARM64 image with no IAM or S3 changes.

## Approval boundary

The user approved this narrow T010 scope update and requested deployment of the corrected image. The deployment plan must be reviewed before apply and must show only the intended in-place Lambda image/configuration update; no IAM changes, Function URL changes, or S3 mutations are in scope. If the plan differs, stop and report the exact actions before applying.
