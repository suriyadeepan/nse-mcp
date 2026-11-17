"""OpenAI agent that discovers and invokes MCP tools dynamically."""

import asyncio
import json
import os
import re
from time import perf_counter
from typing import Any

from openai import AsyncOpenAI
import tiktoken

from client.discovery import (
    DEFAULT_SERVER_URL,
    ToolArgumentError,
    ToolExecutionError,
    call_tool,
    connect_to_server,
    discover_tools,
    to_openai_tools,
)


MAX_TOOL_RESULT_TOKENS = 12_000
MAX_CONVERSATION_TOOL_RESULT_TOKENS = 24_000
_SECRET_PATTERNS = (
    re.compile(r"(?i)\b(bearer\s+)[A-Za-z0-9._~+/=-]+"),
    re.compile(
        r"(?i)(\b(?:api[_-]?key|token|auth(?:orization)?|secret|password)\b\s*[:=]\s*[\"']?)[^\s,;\"']+"
    ),
    re.compile(r"\b(?:sk|pk)-(?:proj-)?[A-Za-z0-9_-]{12,}\b"),
    re.compile(r"\b(?:sk|pk)-lf-[A-Za-z0-9_-]{8,}\b"),
)


def _redact_secrets(value: Any) -> Any:
    """Redact credential-like strings recursively before logging or tracing."""
    if isinstance(value, dict):
        return {
            key: "[REDACTED]"
            if isinstance(key, str)
            and re.search(
                r"(?i)(?:api[_-]?key|token|auth(?:orization)?|secret|password)",
                key,
            )
            else _redact_secrets(item)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [_redact_secrets(item) for item in value]
    if isinstance(value, tuple):
        return tuple(_redact_secrets(item) for item in value)
    if isinstance(value, str):
        for pattern in _SECRET_PATTERNS:
            value = pattern.sub(
                lambda match: (match.group(1) if match.lastindex else "")
                + "[REDACTED]",
                value,
            )
        return value
    return value


def _safe_error(exc: Exception) -> Exception:
    """Create a trace-safe error without retaining the original exception chain."""
    try:
        return type(exc)(str(_redact_secrets(str(exc))))
    except Exception:
        return RuntimeError(str(_redact_secrets(str(exc))))


def _token_encoding(model: str) -> Any:
    try:
        return tiktoken.encoding_for_model(model)
    except KeyError:
        return tiktoken.get_encoding("cl100k_base")


def _serialize_tool_result(result: Any, encoding: Any, token_budget: int) -> tuple[str, int]:
    if token_budget <= 0:
        return "", 0
    serialized = json.dumps(result, ensure_ascii=False, default=str)
    tokens = encoding.encode(serialized)
    if len(tokens) <= token_budget:
        return serialized, len(tokens)

    # Reserve room for the JSON wrapper and truncation marker.
    preview_tokens = max(0, token_budget - 24)
    while preview_tokens >= 0:
        preview = encoding.decode(tokens[:preview_tokens])
        content = json.dumps(
            {"truncated": True, "preview": preview}, ensure_ascii=False
        )
        content_tokens = len(encoding.encode(content))
        if content_tokens <= token_budget:
            return content, content_tokens
        preview_tokens -= max(1, content_tokens - token_budget)
    return "", 0


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

    async def _request_completion(self, client: Any, **request: Any) -> Any:
        """Call OpenAI and record the request, response, latency, and usage."""
        from langfuse import get_client

        langfuse = get_client()
        started = perf_counter()
        with langfuse.start_as_current_observation(
            as_type="generation",
            name="openai-chat-completion",
            model=request["model"],
            input=_redact_secrets(
                {key: value for key, value in request.items() if key != "model"}
            ),
        ) as generation:
            try:
                response = await client.chat.completions.create(**request)
            except Exception as exc:
                safe_error = _safe_error(exc)
                generation.update(output={"error": str(safe_error)})
                raise safe_error from None
            latency_ms = (perf_counter() - started) * 1000
            message = response.choices[0].message
            output = {
                "content": _redact_secrets(message.content),
                "tool_calls": [
                    {
                        "id": call.id,
                        "name": call.function.name,
                        "arguments": _redact_secrets(call.function.arguments),
                    }
                    for call in (message.tool_calls or [])
                ],
            }
            update: dict[str, Any] = {
                "output": _redact_secrets(output),
                "metadata": {"latency_ms": latency_ms},
            }
            usage = getattr(response, "usage", None)
            if usage is not None:
                usage_details = {
                    key: value
                    for key, value in {
                        "input": getattr(usage, "prompt_tokens", None),
                        "output": getattr(usage, "completion_tokens", None),
                        "total": getattr(usage, "total_tokens", None),
                    }.items()
                    if value is not None
                }
                if usage_details:
                    update["usage_details"] = usage_details
            generation.update(**update)
        return response

    async def _invoke_tool(
        self,
        client: Any,
        name: str,
        arguments: Any,
    ) -> Any:
        """Invoke an MCP tool and record its name, arguments, and result."""
        from langfuse import get_client

        langfuse = get_client()
        with langfuse.start_as_current_observation(
            as_type="tool",
            name=f"mcp-tool:{name}",
            input=_redact_secrets({"arguments": arguments}),
        ) as observation:
            try:
                tool = self.tools.get(name)
                if tool is None:
                    raise ToolExecutionError(
                        f"OpenAI selected unknown MCP tool {name!r}."
                    )
                if isinstance(arguments, str):
                    try:
                        arguments = json.loads(arguments)
                    except (TypeError, json.JSONDecodeError) as exc:
                        raise ToolArgumentError(
                            f"Invalid JSON arguments for MCP tool {name!r}."
                        ) from exc
                result = await call_tool(client, tool, arguments)
            except (ToolArgumentError, ToolExecutionError) as exc:
                safe_error = _safe_error(exc)
                observation.update(output={"error": str(safe_error)})
                raise safe_error from None
            observation.update(output=_redact_secrets(result))
            return result

    async def _run_with_client(self, prompt: str, client: Any) -> str:
        if not self.tools:
            await self.connect()

        messages: list[dict[str, Any]] = [{"role": "user", "content": prompt}]
        encoding = _token_encoding(self.model)
        remaining_result_tokens = MAX_CONVERSATION_TOOL_RESULT_TOKENS
        async with connect_to_server(self.server_url) as mcp_client:
            for _ in range(self.max_tool_rounds):
                response = await self._request_completion(
                    client,
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
                        result = await self._invoke_tool(
                            mcp_client, name, item.function.arguments
                        )
                    except (ToolArgumentError, ToolExecutionError) as exc:
                        result = {"error": str(exc)}

                    result_content, used_tokens = _serialize_tool_result(
                        result,
                        encoding,
                        min(MAX_TOOL_RESULT_TOKENS, remaining_result_tokens),
                    )
                    remaining_result_tokens = max(0, remaining_result_tokens - used_tokens)
                    messages.append(
                        {
                            "role": "tool",
                            "tool_call_id": item.id,
                            "content": result_content,
                        }
                    )

            # Ask for a final answer after the configured number of tool rounds.
            response = await self._request_completion(
                client,
                model=self.model,
                messages=messages,
                tools=self.openai_tools,
                tool_choice="none",
            )
            return response.choices[0].message.content or ""

    async def run(self, prompt: str) -> str:
        """Answer a prompt, executing model-selected MCP tools as needed."""
        from langfuse import get_client

        langfuse = get_client()
        with langfuse.start_as_current_observation(
            as_type="span",
            name="agent-execution",
            input=_redact_secrets({"question": prompt}),
        ) as observation:
            try:
                if self.openai_client is not None:
                    answer = await self._run_with_client(prompt, self.openai_client)
                else:
                    async with AsyncOpenAI() as client:
                        answer = await self._run_with_client(prompt, client)
            except Exception as exc:
                safe_error = _safe_error(exc)
                observation.update(output={"error": str(safe_error)})
                raise safe_error from None
            observation.update(output=_redact_secrets({"answer": answer}))
            return answer


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
