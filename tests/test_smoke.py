"""Smoke tests for the market data MCP package layout."""

import importlib

MODULES = [
    "server",
    "server.main",
    "server.tools",
    "server.data",
    "client",
    "client.main",
    "client.agent",
    "client.discovery",
]


def test_modules_import():
    for name in MODULES:
        importlib.import_module(name)


def test_tool_registry_is_unique():
    from server.tools import registry

    tools = registry()
    assert "list_symbols" in tools
    assert "get_bars" in tools
    assert len(tools) == 3