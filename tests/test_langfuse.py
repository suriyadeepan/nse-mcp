"""Tests for Langfuse client lifecycle setup."""

import sys
import json
from contextlib import asynccontextmanager, contextmanager
from contextvars import ContextVar
from types import ModuleType, SimpleNamespace

import pytest

from client import main as client_main
from client import agent as client_agent
from client.agent import Agent


def test_initialize_langfuse_loads_dotenv_before_client(monkeypatch):
    calls = []
    dotenv = ModuleType("dotenv")
    dotenv.load_dotenv = lambda: calls.append("load_dotenv")
    langfuse = ModuleType("langfuse")
    langfuse.get_client = lambda: calls.append("get_client") or "client"
    monkeypatch.setitem(sys.modules, "dotenv", dotenv)
    monkeypatch.setitem(sys.modules, "langfuse", langfuse)

    assert client_main._initialize_langfuse() == "client"
    assert calls == ["load_dotenv", "get_client"]


def test_cli_flushes_langfuse_after_success(monkeypatch, capsys):
    flushed = []
    monkeypatch.setattr(sys, "argv", ["kite-mcp-client", "--prompt", "hello"])
    monkeypatch.setattr(
        client_main,
        "_initialize_langfuse",
        lambda: SimpleNamespace(flush=lambda: flushed.append(True)),
    )
    monkeypatch.setattr("client.agent.run", lambda *args, **kwargs: "answer")

    client_main.main()

    assert flushed == [True]
    assert capsys.readouterr().out == "answer\n"


def test_cli_flushes_langfuse_after_connection_error(monkeypatch):
    flushed = []
    monkeypatch.setattr(sys, "argv", ["kite-mcp-client", "--prompt", "hello"])
    monkeypatch.setattr(
        client_main,
        "_initialize_langfuse",
        lambda: SimpleNamespace(flush=lambda: flushed.append(True)),
    )

    def fail(*args, **kwargs):
        raise ConnectionError("server unavailable")

    monkeypatch.setattr("client.agent.run", fail)

    with pytest.raises(SystemExit, match="1"):
        client_main.main()

    assert flushed == [True]


@pytest.mark.anyio
async def test_agent_trace_records_question_and_final_answer(monkeypatch):
    observations = []

    class FakeLangfuse:
        @contextmanager
        def start_as_current_observation(self, **kwargs):
            observation = SimpleNamespace(update=lambda **values: observations.append(values))
            observations.append(kwargs)
            yield observation

    langfuse = ModuleType("langfuse")
    langfuse.get_client = lambda: FakeLangfuse()
    monkeypatch.setitem(sys.modules, "langfuse", langfuse)

    async def answer(prompt, client):
        return "The answer is 42."

    agent = Agent(openai_client=object())
    monkeypatch.setattr(agent, "_run_with_client", answer)

    result = await agent.run("What is the answer?")

    assert result == "The answer is 42."
    assert observations == [
        {
            "as_type": "span",
            "name": "agent-execution",
            "input": {"question": "What is the answer?"},
        },
        {"output": {"answer": "The answer is 42."}},
    ]


@pytest.mark.anyio
async def test_openai_generation_records_request_response_latency_and_usage(monkeypatch):
    observations = []

    class FakeLangfuse:
        @contextmanager
        def start_as_current_observation(self, **kwargs):
            observation = dict(kwargs)
            observations.append(observation)
            yield SimpleNamespace(update=lambda **values: observation.update(values))

    langfuse = ModuleType("langfuse")
    langfuse.get_client = lambda: FakeLangfuse()
    monkeypatch.setitem(sys.modules, "langfuse", langfuse)
    response = SimpleNamespace(
        choices=[
            SimpleNamespace(
                message=SimpleNamespace(content="answer", tool_calls=[])
            )
        ],
        usage=SimpleNamespace(prompt_tokens=12, completion_tokens=4, total_tokens=16),
    )

    class FakeOpenAI:
        chat = SimpleNamespace(completions=SimpleNamespace(create=None))

    async def create(**kwargs):
        return response

    client = FakeOpenAI()
    client.chat.completions.create = create
    request = {"model": "test-model", "messages": [{"role": "user", "content": "hi"}]}

    result = await Agent()._request_completion(client, **request)

    assert result is response
    assert observations[0]["as_type"] == "generation"
    assert observations[0]["model"] == "test-model"
    assert observations[0]["input"] == {"messages": request["messages"]}
    assert observations[0]["output"] == {"content": "answer", "tool_calls": []}
    assert observations[0]["metadata"]["latency_ms"] >= 0
    assert observations[0]["usage_details"] == {
        "input": 12,
        "output": 4,
        "total": 16,
    }


