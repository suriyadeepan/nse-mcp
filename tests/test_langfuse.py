"""Tests for Langfuse client lifecycle setup."""

import sys
from types import ModuleType, SimpleNamespace

import pytest

from client import main as client_main


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
