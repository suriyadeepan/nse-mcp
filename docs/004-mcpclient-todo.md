# Step 4: Dynamic MCP Client and OpenAI Agent TODO

1. [x] Connect the MCP client to the server's Streamable HTTP endpoint (default `http://localhost:8000/mcp`), with configurable URL and clear connection failure handling.
2. [x] Implement runtime `list_tools()` discovery over the HTTP MCP session and convert every discovered tool's name, description, and JSON Schema into OpenAI-compatible definitions without hardcoded tool metadata.
3. [ ] Validate OpenAI-generated arguments against each discovered JSON Schema before invoking the selected tool through the HTTP MCP session; report invalid arguments and MCP execution errors safely.
4. [ ] Implement the OpenAI agent loop so the model selects tools and generates arguments from the user's question, receives MCP results, and produces a readable final answer.
5. [ ] Support multiple tool calls and cap the tool-calling loop at a configurable maximum of 2–3 rounds.
6. [ ] Read OpenAI credentials from environment variables and ensure logs and errors never expose API keys or credentials.
7. [ ] Update `src/client/main.py` for CLI interaction with the HTTP server endpoint and create `tests/test_client.py` covering HTTP discovery, schema conversion, validation, agent tool calls, round limits, and failure handling.
8. [ ] Verify all six current tools are discovered over HTTP and available to OpenAI, then run client tests and confirm existing MCP server and analytics tests remain unaffected; adding a server tool must require no client code changes.
