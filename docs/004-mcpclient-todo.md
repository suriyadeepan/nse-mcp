# Step 4: Dynamic MCP Client and OpenAI Agent TODO

1. [x] Connect the MCP client to the server's Streamable HTTP endpoint (default `http://localhost:8000/mcp`), with configurable URL and clear connection failure handling.
2. [x] Implement runtime `list_tools()` discovery over the HTTP MCP session and convert every discovered tool's name, description, and JSON Schema into OpenAI-compatible definitions without hardcoded tool metadata.
3. [x] Validate OpenAI-generated arguments against each discovered JSON Schema before invoking the selected tool through the HTTP MCP session; report invalid arguments and MCP execution errors safely.
4. [x] Implement the OpenAI agent loop so the model selects tools and generates arguments from the user's question, receives MCP results, and produces a readable final answer.
5. [x] Support multiple tool calls and cap the tool-calling loop at a configurable maximum of 2–3 rounds.
6. [x] Read OpenAI credentials from environment variables and ensure logs and errors never expose API keys or credentials.
7. [x] Update `src/client/main.py` for CLI interaction; test client behavior, including the 12,000-token per-result and 24,000-token per-conversation MCP result limits; verify adding server tools requires no client changes.
8. [x] Cap every row list returned by MCP tools at 30 rows and test the server-side response limit.
