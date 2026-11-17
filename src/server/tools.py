"""MCP tool definitions exposed by the server."""

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class Tool:
    name: str
    description: str
    handler: Callable[..., Any]


def _list_symbols(**kwargs: Any) -> list[str]:
    """Return symbols available in the data directory."""
    raise NotImplementedError


def _get_bars(**kwargs: Any) -> list[dict[str, Any]]:
    """Return OHLCV bars for a symbol and date range."""
    raise NotImplementedError


def _get_metadata(**kwargs: Any) -> dict[str, Any]:
    """Return instrument metadata for a symbol."""
    raise NotImplementedError


TOOLS: tuple[Tool, ...] = (
    Tool("list_symbols", "List available symbols", _list_symbols),
    Tool("get_bars", "Fetch OHLCV bars for a symbol", _get_bars),
    Tool("get_metadata", "Fetch instrument metadata", _get_metadata),
)


def registry() -> dict[str, Tool]:
    """Return tools keyed by name."""
    return {tool.name: tool for tool in TOOLS}