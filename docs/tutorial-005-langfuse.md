# Tutorial 005: Run the MCP client and inspect Langfuse traces

This walkthrough starts the market data MCP server, checks it with MCP Inspector, asks natural language questions through the OpenAI client, and inspects the resulting Langfuse traces. Run commands from the repository root. The examples assume `uv`, Node.js/npm, local data under `data/processed`, and working OpenAI and Langfuse Cloud credentials.

## 1. Configure credentials

Create or update the project-root `.env` using your preferred local editor. Add these variables with credentials from OpenAI and the Langfuse project settings:

```dotenv
OPENAI_API_KEY=your-openai-api-key
LANGFUSE_PUBLIC_KEY=your-langfuse-public-key
LANGFUSE_SECRET_KEY=your-langfuse-secret-key
LANGFUSE_BASE_URL=https://cloud.langfuse.com
```

Use your Langfuse Cloud region's base URL if your project is hosted outside the default EU region. Keep `.env` private and do not paste credentials into terminal commands, prompts, or screenshots. The client loads `.env` before initializing Langfuse. `OPENAI_MODEL` is optional; the default is `gpt-4o-mini`.

Install/sync the Python dependencies and confirm which symbols are present in your local dataset:

```sh
uv sync
uv run python -c 'from server.data import list_symbols; from server.config import ANALYTICS_CONFIG; print(sorted(list_symbols(ANALYTICS_CONFIG.processed_data_dir)))'
```

Use a listed symbol and dates covered by your data in the examples below.

## 2. Start the MCP server

In Terminal 1, start the Streamable HTTP server and leave it running:

```sh
uv run uvicorn server.main:app --host 127.0.0.1 --port 8000
```

The MCP endpoint is `http://127.0.0.1:8000/mcp`.

## 3. Connect MCP Inspector

In Terminal 2, launch the Inspector UI:

```sh
npx -y @modelcontextprotocol/inspector
```

Open the local Inspector page shown by the command. Select the Streamable HTTP transport, enter `http://127.0.0.1:8000/mcp` as the server URL, and connect. In the tools view, list the available tools and try a tool such as `get_bars` with a symbol and date range from your local data. This confirms the server is reachable and returns structured data.

Inspector calls go directly to the MCP server. They do not run the OpenAI agent and therefore do not create the agent traces described below. Use the client in the next section to create a Langfuse trace.

## 4. Ask natural language questions

In Terminal 3, run the client with a question. The agent selects the relevant MCP tools, calls OpenAI, and prints its final response:

```sh
uv run python -m client.main \
  --server http://127.0.0.1:8000/mcp \
  --prompt 'Show up to 5 OHLCV bars for RELIANCE from midnight on January 1 through the end of January 31, 2024.'
```

Replace `RELIANCE` and the date range with values in your local data. More examples:

```sh
uv run python -m client.main --server http://127.0.0.1:8000/mcp --prompt 'Summarize RELIANCE on January 15, 2024, including its opening and closing prices, high, low, volume, and number of bars.'
uv run python -m client.main --server http://127.0.0.1:8000/mcp --prompt 'Find RELIANCE’s highest high and lowest low during January 2024.'
uv run python -m client.main --server http://127.0.0.1:8000/mcp --prompt 'Compare RELIANCE and TCS during January 2024.'
```

## 5. Inspect the trace in Langfuse Cloud

Sign in to the Langfuse Cloud project that matches the public and secret keys in `.env`, then open **Traces** (the observability trace list). Refresh if needed; the SDK sends events in the background and the client flushes them when it exits. Open the newest trace named `agent-execution`.

The trace tree should contain:

- The parent `agent-execution` span, with the user question as input and final answer as output.
- One `openai-chat-completion` generation per model request. Select it to inspect the request messages, response/tool calls, model, latency metadata, and token usage when OpenAI returned it.
- An `mcp-tool:<tool-name>` tool observation for each MCP execution, with generated arguments as input and the tool result or safe error as output.

Select observations in the trace tree to view their details. Use the trace timeline/durations to compare where time was spent. Use the trace list filters to find traces by name, model, or time range if your project UI exposes those filters. Generation cost may be shown when Langfuse has pricing data for the model; token counts are recorded when present in the OpenAI response.

## 6. Review errors and other recorded events

Failures during a model request or tool execution appear on the corresponding generation/tool observation, with an error output. An overall agent failure is also recorded on the parent span when the agent catches it. Check the observation type, name, input/output, metadata, usage, status, and timestamps while debugging. Langfuse stores these trace observations; this client does not send arbitrary terminal output or Python log records as separate Langfuse logs.

The client redacts common API keys, bearer tokens, and credential-like fields from trace payloads and sanitized errors. Treat prompts and tool results as potentially sensitive application data and review them before sharing a trace or screenshot.

If no trace appears, check that the client loaded the expected project credentials, that the Cloud base URL matches your project region, and that the command completed (it flushes Langfuse on exit). The [Langfuse tracing guide](https://langfuse.com/docs/observability/get-started) explains project keys and viewing traces. The [MCP Inspector guide](https://modelcontextprotocol.io/docs/tools/inspector) describes Inspector startup and connection options.

Stop the HTTP server and Inspector with Ctrl+C when you are done.
