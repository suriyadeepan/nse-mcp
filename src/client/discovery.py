"""Tool discovery against an MCP server."""

from typing import Any


def list_tools(server_url: str, timeout: float = 10.0) -> list[dict[str, Any]]:
    """Return tool descriptors from the server's `tools/list` endpoint."""
    raise NotImplementedError


def call_tool(server_url: str, name: str, arguments: dict[str, Any]) -> Any:
    """Invoke `name` on the server with `arguments`."""
    raise NotImplementedError


def discover_tools(server_url: str) -> dict[str, Any]:
    """Return discovered tools keyed by name."""
    return {tool["name"]: tool for tool in list_tools(server_url)}