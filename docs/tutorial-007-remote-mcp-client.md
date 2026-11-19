# Tutorial 007: Run the remote MCP analytics client

This guide connects the OpenAI client to the authenticated remote MCP server, lets it discover the server's tools, and runs analytics against the restored S3-backed dataset. The endpoint and sample results below were verified on 2026-11-19. The endpoint can be redeployed or replaced; use the URL and bearer token supplied by the operator of the deployment you are authorized to access.

## Prerequisites

- Python 3.15 or later and [`uv`](https://docs.astral.sh/uv/).
- An OpenAI API key with access to the configured model.
- The remote MCP `/mcp` endpoint URL and bearer token from the deployment operator. The client requires the token for any non-local endpoint.
- Optional: Langfuse project credentials if you want to inspect traces. The client can run without tracing credentials.

Run commands from the repository root. Install the locked project dependencies:

```sh
uv sync
```

## Configure credentials locally

The client loads `.env` from the repository root. That file is ignored by Git. If it does not already exist, create it with owner-only permissions, then edit it using your preferred editor. This leaves an existing `.env` untouched:

```sh
if [ ! -e .env ]; then (umask 077 && touch .env); fi
${EDITOR:-vi} .env
```

Add your own values, without quotes or angle brackets:

```dotenv
MCP_SERVER_URL=https://your-function-url-host/mcp
MCP_BEARER_TOKEN=your-bearer-token
OPENAI_API_KEY=your-openai-api-key
# Optional model override; defaults to gpt-4o-mini.
# OPENAI_MODEL=gpt-4o-mini
# Optional Langfuse tracing. Keep these values in your local .env only.
# LANGFUSE_PUBLIC_KEY=your-langfuse-public-key
# LANGFUSE_SECRET_KEY=your-langfuse-secret-key
# LANGFUSE_HOST=https://cloud.langfuse.com
```

Replace the example endpoint with the exact URL provided by your deployment operator. Do not commit or share `.env`, paste credentials into prompts, or put tokens in command arguments. The CLI accepts `--server` as an endpoint override, but using `MCP_SERVER_URL` avoids putting deployment details in shell history. A remote endpoint without `MCP_BEARER_TOKEN` is rejected before the client connects. Local development retains the `http://localhost:8000/mcp` fallback and does not require the remote token.

## Run a single-tool query

Ask about the verified RELIANCE session for January 2, 2025:

```sh
uv run python -m client.main \
  --prompt 'For RELIANCE on 2025-01-02, report the open, close, return, VWAP, and number of bars.'
```

The client connects to the configured endpoint, discovers the available tool schemas at runtime, and asks the model to select and call the appropriate tool. In the verified run, it selected `intraday_stats` and reported an open of ₹1,221.25, close of ₹1,240.80, return of 1.60%, VWAP of ₹1,234.29, and 375 bars. Results depend on the deployed dataset and model response.

## Run a multi-tool query

Ask for price extremes and daily volumes for the same three-day period:

```sh
uv run python -m client.main \
  --prompt 'For RELIANCE from 2025-01-01 through 2025-01-03, give the highest high and lowest low with their timestamps, then list each IST daily volume.'
```

The verified run called `get_price_extremes` and `get_volume_stats`. It returned a high of 1,262.05 at `2025-01-03T08:04:00Z`, a low of 1,211.60 at `2025-01-01T04:24:00Z`, and daily volumes of 5,863,755 (Jan 1), 15,431,413 (Jan 2), and 15,320,449 (Jan 3). The client validates model-generated arguments against each discovered JSON Schema before calling the MCP tool.

Use symbols and dates available in the remote dataset. To ask for another range, edit the natural-language prompt; the client does not contain a hardcoded tool catalogue or symbol list.

## Review traces (optional)

When Langfuse is configured, inspect the trace for each query in your Langfuse project. A complete run includes the user query, OpenAI requests and responses, MCP tool inputs and results, and the final answer. The verified single-tool trace contained 4 observations; the multi-tool trace contained 5. The configured bearer token, OpenAI API key, Langfuse secret, and MCP endpoint were absent from trace inputs and outputs. Langfuse may attach its public project identifier in SDK metadata.

Do not copy credentials from `.env` into trace annotations, prompts, screenshots, or support requests. If you do not see a trace, confirm that Langfuse credentials and host are configured for the project, then run a new query; tracing is optional for the MCP request itself.

## Troubleshooting

- **Missing `MCP_BEARER_TOKEN`:** Confirm the local `.env` has the token for the configured remote endpoint. Do not include the token in a command or share it in logs.
- **Streamable HTTP connection error:** Check the `/mcp` endpoint URL and confirm the deployment is available. The client sanitizes connection failures and does not include the endpoint in the error.
- **Authentication failure:** Ask the deployment operator to confirm the token is current and belongs to this endpoint. Do not retrieve or guess deployment secrets.
- **No data for a query:** Try a symbol and date range known to exist in that deployment's dataset.
- **No Langfuse trace:** Confirm the optional Langfuse project settings and host, then issue another query.

The restored demo endpoint and S3-backed dataset are deployment resources and may not always be running. Contact the deployment operator if the endpoint is unavailable.
