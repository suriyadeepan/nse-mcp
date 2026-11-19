"""Bearer authentication tests for the ASGI MCP app."""

import httpx
import pytest

from server.main import app


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.mark.anyio
async def test_http_rejects_requests_when_token_is_not_configured(monkeypatch):
    monkeypatch.delenv("MCP_BEARER_TOKEN", raising=False)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/mcp")

    assert response.status_code == 503
    assert response.json() == {"detail": "Authentication is not configured"}


@pytest.mark.anyio
@pytest.mark.parametrize(
    "authorization",
    [None, "Basic dXNlcjpwYXNz", "Bearer wrong-value", "Bearer expected-value extra"],
)
async def test_http_rejects_missing_malformed_or_incorrect_bearer_token(
    monkeypatch, authorization
):
    monkeypatch.setenv("MCP_BEARER_TOKEN", "expected-value")
    headers = {} if authorization is None else {"Authorization": authorization}
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/mcp", headers=headers)

    assert response.status_code == 401
    assert response.json() == {"detail": "Unauthorized"}
    assert "expected-value" not in response.text
    assert response.headers["www-authenticate"] == "Bearer"


@pytest.mark.anyio
async def test_http_accepts_correct_bearer_token(monkeypatch):
    monkeypatch.setenv("MCP_BEARER_TOKEN", "expected-value")
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get(
            "/not-an-mcp-route", headers={"Authorization": "Bearer expected-value"}
        )

    assert response.status_code == 404
