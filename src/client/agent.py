"""Agent loop that drives the MCP server tools."""

from collections.abc import Sequence
from typing import Any

from client.discovery import discover_tools


class Agent:
    """Minimal tool-using agent bound to a discovered tool set."""

    def __init__(self, server_url: str, model: str = "") -> None:
        self.server_url = server_url
        self.model = model
        self.tools: dict[str, Any] = {}

    def connect(self) -> dict[str, Any]:
        """Discover the tools exposed by the server."""
        self.tools = discover_tools(self.server_url)
        return self.tools

    def run(self, prompt: str) -> str:
        """Answer `prompt`, calling tools when needed."""
        raise NotImplementedError


def run(server_url: str, prompt: str, model: str = "") -> str:
    """Connect an agent to `server_url` and answer `prompt`."""
    agent = Agent(server_url, model=model)
    agent.connect()
    return agent.run(prompt)