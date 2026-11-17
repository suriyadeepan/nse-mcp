"""Tool discovery against an MCP server."""

from contextlib import asynccontextmanager
from typing import Any, AsyncIterator

from mcp import Client


DEFAULT_SERVER_URL = "http://localhost:8000/mcp"


class MCPConnectionError(ConnectionError):
    """Raised when the Streamable HTTP MCP endpoint cannot be reached."""


@asynccontextmanager
async def connect_to_server(
    server_url: str = DEFAULT_SERVER_URL,
) -> AsyncIterator[Client]:
    """Open a Streamable HTTP MCP session and report connection failures clearly."""
    client = Client(server_url)
    try:
        await client.__aenter__()
    except Exception as exc:
        # Avoid echoing the URL: it may contain credentials or sensitive query data.
        raise MCPConnectionError(
            "Could not connect to the MCP server over Streamable HTTP. "
            "Check that the server is running and the endpoint URL is correct."
        ) from exc
    try:
        yield client
    finally:
        await client.__aexit__(None, None, None)


def list_tools(server_url: str, timeout: float = 10.0) -> list[dict[str, Any]]:
    """Return tool descriptors from the server's `tools/list` endpoint."""
    raise NotImplementedError


def call_tool(server_url: str, name: str, arguments: dict[str, Any]) -> Any:
    """Invoke `name` on the server with `arguments`."""
    raise NotImplementedError


def discover_tools(server_url: str) -> dict[str, Any]:
    """Return discovered tools keyed by name."""
    return {tool["name"]: tool for tool in list_tools(server_url)}
