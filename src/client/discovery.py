"""Tool discovery against an MCP server."""

from contextlib import asynccontextmanager
from typing import Any, AsyncIterator

from mcp import Client, types


DEFAULT_SERVER_URL = "http://localhost:8000/mcp"


class MCPConnectionError(ConnectionError):
    """Raised when the Streamable HTTP MCP endpoint cannot be reached."""


@asynccontextmanager
async def connect_to_server(
    server_url: str = DEFAULT_SERVER_URL,
    timeout: float = 10.0,
) -> AsyncIterator[Client]:
    """Open a Streamable HTTP MCP session and report connection failures clearly."""
    client = Client(server_url, read_timeout_seconds=timeout)
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


async def list_tools(
    server_url: str = DEFAULT_SERVER_URL,
    timeout: float = 10.0,
) -> list[types.Tool]:
    """Discover every tool from the server, following MCP list pagination."""
    async with connect_to_server(server_url, timeout=timeout) as client:
        tools: list[types.Tool] = []
        cursor: str | None = None
        while True:
            result = await client.list_tools(cursor=cursor)
            tools.extend(result.tools)
            cursor = result.next_cursor
            if cursor is None:
                return tools


def to_openai_tool(tool: types.Tool) -> dict[str, Any]:
    """Convert one discovered MCP tool to an OpenAI function-tool definition."""
    return {
        "type": "function",
        "function": {
            "name": tool.name,
            "description": tool.description or "",
            "parameters": tool.input_schema,
        },
    }


def to_openai_tools(tools: list[types.Tool]) -> list[dict[str, Any]]:
    """Convert discovered MCP tools without embedding server-specific metadata."""
    return [to_openai_tool(tool) for tool in tools]


def call_tool(server_url: str, name: str, arguments: dict[str, Any]) -> Any:
    """Invoke `name` on the server with `arguments`."""
    raise NotImplementedError


async def discover_tools(server_url: str = DEFAULT_SERVER_URL) -> dict[str, types.Tool]:
    """Return discovered tools keyed by name."""
    return {tool.name: tool for tool in await list_tools(server_url)}
