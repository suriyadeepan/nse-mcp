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
from server import tools as server_tools


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


TOOL_ARGUMENTS = {
    "get_bars": {
        "symbol": "AAA",
        "start_datetime": "2024-01-01T00:00:00Z",
        "end_datetime": "2024-01-02T00:00:00Z",
        "limit": 10,
    },
    "intraday_stats": {"symbol": "AAA", "trading_date": "2024-01-01"},
    "get_price_extremes": {
        "symbol": "AAA",
        "start_datetime": "2024-01-01T00:00:00Z",
        "end_datetime": "2024-01-02T00:00:00Z",
    },
    "get_volume_stats": {
        "symbol": "AAA",
        "start_datetime": "2024-01-01T00:00:00Z",
        "end_datetime": "2024-01-02T00:00:00Z",
        "bucket": "daily",
    },
    "compute_indicators": {
        "symbol": "AAA",
        "start_datetime": "2024-01-01T00:00:00Z",
        "end_datetime": "2024-01-02T00:00:00Z",
        "indicators": ["SMA"],
    },
    "compare_symbols": {
        "symbols": ["AAA", "BBB"],
        "start_datetime": "2024-01-01T00:00:00Z",
        "end_datetime": "2024-01-02T00:00:00Z",
    },
}

EMPTY_RESULTS = {
    "get_bars": {"bars": [], "returned_count": 0},
    "intraday_stats": {
        "open": None,
        "close": None,
        "high": None,
        "low": None,
        "total_volume": None,
        "vwap": None,
        "absolute_return": None,
        "percentage_return": None,
        "bar_count": 0,
        "first_timestamp": None,
        "last_timestamp": None,
    },
    "get_price_extremes": {
        "highest_high": None,
        "highest_high_timestamp": None,
        "lowest_low": None,
        "lowest_low_timestamp": None,
        "range_absolute": None,
        "range_percentage": None,
    },
    "get_volume_stats": {
        "total_volume": None,
        "average_volume": None,
        "maximum_volume": None,
        "minimum_volume": None,
        "average_bucket_volume": None,
        "volume_by_bucket": [],
        "bar_count": 0,
    },
    "compute_indicators": {
        "values": [],
        "indicator_parameters": {"SMA": {"period": 14}},
        "indicator_status": {"SMA": "no_data"},
        "returned_count": 0,
    },
    "compare_symbols": {
        "common_trading_dates": [],
        "common_trading_days": 0,
        "symbols": [],
    },
}

ANALYTICS_FUNCTIONS = {
    "get_bars": "get_bars",
    "intraday_stats": "intraday_stats",
    "get_price_extremes": "get_price_extremes",
    "get_volume_stats": "get_volume_stats",
    "compute_indicators": "compute_indicators",
    "compare_symbols": "compare_symbols",
}


@pytest.mark.anyio
async def test_registered_analytics_tools_return_structured_empty_results(monkeypatch):
    calls = {}
    for name, function_name in ANALYTICS_FUNCTIONS.items():
        def fake_analytics(*, tool_name=name, **kwargs):
            calls[tool_name] = kwargs
            return EMPTY_RESULTS[tool_name]

        monkeypatch.setattr(server_tools.analytics, function_name, fake_analytics)

    async with Client(server_main.mcp) as client:
        listed = await client.list_tools()
        assert {tool.name for tool in listed.tools} == set(ANALYTICS_FUNCTIONS)
        assert all(tool.description for tool in listed.tools)
        assert all(tool.output_schema is not None for tool in listed.tools)

        results = {}
        for name, arguments in TOOL_ARGUMENTS.items():
            result = await client.call_tool(name, {"arguments": arguments})
            assert result.is_error is False
            results[name] = result.structured_content

    assert results == EMPTY_RESULTS
    assert set(calls) == set(ANALYTICS_FUNCTIONS)
    assert calls["get_bars"]["symbol"] == "AAA"
    assert calls["intraday_stats"]["trading_date"].isoformat() == "2024-01-01"
    assert calls["get_volume_stats"]["bucket"] == "daily"
    assert calls["compute_indicators"]["indicators"] == ["SMA"]
    assert calls["compare_symbols"]["symbols"] == ["AAA", "BBB"]


@pytest.mark.anyio
async def test_registered_tool_rejects_invalid_arguments_before_execution(monkeypatch):
    invoked = False

    def should_not_run(**kwargs):
        nonlocal invoked
        invoked = True
        return EMPTY_RESULTS["get_bars"]

    monkeypatch.setattr(server_tools.analytics, "get_bars", should_not_run)
    arguments = dict(TOOL_ARGUMENTS["get_bars"], limit=0)

    async with Client(server_main.mcp) as client:
        result = await client.call_tool("get_bars", {"arguments": arguments})

    assert result.is_error is True
    assert invoked is False


@pytest.mark.anyio
async def test_registered_tool_returns_clear_analytics_and_execution_errors(monkeypatch):
    def invalid_symbol(**kwargs):
        from server.validation import AnalyticsInputError

        raise AnalyticsInputError("unknown symbol: 'MISSING'")

    monkeypatch.setattr(server_tools.analytics, "get_bars", invalid_symbol)
    async with Client(server_main.mcp) as client:
        validation_error = await client.call_tool(
            "get_bars", {"arguments": TOOL_ARGUMENTS["get_bars"]}
        )

    assert validation_error.is_error is True
    assert "unknown symbol: 'MISSING'" in validation_error.content[0].text

    def failed_query(**kwargs):
        raise RuntimeError("internal query details")

    monkeypatch.setattr(server_tools.analytics, "get_bars", failed_query)
    async with Client(server_main.mcp) as client:
        execution_error = await client.call_tool(
            "get_bars", {"arguments": TOOL_ARGUMENTS["get_bars"]}
        )

    assert execution_error.is_error is True
    message = execution_error.content[0].text
    assert "analytics execution failed" in message
    assert "internal query details" not in message
