"""End-to-end ASGI and MCP Streamable HTTP integration tests."""

import asyncio
from contextlib import asynccontextmanager
import socket

import httpx
import httpx2
import pytest
import uvicorn
from mcp import Client
from mcp.client.streamable_http import streamable_http_client

from server import main as server_main
from server import tools as server_tools


@asynccontextmanager
async def serve_http_app():
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    sock.listen()
    port = sock.getsockname()[1]
    server = uvicorn.Server(uvicorn.Config(server_main.app, log_level="critical"))
    task = asyncio.create_task(server.serve(sockets=[sock]))
    try:
        for _ in range(100):
            if server.started:
                break
            if task.done():
                await task
            await asyncio.sleep(0.05)
        assert server.started, "ASGI server did not start"
        yield f"http://127.0.0.1:{port}"
    finally:
        server.should_exit = True
        await task


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture(autouse=True)
def configure_test_bearer_token(monkeypatch):
    monkeypatch.setenv("MCP_BEARER_TOKEN", "http-test-token-with-at-least-32-chars")


@pytest.mark.anyio
async def test_asgi_app_returns_http_response_for_unknown_route():
    transport = httpx.ASGITransport(app=server_main.app)
    async with httpx.AsyncClient(
        transport=transport,
        base_url="http://test",
        headers={"Authorization": "Bearer http-test-token-with-at-least-32-chars"},
    ) as http_client:
        response = await http_client.get("/not-an-mcp-route")

    assert response.status_code == 404


@pytest.mark.anyio
async def test_streamable_http_initializes_lists_tools_and_executes_tool(monkeypatch):
    expected_bars = [
        {
            "timestamp": "2024-01-01T00:00:00Z",
            "open": 100.0,
            "high": 105.0,
            "low": 99.0,
            "close": 104.0,
            "volume": 1200,
        }
    ]
    analytics_calls = []

    def get_bars(**arguments):
        analytics_calls.append(arguments)
        return {"bars": expected_bars, "returned_count": 1}

    monkeypatch.setattr(server_tools.analytics, "get_bars", get_bars)

    async with serve_http_app() as base_url:
        async with httpx2.AsyncClient(
            headers={"Authorization": "Bearer http-test-token-with-at-least-32-chars"}
        ) as authorized_http_client:
            transport = streamable_http_client(
                f"{base_url}/mcp", http_client=authorized_http_client
            )
            async with Client(transport) as mcp_client:
                assert mcp_client.server_info.name == "kite-mcp"

                listed = await mcp_client.list_tools()
                tool_names = {tool.name for tool in listed.tools}
                assert tool_names == {
                    "get_bars",
                    "intraday_stats",
                    "get_price_extremes",
                    "get_volume_stats",
                    "compute_indicators",
                    "compare_symbols",
                }
                assert next(tool for tool in listed.tools if tool.name == "get_bars").input_schema

                result = await mcp_client.call_tool(
                    "get_bars",
                    {
                        "arguments": {
                            "symbol": "RELIANCE",
                            "start_datetime": "2024-01-01T00:00:00Z",
                            "end_datetime": "2024-01-02T00:00:00Z",
                            "limit": 10,
                        }
                    },
                )

    assert result.is_error is False
    assert result.structured_content == {
        "bars": expected_bars,
        "returned_count": 1,
    }
    assert len(analytics_calls) == 1
    assert analytics_calls[0]["symbol"] == "RELIANCE"
    assert analytics_calls[0]["start_datetime"].isoformat() == (
        "2024-01-01T00:00:00+00:00"
    )
    assert analytics_calls[0]["end_datetime"].isoformat() == (
        "2024-01-02T00:00:00+00:00"
    )
    assert analytics_calls[0]["limit"] == 10
