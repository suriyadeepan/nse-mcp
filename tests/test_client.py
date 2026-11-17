"""Tests for the client's Streamable HTTP MCP connection."""

import asyncio
import json
import socket
from contextlib import asynccontextmanager
from types import SimpleNamespace
from typing import Any, AsyncIterator

import pytest
import uvicorn
from mcp.server import MCPServer
from server.tools import register_tools

from client.agent import Agent
from client.discovery import (
    MCPConnectionError,
    connect_to_server,
    list_tools,
    to_openai_tools,
)


class FakeOpenAI:
    def __init__(self, responses: list[Any]) -> None:
        self.responses = iter(responses)
        self.requests: list[dict[str, Any]] = []
        self.chat = SimpleNamespace(completions=self)

    async def create(self, **kwargs: Any) -> Any:
        self.requests.append(kwargs)
        return next(self.responses)


def completion(content: str | None = None, tool_calls: list[Any] | None = None) -> Any:
    message = SimpleNamespace(content=content, tool_calls=tool_calls or [])
    return SimpleNamespace(choices=[SimpleNamespace(message=message)])


def tool_call(call_id: str, name: str, arguments: str) -> Any:
    return SimpleNamespace(
        id=call_id,
        function=SimpleNamespace(name=name, arguments=arguments),
    )


@asynccontextmanager
async def serve_mcp(mcp_server: MCPServer) -> AsyncIterator[str]:
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    sock.listen()
    port = sock.getsockname()[1]
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
        yield f"http://127.0.0.1:{port}/mcp"
    finally:
        http_server.should_exit = True
        await task


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


@pytest.mark.anyio
async def test_discovers_and_converts_server_defined_tools_over_http():
    mcp_server = MCPServer("dynamic-tools")

    @mcp_server.tool(name="custom_lookup", description="Find custom records.")
    def custom_lookup(query: str, limit: int = 3) -> str:
        return query * limit
    register_tools(mcp_server)

    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    sock.listen()
    port = sock.getsockname()[1]
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

        discovered = await list_tools(f"http://127.0.0.1:{port}/mcp")
        converted = to_openai_tools(discovered)
        agent = Agent(f"http://127.0.0.1:{port}/mcp")
        await agent.connect()
    finally:
        http_server.should_exit = True
        await task

    discovered_by_name = {tool.name: tool for tool in discovered}
    converted_by_name = {item["function"]["name"]: item for item in converted}
    assert len(discovered) == 7
    assert {
        "get_bars",
        "intraday_stats",
        "get_price_extremes",
        "get_volume_stats",
        "compute_indicators",
        "compare_symbols",
        "custom_lookup",
    } == set(discovered_by_name)
    assert converted_by_name["custom_lookup"] == {
        "type": "function",
        "function": {
            "name": discovered_by_name["custom_lookup"].name,
            "description": discovered_by_name["custom_lookup"].description,
            "parameters": discovered_by_name["custom_lookup"].input_schema,
        },
    }
    assert discovered_by_name["custom_lookup"].input_schema["properties"].keys() == {
        "query",
        "limit",
    }
    assert agent.openai_tools == converted


@pytest.mark.anyio
async def test_agent_executes_model_selected_tool_and_returns_result_to_openai():
    mcp_server = MCPServer("agent-tools")
    executions: list[dict[str, Any]] = []

    @mcp_server.tool(name="custom_lookup", description="Find custom records.")
    def custom_lookup(query: str, limit: int = 3) -> str:
        executions.append({"query": query, "limit": limit})
        return query * limit

    fake_openai = FakeOpenAI(
        [
            completion(
                tool_calls=[tool_call("call-1", "custom_lookup", '{"query":"A","limit":2}')]
            ),
            completion("Found AA."),
        ]
    )
    async with serve_mcp(mcp_server) as url:
        agent = Agent(url, openai_client=fake_openai)
        answer = await agent.run("Look up A twice")

    assert answer == "Found AA."
    assert executions == [{"query": "A", "limit": 2}]
    assert fake_openai.requests[0]["tools"] == agent.openai_tools
    returned_tool_result = fake_openai.requests[1]["messages"][-1]
    assert returned_tool_result["role"] == "tool"
    assert "AA" in returned_tool_result["content"]


@pytest.mark.anyio
async def test_agent_rejects_invalid_arguments_before_mcp_execution():
    mcp_server = MCPServer("invalid-arguments")
    executions: list[Any] = []

    @mcp_server.tool(name="custom_lookup", description="Find custom records.")
    def custom_lookup(query: str) -> str:
        executions.append(query)
        return query

    fake_openai = FakeOpenAI(
        [
            completion(
                tool_calls=[tool_call("call-1", "custom_lookup", '{"query":42}')]
            ),
            completion("The request had invalid arguments."),
        ]
    )
    async with serve_mcp(mcp_server) as url:
        agent = Agent(url, openai_client=fake_openai)
        answer = await agent.run("Look up something")

    assert answer == "The request had invalid arguments."
    assert executions == []
    error_result = json.loads(fake_openai.requests[1]["messages"][-1]["content"])
    assert "Invalid arguments" in error_result["error"]


@pytest.mark.anyio
async def test_agent_returns_safe_mcp_execution_errors_to_openai():
    mcp_server = MCPServer("execution-error")

    @mcp_server.tool(name="custom_lookup", description="Find custom records.")
    def custom_lookup(query: str) -> str:
        raise RuntimeError("internal query detail")

    fake_openai = FakeOpenAI(
        [
            completion(
                tool_calls=[tool_call("call-1", "custom_lookup", '{"query":"A"}')]
            ),
            completion("The lookup failed."),
        ]
    )
    async with serve_mcp(mcp_server) as url:
        agent = Agent(url, openai_client=fake_openai)
        answer = await agent.run("Look up A")

    assert answer == "The lookup failed."
    error_result = json.loads(fake_openai.requests[1]["messages"][-1]["content"])
    assert "execution error" in error_result["error"]
    assert "internal query detail" not in error_result["error"]


@pytest.mark.anyio
async def test_agent_handles_multiple_calls_and_obeys_round_limit():
    mcp_server = MCPServer("multiple-rounds")
    executions: list[str] = []

    @mcp_server.tool(name="custom_lookup", description="Find custom records.")
    def custom_lookup(query: str) -> str:
        executions.append(query)
        return query

    fake_openai = FakeOpenAI(
        [
            completion(
                tool_calls=[
                    tool_call("call-1", "custom_lookup", '{"query":"A"}'),
                    tool_call("call-2", "custom_lookup", '{"query":"B"}'),
                ]
            ),
            completion(
                tool_calls=[tool_call("call-3", "custom_lookup", '{"query":"C"}')]
            ),
            completion("Lookups completed."),
        ]
    )
    async with serve_mcp(mcp_server) as url:
        agent = Agent(url, openai_client=fake_openai, max_tool_rounds=2)
        answer = await agent.run("Look up A, B, and C")

    assert answer == "Lookups completed."
    assert executions == ["A", "B", "C"]
    assert len(fake_openai.requests) == 3
    assert fake_openai.requests[-1]["tool_choice"] == "none"
