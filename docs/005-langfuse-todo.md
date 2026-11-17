# Step 5: Langfuse Tracing TODO

## Objective

Integrate Langfuse into the local MCP client and OpenAI agent to inspect complete agent executions, using the existing Langfuse Cloud project credentials from the environment.

## TODO

- [x] **T1 — Confirm Langfuse Cloud authentication:** Use environment credentials; never read, print, or commit `.env` contents.
- [x] **T2 — Initialize and flush Langfuse:** Set up Langfuse in `src/client/main.py` and flush it cleanly when the client exits.
- [x] **T3 — Trace agent executions:** Capture each complete execution, including the user question and final answer.
- [x] **T4 — Record OpenAI calls:** Capture model requests and responses, including latency and token usage when available.
- [x] **T5 — Record MCP tool calls:** Capture tool names, generated arguments, executions, and results.
- [x] **T6 — Organize trace hierarchy:** Give each execution a parent trace with child spans for model calls and tool calls.
- [x] **T7 — Filter secrets:** Filter or redact API keys, bearer tokens, and other secrets from traces, logs, and errors.
- [x] **T8 — Add Langfuse tests:** Cover trace creation and secret filtering in `tests/test_langfuse.py`.
- [ ] **T9 — Verify complete traces:** Confirm an execution trace shows OpenAI calls and MCP tool executions, with tool inputs/outputs and available latency/token usage.
- [ ] **T10 — Verify safety and regression behavior:** Confirm no secrets appear in traces or logs and existing client, server, and analytics functionality remains unaffected.

## Files

- `src/client/agent.py` — add traces, spans, and execution metadata.
- `src/client/main.py` — initialize and flush Langfuse.
- `tests/test_langfuse.py` — test trace creation and secret filtering.
