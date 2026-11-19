# Step 7: Remote MCP Client Integration & E2E Demo Plan

## Scope and approach

Extend the existing OpenAI client to connect to a protected Streamable HTTP MCP endpoint configured by environment. Preserve runtime `list_tools()` discovery, JSON Schema validation, multi-round tool execution, and Langfuse observations. Run remote smoke checks against the existing Step 6 deployment and S3 dataset after that deployment is restored. Do not change Lambda, container publishing, S3 upload, IAM, or Terraform design.

The implementation should use the existing MCP client library's supported request-header configuration to send `Authorization: Bearer …`; the endpoint URL and token must come from `MCP_SERVER_URL` and `MCP_BEARER_TOKEN`. Keep the localhost endpoint as the development default when no remote URL is supplied. Never include credentials in errors, logs, trace input, or command history. Confirm the locked MCP 2.3.0 header API before implementation.

## Existing implementation and gaps

- `src/client/discovery.py` already opens Streamable HTTP sessions, follows `list_tools()` pagination, converts discovered schemas to OpenAI tools, validates generated arguments, executes tools, and sanitizes connection errors. It currently supplies no authentication headers.
- `src/client/agent.py` already performs dynamic tool selection, supports multiple tools and bounded tool rounds, and traces user input, OpenAI generations, MCP tool calls/results, and final answers through Langfuse with secret redaction.
- `src/client/main.py` currently accepts a server URL CLI option with a localhost default, initializes Langfuse, flushes it at exit, and reports connection failures. It needs environment-based remote configuration and clear authentication/connection failure handling.
- Existing tests cover dynamic discovery, arbitrary added tools, schema validation, tool execution, connection errors, multi-call loops, tracing, and redaction. They need authenticated-client coverage and remote E2E evidence for all six analytics tools and at least one multi-tool query.
- `docs/006-aws_lambda.md` records that teardown removed the Lambda demo resources and preserved 2,781 dataset objects. Remote E2E testing depends on restoring those resources from existing Step 6 configuration.

## Files and dependencies

- `src/client/main.py` — resolve the endpoint from CLI override / `MCP_SERVER_URL` / localhost default, load the bearer token from the environment, and surface safe configuration errors.
- `src/client/discovery.py` — configure authorization on every MCP session used for discovery and tool execution; preserve credential-safe errors.
- `src/client/agent.py` — pass the same connection settings through discovery and execution without changing tool catalogue behavior; preserve complete redacted tracing.
- `tests/test_client.py` — cover environment configuration, authorized discovery and calls, missing/invalid credentials, and regression of existing dynamic/multi-tool behavior.
- `tests/test_langfuse.py` — verify remote request credentials are excluded while query, model/tool inputs and outputs, and final response remain traced safely.
- `docs/007-remote-mcp-client.md` — implementation decisions, commands, test results, and live verification evidence.
- `docs/tutorial-007-remote-mcp-client.md` — create on feature completion with environment setup and repeatable demo steps.

No new runtime dependency is planned. The MCP package is locked at 2.3.0; the existing OpenAI, JSON Schema, dotenv, and Langfuse dependencies cover the workflow.

## Architecture compatibility

| Area | Status | Evidence and implication |
| --- | --- | --- |
| Local runtime | VERIFIED | Project requires Python `>=3.15` (`pyproject.toml`, `uv.lock`); local `uv python find` resolves the repository `.venv` interpreter. Confirm its exact version with `uv run python --version` during implementation. |
| Local CPU / OS | VERIFIED | `uname -sm` reports Darwin arm64. This is the client development host; no native client extension is introduced. |
| Remote server runtime | VERIFIED | Step 6 Dockerfile uses AWS Lambda Python 3.14 and Terraform configures ARM64. Step 6 documents successful MCP HTTP operation on the deployed image. |
| MCP transport and auth | ASSUMED | Existing server exposes Streamable HTTP at `/mcp` and Bearer middleware reads `MCP_BEARER_TOKEN` (`src/server/main.py`, `src/server/auth.py`). Verify the locked MCP 2.3.0 client accepts custom headers and confirm with an authenticated integration test. |
| Native dependencies | VERIFIED | Client uses Python packages without adding native libraries; server native dependencies stay within the existing ARM64 Lambda image and are out of scope. |
| Deployment target | VERIFIED / prerequisite outstanding | The target is the existing Step 6 Lambda Function URL `/mcp` and preserved S3 dataset. Step 6 records teardown of demo resources. Redeploy with the existing configuration before live checks; a Terraform apply requires human approval under repository instructions. |
| Automated compatibility checks | PLANNED | Unit/integration tests will exercise Streamable HTTP auth, discovered schemas, argument validation, multi-tool rounds, safe failure messages, and trace redaction. Live deployment smoke checks separately verify remote connectivity and S3-backed answers. |

## Risks and mitigations

- **Bearer token leakage:** Keep it only in environment configuration and HTTP headers. Redact any SDK exception text before display or tracing; test failures with sentinel credentials.
- **Split session configuration:** Discovery and subsequent tool calls open separate MCP sessions. Ensure both receive identical endpoint and authorization settings; test a protected local ASGI server.
- **Remote deployment absent:** Step 6 teardown removed Lambda resources. Restore only the existing Step 6 resources after reviewing its Terraform plan and obtaining required apply approval; do not upload or alter S3 data.
- **External service variability:** OpenAI and Langfuse require valid local environment configuration and network access. Keep automated tests mocked; record live checks independently and do not claim them passed unless actually run.
- **Trace completeness and privacy:** Existing trace instrumentation is present. Verify user query, model request/response, tool input/result and final answer are present while endpoint credentials never appear.

## Acceptance criteria and validation

- Client uses an environment-configured remote `/mcp` URL and bearer token without hardcoded credentials; failures are clear and credential-safe.
- Runtime MCP discovery returns all six analytics tools and converts their discovered schemas to OpenAI definitions.
- Generated tool arguments are checked against discovered schemas; remote tool results return to OpenAI and a conversation can execute multiple tools.
- Automated tests cover authenticated transport, invalid/missing auth handling, dynamic discovery, multi-tool execution, and secret-safe Langfuse traces.
- After restoring Step 6 resources, run natural-language S3 dataset queries, verify tool selection/arguments/results/final responses, include one multi-tool query, and inspect the resulting Langfuse trace.
- Record exact validation commands and results in the implementation journal; distinguish automated checks from live AWS/OpenAI/Langfuse verification.

## Approval boundary

This document is the proposed implementation plan for review. Restoring Lambda resources is a separate prerequisite requiring a Terraform plan review and explicit apply approval; no AWS changes are part of planning.
