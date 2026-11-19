# Step 7: Remote MCP Client Integration & E2E Demo Requirements

## Objective

Connect the existing dynamic OpenAI agent to the remote MCP server and verify the complete workflow.

## Requirements

- **R001 — Configure remote connection:** Add remote mode to the existing MCP client using Streamable HTTP. Read the `/mcp` endpoint URL and bearer token from environment variables. Never hardcode credentials.
- **R002 — Preserve dynamic tool discovery:** Discover tools using MCP `list_tools()` at runtime. Convert discovered schemas into OpenAI tool definitions dynamically. Do not hardcode a tool catalogue or add tool-specific client logic.
- **R003 — Execute remote tools:** Discover all six analytics tools. Validate OpenAI-generated arguments against discovered schemas. Execute MCP calls and return results to OpenAI. Support multi-tool conversations.
- **R004 — Verify end-to-end workflow:** Run natural-language queries against the S3-backed dataset. Verify tool selection, arguments, results and final answers. Test at least one multi-tool query. Handle connection and authentication failures cleanly.
- **R005 — Add Langfuse tracing:** Trace user queries, OpenAI calls, MCP tool calls/results and final responses. Never log credentials or secrets.

## Acceptance criteria

- **R006:** Remote client connects to the MCP endpoint.
- **R007:** All six tools are discovered dynamically.
- **R008:** Natural-language queries execute remote analytics successfully.
- **R009:** Multi-tool execution works.
- **R010:** Langfuse captures the complete execution trace.

## Scope exclusions and prerequisite

- **R011:** No general Lambda redesign, S3 upload, IAM redesign, or unrelated Terraform redesign. The approved T010 scope is extended to configure the MCP Function URL host allowlist, regression-test the restored and unexpected hosts, publish the corrected Lambda image, and update the existing Lambda image configuration. The existing IAM and S3 settings remain unchanged.
- **R012:** Step 6 demo Lambda resources were destroyed during teardown. Restore them using the existing Step 6 configuration before remote integration testing. The S3 dataset remains intact.

## Clarifications and assumptions

- This is a reconciliation of the supplied Step 7 requirements with existing implementation evidence. The endpoint and bearer token variable names are `MCP_SERVER_URL` and `MCP_BEARER_TOKEN`, as already implemented and recorded in the Step 7 journal.
- The existing client keeps its localhost fallback for local development; remote endpoints require the environment token. An explicit CLI endpoint override remains supported.
- Restoring Step 6 infrastructure is a prerequisite to live testing, not authorization to apply Terraform. Human approval is required for the reviewed plan because it creates IAM resources.
- Implementation and automated test work are already recorded as complete in the existing Step 7 TODO and journal. Live remote E2E evidence remains outstanding.