@pytest.mark.anyio
async def test_mcp_tool_observation_records_name_arguments_and_result(monkeypatch):
    observations = []

    class FakeLangfuse:
        @contextmanager
        def start_as_current_observation(self, **kwargs):
            observation = dict(kwargs)
            observations.append(observation)
            yield SimpleNamespace(update=lambda **values: observation.update(values))

    langfuse = ModuleType("langfuse")
    langfuse.get_client = lambda: FakeLangfuse()
    monkeypatch.setitem(sys.modules, "langfuse", langfuse)
    tool = object()

    async def call_tool(client, discovered_tool, arguments):
        assert discovered_tool is tool
        assert arguments == {"symbol": "AAPL"}
        return {"price": 190.0}

    monkeypatch.setattr(client_agent, "call_tool", call_tool)
    agent = Agent()
    agent.tools = {"lookup_price": tool}

    result = await agent._invoke_tool(
        object(), "lookup_price", '{"symbol":"AAPL"}'
    )

    assert result == {"price": 190.0}
    assert observations == [
        {
            "as_type": "tool",
            "name": "mcp-tool:lookup_price",
            "input": {"arguments": '{"symbol":"AAPL"}'},
            "output": {"price": 190.0},
        }
    ]


@pytest.mark.anyio
async def test_model_and_tool_observations_are_children_of_agent_trace(monkeypatch):
    active_observation = ContextVar("active_observation", default=None)
    observations = []

    class FakeLangfuse:
        @contextmanager
        def start_as_current_observation(self, **kwargs):
            observation_id = len(observations)
            observation = {
                "id": observation_id,
                "parent_id": active_observation.get(),
                **kwargs,
            }
            observations.append(observation)
            token = active_observation.set(observation_id)
            try:
                yield SimpleNamespace(update=lambda **values: observation.update(values))
            finally:
                active_observation.reset(token)

    langfuse = ModuleType("langfuse")
    langfuse.get_client = lambda: FakeLangfuse()
    monkeypatch.setitem(sys.modules, "langfuse", langfuse)

    tool_call = SimpleNamespace(
        id="call-1",
        function=SimpleNamespace(name="lookup", arguments='{"symbol":"ABC"}'),
    )
    responses = iter(
        [
            SimpleNamespace(
                choices=[
                    SimpleNamespace(
                        message=SimpleNamespace(content=None, tool_calls=[tool_call])
                    )
                ],
                usage=None,
            ),
            SimpleNamespace(
                choices=[
                    SimpleNamespace(
                        message=SimpleNamespace(content="Done", tool_calls=[])
                    )
                ],
                usage=None,
            ),
        ]
    )

    class FakeOpenAI:
        chat = SimpleNamespace(completions=SimpleNamespace(create=None))

    async def create(**kwargs):
        return next(responses)

    openai_client = FakeOpenAI()
    openai_client.chat.completions.create = create

    @asynccontextmanager
    async def connect_to_server(_server_url):
        yield object()

    async def call_tool(_client, _tool, arguments):
        assert arguments == {"symbol": "ABC"}
        return {"matches": 1}

    monkeypatch.setattr(client_agent, "connect_to_server", connect_to_server)
    monkeypatch.setattr(client_agent, "call_tool", call_tool)
    monkeypatch.setattr(client_agent, "_token_encoding", lambda _model: object())
    monkeypatch.setattr(
        client_agent,
        "_serialize_tool_result",
        lambda result, _encoding, _budget: (json.dumps(result), 2),
    )
    agent = Agent(openai_client=openai_client)
    agent.tools = {"lookup": object()}

    assert await agent.run("Find ABC") == "Done"

    root = observations[0]
    assert root["name"] == "agent-execution"
    child_observations = observations[1:]
    assert [item["name"] for item in child_observations] == [
        "openai-chat-completion",
        "mcp-tool:lookup",
        "openai-chat-completion",
    ]
    assert all(item["parent_id"] == root["id"] for item in child_observations)
