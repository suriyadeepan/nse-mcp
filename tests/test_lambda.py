"""Lambda container HTTP/auth and role credential-chain integration coverage."""

from dataclasses import replace

import httpx
import httpx2
import pytest
from mcp import Client
from mcp.client.streamable_http import streamable_http_client
from mcp.server import MCPServer

from server import analytics, tools, validation
from server.auth import BearerAuthMiddleware
from server.tools import register_tools
from server.config import ANALYTICS_CONFIG


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.mark.anyio
async def test_lambda_http_requires_auth_and_executes_mcp_tool(monkeypatch):
    token = "lambda-test-token-with-at-least-32-characters"
    monkeypatch.setenv("MCP_BEARER_TOKEN", token)
    expected = {
        "bars": [
            {
                "timestamp": "2024-01-01T00:00:00Z",
                "open": 10.0,
                "high": 12.0,
                "low": 9.0,
                "close": 11.0,
                "volume": 100,
            }
        ],
        "returned_count": 1,
    }
    calls = []

    def get_bars(**arguments):
        calls.append(arguments)
        return expected

    monkeypatch.setattr(tools.analytics, "get_bars", get_bars)

    mcp_server = MCPServer("kite-mcp")
    register_tools(mcp_server)
    asgi_app = mcp_server.streamable_http_app(streamable_http_path="/mcp")
    lambda_app = BearerAuthMiddleware(asgi_app)
    async with asgi_app.router.lifespan_context(asgi_app):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=lambda_app), base_url="http://127.0.0.1:8000"
        ) as unauthenticated:
            response = await unauthenticated.get("/mcp")
        assert response.status_code == 401
        assert token not in response.text

        async with httpx2.AsyncClient(
            transport=httpx2.ASGITransport(app=lambda_app),
            base_url="http://127.0.0.1:8000",
            headers={"Authorization": f"Bearer {token}"},
        ) as authorized:
            transport = streamable_http_client(
                "http://127.0.0.1:8000/mcp", http_client=authorized
            )
            async with Client(transport) as client:
                assert client.server_info.name == "kite-mcp"
                listed = await client.list_tools()
                assert "get_bars" in {tool.name for tool in listed.tools}
                result = await client.call_tool(
                    "get_bars",
                    {
                        "arguments": {
                            "symbol": "AAA",
                            "start_datetime": "2024-01-01T00:00:00Z",
                            "end_datetime": "2024-01-02T00:00:00Z",
                            "limit": 10,
                        }
                    },
                )

    assert result.is_error is False
    assert result.structured_content == expected
    assert len(calls) == 1
    assert calls[0]["symbol"] == "AAA"


def test_lambda_s3_query_uses_execution_role_credential_chain(monkeypatch):
    import duckdb

    monkeypatch.delenv("AWS_ACCESS_KEY_ID", raising=False)
    monkeypatch.delenv("AWS_SECRET_ACCESS_KEY", raising=False)
    config = replace(
        ANALYTICS_CONFIG,
        processed_data_source="s3",
        processed_data_s3_bucket="unit-test-market-data",
        processed_data_s3_prefix="datasets/processed",
    )
    monkeypatch.setattr(analytics, "ANALYTICS_CONFIG", config)
    monkeypatch.setattr(validation, "ANALYTICS_CONFIG", config)
    monkeypatch.setattr(validation, "list_symbols", lambda *_args, **_kwargs: ["AAA"])

    class QueryResult:
        def to_arrow_table(self):
            return self

        def to_pylist(self):
            return []

    class FakeDuckDBConnection:
        def __init__(self):
            self.statements = []
            self.query = None
            self.params = None
            self.closed = False

        def execute(self, statement):
            self.statements.append(statement)

        def sql(self, query, params):
            self.query = query
            self.params = params
            return QueryResult()

        def close(self):
            self.closed = True

    fake_connection = FakeDuckDBConnection()
    monkeypatch.setattr(duckdb, "connect", lambda **_kwargs: fake_connection)

    result = analytics.get_bars(
        "AAA", "2024-01-01T00:00:00Z", "2024-01-02T00:00:00Z", 10
    )

    assert result == {"bars": [], "returned_count": 0}
    assert fake_connection.statements == [
        "INSTALL httpfs",
        "LOAD httpfs",
        "CREATE SECRET s3_dataset (TYPE S3, PROVIDER credential_chain)",
    ]
    assert fake_connection.params[0] == (
        "s3://unit-test-market-data/datasets/processed/**/*.parquet"
    )
    assert "WHERE symbol = ?" in fake_connection.query
    assert fake_connection.params[1] == "AAA"
    assert fake_connection.closed
