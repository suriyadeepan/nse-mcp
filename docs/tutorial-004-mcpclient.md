# Tutorial 004: Run the dynamic MCP client

This walkthrough starts the MCP server over Streamable HTTP, inspects the tools the client discovers at runtime, and sends questions to the OpenAI agent. Run commands from the repository root. The examples assume the local market data is available under `data/processed`.

## 1. Check local symbols

List the symbols present in the configured processed-data directory. Use one or more of these symbols in the prompts below:

```sh
uv run python -c 'from server.data import list_symbols; from server.config import ANALYTICS_CONFIG; print(sorted(list_symbols(ANALYTICS_CONFIG.processed_data_dir)))'
```

Choose dates that exist in your data. Ask questions in everyday language, for example “from the morning of January 1 through the evening of January 31, 2024” or “on January 15, 2024.” The agent turns those requests into the structured dates and times required by the tools. The schema-validation example later in this tutorial uses ISO timestamps because it passes arguments directly to a tool, rather than asking the agent to interpret a prompt.

## 2. Start the HTTP MCP server

In Terminal 1, run:

```sh
uv run uvicorn server.main:app --host 127.0.0.1 --port 8000
```

Leave it running. The MCP endpoint is `http://127.0.0.1:8000/mcp`.

## 3. Inspect runtime discovery and OpenAI tool definitions

In Terminal 2, run this command. It connects over HTTP, lists the tools advertised by the server, and prints the OpenAI-compatible definitions created from their discovered schemas:

```sh
uv run python - <<'PY'
import asyncio
import json

from client.agent import Agent


async def main():
    agent = Agent("http://127.0.0.1:8000/mcp")
    tools = await agent.connect()
    print(f"Discovered {len(tools)} MCP tools:")
    for name in tools:
        print(f"- {name}")
    print("\nOpenAI tool definitions:")
    print(json.dumps(agent.openai_tools, indent=2))


asyncio.run(main())
PY
```

You should see all six current server tools and a JSON function definition for each. The names, descriptions, and parameter schemas come from the running MCP server.

## 4. Set the OpenAI API key

In Terminal 2, enter the key without placing it in shell history. For zsh:

```sh
read -s 'OPENAI_API_KEY?OpenAI API key: '
export OPENAI_API_KEY
print
```

For bash:

```sh
read -r -s -p 'OpenAI API key: ' OPENAI_API_KEY
export OPENAI_API_KEY
printf '\n'
```

The client uses `OPENAI_API_KEY` through the OpenAI SDK. It does not print the key. `OPENAI_MODEL` can optionally select the model; otherwise the client uses `gpt-4o-mini`.

## 5. Ask the agent questions

Run the CLI in Terminal 2. Replace `RELIANCE` and the dates with values available in your local data:

```sh
uv run python -m client.main \
  --server http://127.0.0.1:8000/mcp \
  --prompt 'Show up to 5 OHLCV bars for RELIANCE from midnight on January 1 through the end of January 31, 2024.'
```

The command prints the OpenAI generated answer after the selected MCP tool returns. Try other questions to exercise the remaining tools:

```sh
uv run python -m client.main --server http://127.0.0.1:8000/mcp --prompt 'Summarize RELIANCE on January 15, 2024, including its opening and closing prices, high, low, volume, and number of bars.'
uv run python -m client.main --server http://127.0.0.1:8000/mcp --prompt 'Find RELIANCE’s highest high and lowest low from the start of January 1 through the end of January 31, 2024.'
uv run python -m client.main --server http://127.0.0.1:8000/mcp --prompt 'Summarize RELIANCE’s daily trading volume for January 2024.'
uv run python -m client.main --server http://127.0.0.1:8000/mcp --prompt 'Calculate SMA and RSI for RELIANCE from the start of January 1 through the end of January 31, 2024.'
uv run python -m client.main --server http://127.0.0.1:8000/mcp --prompt 'Compare RELIANCE and TCS during January 2024, from the first day through the last day of the month.'
```

Use your available symbols and dates in each prompt. Natural phrases such as “between 9:30 in the morning and 3:30 in the afternoon India time (IST) on January 15” are fine when you mean a time-of-day range. To exercise multiple tool calls in one question, ask for a symbol comparison and bars for one of those symbols during the same month, then ask the agent to summarize both results. The answer appears in the terminal after the tool results are sent back to OpenAI.

## 6. See schema validation reject invalid arguments

This command checks an intentionally invalid `get_bars` request against the schema discovered from the running server. It only validates the arguments and does not invoke the tool:

```sh
uv run python - <<'PY'
import asyncio

from client.agent import Agent
from client.discovery import ToolArgumentError, validate_tool_arguments


async def main():
    agent = Agent("http://127.0.0.1:8000/mcp")
    tools = await agent.connect()
    invalid_arguments = {
        "arguments": {
            "symbol": "RELIANCE",
            "start_datetime": "2024-01-01T00:00:00Z",
            "end_datetime": "2024-01-31T23:59:59Z",
            "limit": 0,
        }
    }
    try:
        validate_tool_arguments(tools["get_bars"], invalid_arguments)
    except ToolArgumentError as exc:
        print(f"Rejected before MCP execution: {exc}")
    else:
        raise SystemExit("Expected schema validation to reject limit=0")


asyncio.run(main())
PY
```

The agent also sends invalid model-generated arguments and MCP execution errors back to OpenAI as safe tool results so it can explain the failure in its final answer.

## 7. Check the connection failure message

With the API key still set in Terminal 2, use a port where no MCP server is running:

```sh
uv run python -m client.main \
  --server http://127.0.0.1:8001/mcp \
  --prompt 'Show 5 bars for RELIANCE.'
```

The command exits with a clear Streamable HTTP connection error. It does not print credentials or the URL's sensitive components.

## 8. Stop and clear the key

Stop the server in Terminal 1 with Ctrl+C. In Terminal 2, remove the key from that shell:

```sh
unset OPENAI_API_KEY
```
