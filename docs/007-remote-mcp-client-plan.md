# Step 7: Remote MCP Client Integration & E2E Demo Plan

## Scope and approach

- **P001 — Remote configuration [R001]:** Use `MCP_SERVER_URL` and `MCP_BEARER_TOKEN` for protected Streamable HTTP connections. Preserve the implemented `--server` override and localhost fallback. Send the token only as an authorization header and keep it out of errors, logs and traces.
- **P002 — Dynamic tool workflow [R002, R003]:** Retain runtime `list_tools()` discovery, schema-derived OpenAI definitions, JSON Schema argument validation, MCP execution, and bounded multi-round conversations. Do not introduce a hardcoded tool catalogue or tool-specific client branches.
- **P003 — Trace coverage [R005, R010]:** Retain Langfuse observations for the user query, OpenAI requests/responses, MCP tool inputs/results, and final response. Verify configured credentials and URL credentials are redacted.
- **P004 — Live remote verification [R004, R006–R009, R012]:** After Step 6 resources are restored, exercise all six discovered analytics tools and representative natural-language queries against the S3-backed dataset, including a multi-tool query. Record selected tools, arguments, results, final answers, and trace evidence in the journal.
- **P005 — Scope boundary [R011]:** Do not change Lambda implementation, Docker/ECR publishing, S3 contents, IAM design, or Terraform design. Restore the existing Step 6 resources only as a prerequisite, from its existing configuration.

## Existing implementation and remaining evidence

The current client already implements authenticated Streamable HTTP sessions for discovery and execution, dynamic schemas, argument validation, a bounded multi-tool loop, and redacted Langfuse tracing. The Step 7 journal records automated regression and compatibility evidence. The remaining acceptance evidence is live remote verification after restoring the destroyed Step 6 endpoint. The existing TODO is the canonical task/status source and remains authoritative for task progress.

## Affected files and dependencies

- `src/client/main.py`, `src/client/discovery.py`, `src/client/agent.py` — existing connection, discovery, execution and trace implementation; change only if live verification exposes a defect.
- `tests/test_client.py`, `tests/test_langfuse.py` — existing automated regression coverage; add regression coverage only for repeatable issues found during verification.
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
| Server runtime/target | VERIFIED | Step 6 documents the existing Lambda image as Python 3.14 on ARM64 and its Streamable HTTP `/mcp` endpoint. The remote resources are currently absent after teardown. |
| Native dependencies | VERIFIED | Client changes use existing Python dependencies and add no native libraries. |
| Deployment prerequisite | VERIFIED, restoration pending | Step 6 records a reviewed plan for restoring seven demo resources and confirms the S3 prefix still has 2,781 objects / 326,546,421 bytes. Applying the plan includes IAM role/policy creation and requires human approval. |
| Automated compatibility checks | VERIFIED for client path | The journal records authenticated HTTP tests and client/Langfuse tests. Live endpoint, S3-backed query and Langfuse Cloud evidence remain to be gathered after restoration. |

## Risks and mitigations

- **P006 — Credential exposure [R001, R005]:** Keep credentials in environment configuration and HTTP headers; preserve sanitization and redaction tests. Never copy secrets into docs or command history.
- **P007 — Session mismatch [R003]:** Discovery and execution use separate MCP sessions; live verification must confirm both use the same resolved endpoint and authorization settings.
- **P008 — Missing deployment [R004, R012]:** Do not start live queries until the reviewed Step 6 restoration is approved and applied. The deployment plan includes IAM changes; no apply is authorized by this plan.
- **P009 — External service variability [R004, R005]:** Keep automated tests distinct from live AWS/OpenAI/Langfuse checks and record actual results without implying unverified success.

## Acceptance and validation

- **P010 [R001, R006]:** Connect to the remote `/mcp` endpoint using environment configuration; verify authentication and sanitized failure behavior.
- **P011 [R002, R007]:** Discover all six analytics tools at runtime and verify definitions come from returned schemas.
- **P012 [R003, R008, R009]:** Verify schema-checked arguments, remote results returned to OpenAI, natural-language answers, and at least one multi-tool conversation.
- **P013 [R005, R010]:** Inspect Langfuse for the complete query/model/tool/result/final-answer trace and absence of credentials.
- **P014 [R004, R012]:** Record exact commands, tool selections, arguments, results, final answers, trace evidence, and failures in the journal. Separate automated checks from live checks.

## Approval boundary

This plan does not authorize Terraform apply. The already-reviewed Step 6 restoration plan includes creation of IAM role and policy resources; apply requires explicit human approval. No AWS mutation is part of this planning update.
