# T6.4 — Local MCP and Lambda Container Smoke Test Documentation

## Objective

Verify the Lambda container locally using:

1. Direct HTTP testing of the MCP server.
2. AWS Lambda Runtime Interface Emulator (RIE).
3. MCP initialization through the Lambda invocation endpoint.

No AWS deployment is required.

## Prerequisites

- Docker image built as `kite-mcp-lambda:local`.
- Image platform: `linux/arm64`.
- RIE binary available at `.aws-lambda/aws-lambda-rie`.
- AWS credentials available in `~/.aws`.
- S3 dataset configured in `nse-mcp-data`.

## 1. Start the container for direct MCP testing

Run the Lambda container directly, without RIE:

```bash
docker run --rm -d \
  --platform linux/arm64 \
  --name kite-mcp-test \
  -p 9000:8080 \
  -e PROCESSED_DATA_SOURCE=s3 \
  -e PROCESSED_DATA_S3_BUCKET=nse-mcp-data \
  -e PROCESSED_DATA_S3_PREFIX=data/processed \
  -v "$HOME/.aws:/var/task/.aws:ro" \
  kite-mcp-lambda:local
```

Check startup:

```bash
docker logs -f kite-mcp-test
```

Expected logs:

```text
StreamableHTTP session manager started
INFO: Application startup complete.
INFO: Uvicorn running on http://0.0.0.0:8080
```

## 2. Test MCP directly over HTTP

The MCP endpoint is `/mcp`.

### Initialize an MCP session

```bash
curl -i -X POST http://localhost:9000/mcp \
  -H "Content-Type: application/json" \
  -H "Accept: application/json, text/event-stream" \
  -H "MCP-Protocol-Version: 2025-03-26" \
  -d '{
    "jsonrpc": "2.0",
    "id": 1,
    "method": "initialize",
    "params": {
      "protocolVersion": "2025-03-26",
      "capabilities": {},
      "clientInfo": {
        "name": "local-smoke-test",
        "version": "1.0"
      }
    }
  }'
```

Expected:
- HTTP `200 OK`.
- An SSE response containing the MCP initialization result.
- An `mcp-session-id` response header.

Save the returned session ID.

### Test tool discovery

```bash
curl -i -X POST http://localhost:9000/mcp \
  -H "Content-Type: application/json" \
  -H "Accept: application/json, text/event-stream" \
  -H "MCP-Protocol-Version: 2025-03-26" \
  -H "MCP-Session-Id: YOUR_SESSION_ID" \
  -d '{
    "jsonrpc": "2.0",
    "id": 2,
    "method": "tools/list",
    "params": {}
  }'
```

Expected: HTTP `200 OK` with the available MCP tools.

### Test a tool call

The `compare_symbols` tool was tested with:

```json
{
  "jsonrpc": "2.0",
  "id": 3,
  "method": "tools/call",
  "params": {
    "name": "compare_symbols",
    "arguments": {
      "arguments": {
        "symbols": ["RELIANCE", "TCS"],
        "start_datetime": "2025-01-01T00:00:00+05:30",
        "end_datetime": "2025-01-12T23:59:59+05:30",
        "interval": "daily"
      }
    }
  }
}
```

Expected: HTTP `200 OK`, `isError: false`, and the comparison results.

**Verified:** The tool successfully returned results for RELIANCE and TCS using the S3-backed dataset.

Stop the direct-test container:

```bash
docker stop kite-mcp-test
```

## 3. Start the container with RIE

RIE simulates the Lambda Runtime API locally.

The existing RIE binary is located at:

```text
.aws-lambda/aws-lambda-rie
```

Start the container:

```bash
docker run --rm -d \
  --platform linux/arm64 \
  --name kite-mcp-rie \
  -p 9000:9000 \
  -v "$PWD/.aws-lambda:/aws-lambda:ro" \
  -v "$HOME/.aws:/var/task/.aws:ro" \
  -e PROCESSED_DATA_SOURCE=s3 \
  -e PROCESSED_DATA_S3_BUCKET=nse-mcp-data \
  -e PROCESSED_DATA_S3_PREFIX=data/processed \
  --entrypoint /aws-lambda/aws-lambda-rie \
  kite-mcp-lambda:local \
  --runtime-interface-emulator-address=0.0.0.0:9000 \
  python -m uvicorn server.main:app --host 0.0.0.0 --port 8080
```

