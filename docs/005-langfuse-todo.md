# Step 5: Langfuse Tracing TODO

## Objective

Integrate Langfuse into the local MCP client and OpenAI agent to inspect complete agent executions, using the existing Langfuse Cloud project credentials from the environment.

## TODO

- [x] Confirm Langfuse Cloud is accessible using environment credentials; never read, print, or commit `.env` contents.
- [ ] Initialize Langfuse in `src/client/main.py` and flush it cleanly when the client exits.
- [ ] Trace each complete agent execution, including the user question and final answer.
- [ ] Record OpenAI model calls and responses, including latency and token usage when available.
- [ ] Record MCP tool names, generated arguments, executions, and results.
- [ ] Organize each execution as a parent trace with clear child spans for model calls and tool calls.
- [ ] Filter or redact API keys, bearer tokens, and all other secrets from traces, logs, and errors.
- [ ] Add `tests/test_langfuse.py` covering trace creation and secret filtering.
- [ ] Verify a complete execution creates a trace showing OpenAI calls and MCP tool executions, with tool inputs/outputs and available latency/token usage.
- [ ] Verify no secrets appear in traces or logs, and existing client, server, and analytics functionality remains unaffected.

## Files

- `src/client/agent.py` — add traces, spans, and execution metadata.
- `src/client/main.py` — initialize and flush Langfuse.
- `tests/test_langfuse.py` — test trace creation and secret filtering.
