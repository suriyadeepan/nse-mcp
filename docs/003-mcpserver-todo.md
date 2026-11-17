# Step 3: MCP Server TODO

Use the current [MCP Python SDK 2.x documentation](https://py.sdk.modelcontextprotocol.io/), including its [server run and transport guidance](https://py.sdk.modelcontextprotocol.io/run/) and [ASGI app guidance](https://py.sdk.modelcontextprotocol.io/run/asgi/). Do not use older FastMCP tutorials or APIs.

1. [x] Update the dependency to `mcp>=2,<3` and initialize `MCPServer` (not `FastMCP`) in `src/server/main.py`; support local stdio with `run(transport="stdio")` and expose Streamable HTTP with `streamable_http_app()`.
2. [ ] Add Pydantic argument schemas in `src/server/validation.py` and define clear descriptions and JSON input schemas for all six tools.
3. [ ] Register all six tools in `src/server/tools.py`, calling the existing DuckDB analytics functions and reusing validation/configuration; leave `analytics.py`, `config.py`, `data.py`, and `queries.py` unchanged.
4. [ ] Return predictable structured results and clear errors, including for empty results and execution failures.
5. [ ] Keep tool implementations in `tools.py` independent of the transports configured in `main.py`.
6. [ ] Keep the server read-only: accept no arbitrary SQL or filesystem paths and perform no database or filesystem writes.
7. [ ] Create `tests/test_mcp_server.py` and test startup and all six tools through the MCP interface over stdio and Streamable HTTP: discovery, valid results, invalid arguments, empty results, and execution errors.
8. [ ] Run the existing DuckDB analytics tests and confirm they remain unaffected.
