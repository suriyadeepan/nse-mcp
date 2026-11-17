"""Tests for the client's Streamable HTTP MCP connection."""

import asyncio
import socket

import pytest
import uvicorn
from mcp.server import MCPServer

from client.discovery import MCPConnectionError, connect_to_server


@pytest.mark.anyio
async def test_connect_to_streamable_http_endpoint():
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    sock.listen()
    port = sock.getsockname()[1]
    mcp_server = MCPServer("test-client")
    http_server = uvicorn.Server(
        uvicorn.Config(mcp_server.streamable_http_app(), log_level="critical")
    )
    task = asyncio.create_task(http_server.serve(sockets=[sock]))

    try:
        for _ in range(100):
            if http_server.started:
                break
            if task.done():
                await task
            await asyncio.sleep(0.05)
        assert http_server.started, "ASGI server did not start"

        async with connect_to_server(f"http://127.0.0.1:{port}/mcp") as client:
            assert client._session is not None
    finally:
        http_server.should_exit = True
        await task


@pytest.mark.anyio
async def test_connection_failure_has_clear_non_sensitive_message():
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()

    url = f"http://user:secret@127.0.0.1:{port}/mcp?token=hidden"
    with pytest.raises(MCPConnectionError, match="Streamable HTTP") as error:
        async with connect_to_server(url):
            pytest.fail("connection unexpectedly succeeded")

    assert "secret" not in str(error.value)
    assert "hidden" not in str(error.value)
