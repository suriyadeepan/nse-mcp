"""Tool discovery against an MCP server."""

from contextlib import asynccontextmanager
from typing import Any, AsyncIterator

import httpx2
from jsonschema import Draft202012Validator, ValidationError
from mcp import Client, types
from mcp.client.streamable_http import streamable_http_client


DEFAULT_SERVER_URL = "http://localhost:8000/mcp"


class MCPConnectionError(ConnectionError):
    """Raised when the Streamable HTTP MCP endpoint cannot be reached."""


class ToolArgumentError(ValueError):
    """Raised when model-generated arguments do not match a discovered schema."""


class ToolExecutionError(RuntimeError):
    """Raised when an MCP tool reports an execution failure."""


@asynccontextmanager
async def connect_to_server(
    server_url: str = DEFAULT_SERVER_URL,
    timeout: float = 10.0,
    bearer_token: str | None = None,
    http_client: httpx2.AsyncClient | None = None,
) -> AsyncIterator[Client]:
    """Open a Streamable HTTP MCP session and report connection failures clearly."""
    owns_http_client = http_client is None
    if http_client is None and bearer_token:
        http_client = httpx2.AsyncClient(
            headers={"Authorization": f"Bearer {bearer_token}"}
        )
    if http_client is not None:
        transport = streamable_http_client(server_url, http_client=http_client)
        client = Client(transport, read_timeout_seconds=timeout)
    else:
        transport = None
        client = Client(server_url, read_timeout_seconds=timeout)
    try:
        await client.__aenter__()
    except Exception:
        if owns_http_client and http_client is not None:
            await http_client.aclose()
        # Avoid echoing the URL: it may contain credentials or sensitive query data.
        raise MCPConnectionError(
            "Could not connect to the MCP server over Streamable HTTP. "
            "Check that the server is running and the endpoint URL is correct."
        ) from None
    try:
        yield client
    finally:
        try:
            await client.__aexit__(None, None, None)
        finally:
            if owns_http_client and http_client is not None:
                await http_client.aclose()


async def list_tools(
    server_url: str = DEFAULT_SERVER_URL,
    timeout: float = 10.0,
    bearer_token: str | None = None,
) -> list[types.Tool]:
    """Discover every tool from the server, following MCP list pagination."""
    async with connect_to_server(
        server_url, timeout=timeout, bearer_token=bearer_token
    ) as client:
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


def validate_tool_arguments(tool: types.Tool, arguments: Any) -> None:
    """Validate model-generated arguments against the server's JSON Schema."""
    try:
        Draft202012Validator(
            tool.input_schema,
            format_checker=Draft202012Validator.FORMAT_CHECKER,
        ).validate(arguments)
    except ValidationError as exc:
        path = "/" + "/".join(str(part) for part in exc.absolute_path)
        raise ToolArgumentError(
            f"Invalid arguments for MCP tool {tool.name!r} at {path}: "
            "arguments do not match the discovered schema."
        ) from exc


async def call_tool(
    client: Client,
    tool: types.Tool,
    arguments: Any,
) -> Any:
    """Validate arguments and invoke the discovered MCP tool."""
    validate_tool_arguments(tool, arguments)
    result = await client.call_tool(tool.name, arguments)
    if result.is_error:
        raise ToolExecutionError(
            f"MCP tool {tool.name!r} reported an execution error."
        )
    if result.structured_content is not None:
        return result.structured_content
    return [content.model_dump(mode="json") for content in result.content]


async def discover_tools(
    server_url: str = DEFAULT_SERVER_URL,
    bearer_token: str | None = None,
) -> dict[str, types.Tool]:
    """Return discovered tools keyed by name."""
    return {
        tool.name: tool
        for tool in await list_tools(server_url, bearer_token=bearer_token)
    }
