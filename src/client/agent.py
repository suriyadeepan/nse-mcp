"""OpenAI agent that discovers and invokes MCP tools dynamically."""

import asyncio
import json
import os
from typing import Any

from openai import AsyncOpenAI

from client.discovery import (
    DEFAULT_SERVER_URL,
    ToolArgumentError,
    ToolExecutionError,
    call_tool,
    connect_to_server,
    discover_tools,
    to_openai_tools,
)


class Agent:
    """Tool-using agent backed by an HTTP MCP server and the OpenAI API."""

    def __init__(
        self,
        server_url: str = DEFAULT_SERVER_URL,
        model: str = "",
        *,
        openai_client: Any = None,
        max_tool_rounds: int = 3,
    ) -> None:
        if max_tool_rounds < 1:
            raise ValueError("max_tool_rounds must be positive")
        self.server_url = server_url
        self.model = model or os.environ.get("OPENAI_MODEL", "gpt-4o-mini")
        self.openai_client = openai_client
        self.max_tool_rounds = max_tool_rounds
        self.tools: dict[str, Any] = {}
        self.openai_tools: list[dict[str, Any]] = []

    async def connect(self) -> dict[str, Any]:
        """Discover the tools exposed by the server and prepare OpenAI definitions."""
        self.tools = await discover_tools(self.server_url)
        self.openai_tools = to_openai_tools(list(self.tools.values()))
        return self.tools

    async def _run_with_client(self, prompt: str, client: Any) -> str:
        if not self.tools:
            await self.connect()

        messages: list[dict[str, Any]] = [{"role": "user", "content": prompt}]
        async with connect_to_server(self.server_url) as mcp_client:
            for _ in range(self.max_tool_rounds):
                response = await client.chat.completions.create(
                    model=self.model,
                    messages=messages,
                    tools=self.openai_tools,
                    tool_choice="auto",
                )
                message = response.choices[0].message
                tool_calls = message.tool_calls or []
                if not tool_calls:
                    return message.content or ""

                messages.append(
                    {
                        "role": "assistant",
                        "content": message.content,
                        "tool_calls": [
                            {
                                "id": item.id,
                                "type": "function",
                                "function": {
                                    "name": item.function.name,
                                    "arguments": item.function.arguments,
                                },
                            }
                            for item in tool_calls
                        ],
                    }
                )

                for item in tool_calls:
                    name = item.function.name
                    try:
                        tool = self.tools.get(name)
                        if tool is None:
                            raise ToolExecutionError(
                                f"OpenAI selected unknown MCP tool {name!r}."
                            )
                        try:
                            arguments = json.loads(item.function.arguments)
                        except (TypeError, json.JSONDecodeError) as exc:
                            raise ToolArgumentError(
                                f"Invalid JSON arguments for MCP tool {name!r}."
                            ) from exc
                        result = await call_tool(mcp_client, tool, arguments)
                    except (ToolArgumentError, ToolExecutionError) as exc:
                        result = {"error": str(exc)}

                    messages.append(
                        {
                            "role": "tool",
                            "tool_call_id": item.id,
                            "content": json.dumps(result, ensure_ascii=False, default=str),
                        }
                    )

            # Ask for a final answer after the configured number of tool rounds.
            response = await client.chat.completions.create(
                model=self.model,
                messages=messages,
                tools=self.openai_tools,
                tool_choice="none",
            )
            return response.choices[0].message.content or ""

    async def run(self, prompt: str) -> str:
        """Answer a prompt, executing model-selected MCP tools as needed."""
        if self.openai_client is not None:
            return await self._run_with_client(prompt, self.openai_client)
        async with AsyncOpenAI() as client:
            return await self._run_with_client(prompt, client)


def run(
    server_url: str,
    prompt: str,
    model: str = "",
    *,
    openai_client: Any = None,
) -> str:
    """Connect an agent and answer `prompt` using OpenAI and MCP tools."""
    agent = Agent(server_url, model=model, openai_client=openai_client)
    return asyncio.run(agent.run(prompt))
