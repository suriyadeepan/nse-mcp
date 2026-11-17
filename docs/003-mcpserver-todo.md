# Step 3: Local FastMCP Server TODO

1. [x] Add the official Python MCP SDK and initialize FastMCP in `src/server/main.py`; provide local stdio transport and expose the Streamable HTTP ASGI app there.
2. [ ] Add Pydantic argument schemas in `src/server/validation.py` and define clear descriptions and JSON input schemas for all six tools.
3. [ ] Register all six tools in `src/server/tools.py`, calling the existing DuckDB analytics functions and reusing validation/configuration; leave `analytics.py`, `config.py`, `data.py`, and `queries.py` unchanged.
4. [ ] Return predictable structured results and clear errors, including for empty results and execution failures.
5. [ ] Keep tool implementations in `tools.py` independent of the transports configured in `main.py`.
6. [ ] Keep the server read-only: accept no arbitrary SQL or filesystem paths and perform no database or filesystem writes.
7. [ ] Create `tests/test_mcp_server.py` and test all six tools through the MCP interface: startup, discovery, valid results, invalid arguments, empty results, and execution errors.
8. [ ] Run the existing DuckDB analytics tests and confirm they remain unaffected.
