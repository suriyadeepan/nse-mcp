"""Agent loop that drives the MCP server tools."""

import asyncio
from collections.abc import Sequence
from typing import Any

from client.discovery import discover_tools, to_openai_tools


class Agent:
    """Minimal tool-using agent bound to a discovered tool set."""

    def __init__(self, server_url: str, model: str = "") -> None:
        self.server_url = server_url
        self.model = model
        self.tools: dict[str, Any] = {}
        self.openai_tools: list[dict[str, Any]] = []

    async def connect(self) -> dict[str, Any]:
        """Discover the tools exposed by the server."""
        self.tools = await discover_tools(self.server_url)
        self.openai_tools = to_openai_tools(list(self.tools.values()))
        return self.tools

    def run(self, prompt: str) -> str:
        """Answer `prompt`, calling tools when needed."""
        raise NotImplementedError


def run(server_url: str, prompt: str, model: str = "") -> str:
    """Connect an agent to `server_url` and answer `prompt`."""
    agent = Agent(server_url, model=model)
    asyncio.run(agent.connect())
    return agent.run(prompt)
