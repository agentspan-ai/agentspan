# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""Tests for the async AgentHttpClient."""

from __future__ import annotations

import json

import httpx
import pytest

from agentspan.agents.runtime.http_client import (
    AgentHttpClient,
)

# ── Helpers ──────────────────────────────────────────────────────────────


def _make_client(handler, **auth) -> AgentHttpClient:
    """Create an AgentHttpClient backed by a mock transport.

    Anonymous by default — pass api_key/auth_key/auth_secret to exercise auth.
    """
    client = AgentHttpClient(server_url="http://test-server/api", **auth)
    # Override the lazy client with a mock-transport client. Auth headers are
    # attached per-request by _auth_headers(), not as client defaults.
    client._client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    return client


# ── Tests ────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_start_agent():
    """POST /agent/start returns executionId."""

    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "POST"
        assert request.url.path == "/api/agent/start"
        body = json.loads(request.content)
        assert body["prompt"] == "hello"
        return httpx.Response(200, json={"executionId": "wf-123"})

    client = _make_client(handler)
    result = await client.start_agent({"prompt": "hello"})
    assert result["executionId"] == "wf-123"
    await client.close()


@pytest.mark.asyncio
async def test_compile_agent():
    """POST /agent/compile returns agent def."""

    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/agent/compile"
        return httpx.Response(200, json={"workflowDef": {"name": "test_wf"}})

    client = _make_client(handler)
    result = await client.compile_agent({"name": "test"})
    assert result["workflowDef"]["name"] == "test_wf"
    await client.close()


@pytest.mark.asyncio
async def test_get_status():
    """GET /agent/{id}/status returns status dict."""

    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "GET"
        assert "/wf-123/status" in str(request.url)
        return httpx.Response(
            200,
            json={
                "status": "COMPLETED",
                "isComplete": True,
                "isRunning": False,
                "isWaiting": False,
                "output": "done",
            },
        )

    client = _make_client(handler)
    result = await client.get_status("wf-123")
    assert result["status"] == "COMPLETED"
    assert result["isComplete"] is True
    await client.close()


@pytest.mark.asyncio
async def test_respond():
    """POST /agent/{id}/respond succeeds."""
    called = {}

    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "POST"
        assert "/wf-123/respond" in str(request.url)
        called["body"] = json.loads(request.content)
        return httpx.Response(200, json={})

    client = _make_client(handler)
    await client.respond("wf-123", {"approved": True})
    assert called["body"] == {"approved": True}
    await client.close()


@pytest.mark.asyncio
async def test_http_error_raises():
    """Non-2xx responses raise AgentAPIError (wrapping httpx.HTTPStatusError)."""
    from agentspan.agents.exceptions import AgentAPIError

    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, text="Internal Server Error")

    client = _make_client(handler)
    with pytest.raises(AgentAPIError) as exc_info:
        await client.start_agent({"prompt": "test"})
    assert exc_info.value.status_code == 500
    await client.close()


@pytest.mark.asyncio
async def test_parse_sse_async():
    """SSE parsing handles events, heartbeats, and multi-line data."""

    async def lines():
        for line in [
            ": heartbeat",
            "event: thinking",
            'data: {"content": "processing"}',
            "",
            "event: done",
            "id: 42",
            'data: {"output": "result"}',
            "",
        ]:
            yield line

    events = []
    async for event in AgentHttpClient._parse_sse_async(lines()):
        events.append(event)

    assert events[0] == {"_heartbeat": True}
    assert events[1]["event"] == "thinking"
    assert events[1]["data"]["content"] == "processing"
    assert events[2]["event"] == "done"
    assert events[2]["id"] == "42"
    assert events[2]["data"]["output"] == "result"


@pytest.mark.asyncio
async def test_close_idempotent():
    """Closing twice doesn't error."""

    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={})

    client = _make_client(handler)
    await client.close()
    await client.close()  # should not raise


# ── Auth: X-Authorization via api_key or minted token (orkes hosts) ──────


@pytest.mark.asyncio
async def test_anonymous_sends_no_auth_header():
    """No api_key and no auth_key/secret → no X-Authorization header."""

    async def handler(request: httpx.Request) -> httpx.Response:
        assert "x-authorization" not in request.headers
        return httpx.Response(200, json={"executionId": "wf-1"})

    client = _make_client(handler)
    await client.start_agent({"prompt": "test"})
    await client.close()


@pytest.mark.asyncio
async def test_api_key_sends_x_authorization():
    """An explicit api_key is already a token — sent directly, no /token call."""

    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path != "/api/token", "api_key must not mint a token"
        assert request.headers.get("x-authorization") == "my-api-token"
        return httpx.Response(200, json={"executionId": "wf-1"})

    client = _make_client(handler, api_key="my-api-token")
    await client.start_agent({"prompt": "test"})
    await client.close()


@pytest.mark.asyncio
async def test_auth_key_mints_token_and_caches_it():
    """auth_key/auth_secret mint a JWT via POST /token, cached across requests."""
    token_calls = {"count": 0}

    async def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/token":
            token_calls["count"] += 1
            body = json.loads(request.content)
            assert body == {"keyId": "key1", "keySecret": "secret1"}
            return httpx.Response(200, json={"token": "minted-token"})
        assert request.headers.get("x-authorization") == "minted-token"
        return httpx.Response(200, json={"executionId": "wf-1"})

    client = _make_client(handler, auth_key="key1", auth_secret="secret1")
    await client.start_agent({"prompt": "one"})
    await client.start_agent({"prompt": "two"})
    # opaque token → exp unknown → cached until rejected; minted exactly once
    assert token_calls["count"] == 1
    await client.close()


@pytest.mark.asyncio
async def test_api_key_takes_precedence_over_auth_key():
    """When both api_key and auth_key are set, api_key wins and no token is minted."""

    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path != "/api/token", "api_key must not mint a token"
        assert request.headers.get("x-authorization") == "my-api-key"
        return httpx.Response(200, json={"executionId": "wf-1"})

    client = _make_client(
        handler,
        api_key="my-api-key",
        auth_key="my-auth-key",
        auth_secret="my-auth-secret",
    )
    await client.start_agent({"prompt": "test"})
    await client.close()


@pytest.mark.asyncio
async def test_token_mint_failure_degrades_to_anonymous():
    """A failing /token endpoint logs a warning and the request proceeds unauthenticated."""

    async def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/token":
            return httpx.Response(503, text="token service down")
        assert "x-authorization" not in request.headers
        return httpx.Response(200, json={"executionId": "wf-1"})

    client = _make_client(handler, auth_key="key1", auth_secret="secret1")
    result = await client.start_agent({"prompt": "test"})
    assert result["executionId"] == "wf-1"
    await client.close()