Check the container:

```bash
docker ps --filter name=kite-mcp-rie
```

Inspect startup logs:

```bash
docker logs -f kite-mcp-rie
```

Expected startup indicators:

```text
External agent lambda-adapter ... registered
StreamableHTTP session manager started
INFO: Application startup complete.
INFO: Uvicorn running on http://0.0.0.0:8080
INIT RTDONE(status: success)
```

## 4. Invoke the container through RIE

The RIE invocation endpoint is:

```text
http://localhost:9000/2015-03-31/functions/function/invocations
```

Send an API Gateway HTTP API v2 event containing an MCP initialization request:

```bash
curl -i -X POST \
  http://localhost:9000/2015-03-31/functions/function/invocations \
  -H "Content-Type: application/json" \
  -d '{
    "version": "2.0",
    "routeKey": "$default",
    "rawPath": "/mcp",
    "rawQueryString": "",
    "headers": {
      "content-type": "application/json",
      "accept": "application/json, text/event-stream",
      "mcp-protocol-version": "2025-03-26"
    },
    "requestContext": {
      "http": {
        "method": "POST",
        "path": "/mcp",
        "protocol": "HTTP/1.1",
        "sourceIp": "127.0.0.1",
        "userAgent": "rie-smoke-test"
      }
    },
    "body": "{\"jsonrpc\":\"2.0\",\"id\":1,\"method\":\"initialize\",\"params\":{\"protocolVersion\":\"2025-03-26\",\"capabilities\":{},\"clientInfo\":{\"name\":\"rie-smoke-test\",\"version\":\"1.0\"}}}",
    "isBase64Encoded": false
  }'
```

Expected response:

- HTTP `200 OK` from RIE.
- Lambda proxy response with `statusCode: 200`.
- `content-type: text/event-stream`.
- An `mcp-session-id` response header.
- MCP initialization result in the response body.

## 5. Problems encountered and resolutions

| Problem | Resolution |
|---|---|
| Container was initially tested directly, without RIE. | Used RIE separately to verify the Lambda invocation path. |
| Docker image architecture needed to match the ARM64 test environment. | Ran the container with `--platform linux/arm64`. |
| AWS credentials needed to be accessible inside the container. | Mounted `~/.aws` at `/var/task/.aws:ro`, matching the container's `HOME=/var/task`. |
| RIE binary was already present in the repository. | Reused `.aws-lambda/aws-lambda-rie` and mounted `.aws-lambda` at `/aws-lambda`. No download was necessary. |
| An initial RIE invocation using `{}` returned `200 OK` with `null`. | This was not a valid API Gateway event. The Lambda Web Adapter forwarded it to `/events`, which returned `404`. Replaced it with a valid API Gateway HTTP API v2 event targeting `/mcp`. |
| Initial logs showed `GET /` and `POST /events` returning `404`. | These were caused by the invalid test event, not MCP startup failure. The corrected event successfully reached `/mcp`. |
| `pyarrow` was missing when Arrow conversion was used. | Added `pyarrow>=26.0.1` to `requirements-lambda.txt` and rebuilt the image. |

## 6. Verified results

| Check | Result |
|---|---|
| ARM64 Lambda container starts | Passed |
| Direct Uvicorn startup | Passed |
| MCP session manager initialization | Passed |
| Direct MCP initialization | Passed |
| Direct MCP tool discovery | Passed |
| Direct `compare_symbols` tool call | Passed |
| RIE starts Lambda runtime | Passed |
| Lambda Web Adapter registers | Passed |
| Uvicorn starts under RIE | Passed |
| RIE invocation reaches `/mcp` | Passed |
| MCP initialization through RIE | Passed |

## Conclusion

The local Lambda container successfully starts under ARM64 RIE, the Lambda Web Adapter starts Uvicorn, and an MCP initialization request successfully travels through the RIE invocation endpoint to the `/mcp` endpoint.

Direct MCP testing also verified tool discovery and execution against the S3-backed Parquet dataset.

**T6.4 smoke test: startup and MCP initialization verified.**

Note: MCP tool discovery and execution were verified through direct HTTP testing. They have not yet been separately verified through RIE.
