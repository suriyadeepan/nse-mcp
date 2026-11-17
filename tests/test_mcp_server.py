"""Tests for the local FastMCP server entry points."""

import sys

import pytest
from mcp.client.session import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client

from server import main as server_main


def test_main_runs_fastmcp_over_stdio(monkeypatch):
    monkeypatch.setattr(sys, "argv", ["kite-mcp"])
    transports = []
    monkeypatch.setattr(
        server_main.mcp,
        "run",
        lambda *, transport: transports.append(transport),
    )

    server_main.main()

    assert transports == ["stdio"]


def test_streamable_http_asgi_app_exposes_mcp_endpoint():
    assert callable(server_main.app)
    assert "/mcp" in {route.path for route in server_main.app.routes}


@pytest.mark.anyio
async def test_server_starts_and_initializes_over_stdio():
    parameters = StdioServerParameters(
        command=sys.executable,
        args=["-m", "server.main"],
    )

    async with stdio_client(parameters) as (read_stream, write_stream):
        async with ClientSession(read_stream, write_stream) as session:
            result = await session.initialize()

    assert result.serverInfo.name == "kite-mcp"
