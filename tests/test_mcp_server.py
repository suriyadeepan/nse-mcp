"""Tests for the local MCP server entry points and transports."""

import asyncio
import socket
import sys

import pytest
import uvicorn
from mcp import Client
from mcp.client.stdio import StdioServerParameters
from mcp.server import MCPServer

from server import main as server_main


@pytest.fixture
def anyio_backend():
    return "asyncio"


def test_main_runs_mcpserver_over_stdio(monkeypatch):
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
    assert isinstance(server_main.mcp, MCPServer)
    assert callable(server_main.app)
    assert "/mcp" in {route.path for route in server_main.app.routes}


@pytest.mark.anyio
async def test_server_starts_and_initializes_over_stdio():
    parameters = StdioServerParameters(
        command=sys.executable,
        args=["-m", "server.main"],
    )

    async with Client(parameters) as client:
        assert client.server_info.name == "kite-mcp"


@pytest.mark.anyio
async def test_server_starts_over_streamable_http():
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

        async with Client(f"http://127.0.0.1:{port}/mcp") as client:
            assert client.server_info.name == "kite-mcp"
    finally:
        server.should_exit = True
        await task
