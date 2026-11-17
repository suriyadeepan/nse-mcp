"""MCP tool definitions exposed by the server."""

import logging
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from mcp.server import MCPServer
from mcp.server.mcpserver.exceptions import ToolError

from . import analytics
from .validation import (
    TOOL_DESCRIPTIONS,
    AnalyticsError,
    CompareSymbolsArguments,
    ComputeIndicatorsArguments,
    GetBarsArguments,
    IntradayStatsArguments,
    PriceExtremesArguments,
    ToolArguments,
    VolumeStatsArguments,
)

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Tool:
    name: str
    description: str
    arguments: type[ToolArguments]
    handler: Callable[..., Any]


def _invoke(
    handler: Callable[..., Any], arguments: ToolArguments
) -> Any:
    """Call an analytics function and expose safe, consistent tool errors."""
    try:
        return handler(**arguments.model_dump())
    except AnalyticsError as exc:
        raise ToolError(exc.message) from exc
    except Exception as exc:
        logger.exception("analytics tool execution failed")
        raise ToolError(
            "analytics execution failed; check that processed market data is available"
        ) from exc


def _get_bars(arguments: GetBarsArguments) -> analytics.BarsResult:
    """Return ordered OHLCV candles for a symbol and inclusive UTC range."""
    return _invoke(analytics.get_bars, arguments)


def _intraday_stats(arguments: IntradayStatsArguments) -> analytics.IntradayStatsResult:
    """Summarize a symbol's market session on an IST calendar date."""
    return _invoke(analytics.intraday_stats, arguments)


def _get_price_extremes(
    arguments: PriceExtremesArguments,
) -> analytics.PriceExtremesResult:
    """Find the highest high and lowest low in a UTC time range."""
    return _invoke(analytics.get_price_extremes, arguments)


def _get_volume_stats(arguments: VolumeStatsArguments) -> analytics.VolumeStatsResult:
    """Summarize candle volumes and hourly or daily IST bucket totals."""
    return _invoke(analytics.get_volume_stats, arguments)


def _compute_indicators(
    arguments: ComputeIndicatorsArguments,
) -> analytics.IndicatorsResult:
    """Calculate supported technical indicators with prior-candle warm-up."""
    return _invoke(analytics.compute_indicators, arguments)


def _compare_symbols(
    arguments: CompareSymbolsArguments,
) -> analytics.CompareSymbolsResult:
    """Compare symbols using daily metrics on their common trading dates."""
    return _invoke(analytics.compare_symbols, arguments)


TOOLS: tuple[Tool, ...] = (
    Tool(
        "get_bars",
        TOOL_DESCRIPTIONS["get_bars"],
        GetBarsArguments,
        _get_bars,
    ),
    Tool(
        "intraday_stats",
        TOOL_DESCRIPTIONS["intraday_stats"],
        IntradayStatsArguments,
        _intraday_stats,
    ),
    Tool(
        "get_price_extremes",
        TOOL_DESCRIPTIONS["get_price_extremes"],
        PriceExtremesArguments,
        _get_price_extremes,
    ),
    Tool(
        "get_volume_stats",
        TOOL_DESCRIPTIONS["get_volume_stats"],
        VolumeStatsArguments,
        _get_volume_stats,
    ),
    Tool(
        "compute_indicators",
        TOOL_DESCRIPTIONS["compute_indicators"],
        ComputeIndicatorsArguments,
        _compute_indicators,
    ),
    Tool(
        "compare_symbols",
        TOOL_DESCRIPTIONS["compare_symbols"],
        CompareSymbolsArguments,
        _compare_symbols,
    ),
)


def registry() -> dict[str, Tool]:
    """Return tools keyed by name."""
    return {tool.name: tool for tool in TOOLS}


def register_tools(server: MCPServer) -> None:
    """Register each analytics handler with an MCP SDK 2.x server."""
    for tool in TOOLS:
        server.tool(
            name=tool.name,
            description=tool.description,
            structured_output=True,
        )(tool.handler)
