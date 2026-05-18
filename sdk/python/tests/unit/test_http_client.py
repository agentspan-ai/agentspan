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


def _make_client(handler) -> AgentHttpClient:
    """Create an AgentHttpClient backed by a mock transport."""
    client = AgentHttpClient(
        server_url="http://test-server/api",
        auth_key="key1",
        auth_secret="secret1",
    )
    # Override the lazy client with a mock-transport client that includes base headers
    client._client = httpx.AsyncClient(
        transport=httpx.MockTransport(handler),
        headers=client._base_headers(),
    )
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
async def test_auth_headers():
    """Auth headers are sent with every request."""

    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers.get("x-auth-key") == "key1"
        assert request.headers.get("x-auth-secret") == "secret1"
        return httpx.Response(200, json={"executionId": "wf-1"})

    client = _make_client(handler)
    await client.start_agent({"prompt": "test"})
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


# ── api_key Bearer auth (fix #4) ─────────────────────────────────────


def _make_client_with_api_key(handler) -> AgentHttpClient:
    """Create an AgentHttpClient with api_key (Bearer auth)."""
    client = AgentHttpClient(
        server_url="http://test-server/api",
        api_key="my-bearer-token",
    )
    client._client = httpx.AsyncClient(
        transport=httpx.MockTransport(handler),
        headers=client._base_headers(),
    )
    return client


@pytest.mark.asyncio
async def test_api_key_sends_bearer_auth():
    """api_key should produce Authorization: Bearer header."""

    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers.get("authorization") == "Bearer my-bearer-token"
        # Should NOT have X-Auth-Key when api_key is used
        assert "x-auth-key" not in request.headers
        return httpx.Response(200, json={"executionId": "wf-1"})

    client = _make_client_with_api_key(handler)
    await client.start_agent({"prompt": "test"})
    await client.close()


@pytest.mark.asyncio
async def test_api_key_takes_precedence_over_auth_key():
    """When both api_key and auth_key are set, api_key (Bearer) wins."""

    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers.get("authorization") == "Bearer my-api-key"
        assert "x-auth-key" not in request.headers
        return httpx.Response(200, json={"executionId": "wf-1"})

    client = AgentHttpClient(
        server_url="http://test-server/api",
        api_key="my-api-key",
        auth_key="my-auth-key",
        auth_secret="my-auth-secret",
    )
    client._client = httpx.AsyncClient(
        transport=httpx.MockTransport(handler),
        headers=client._base_headers(),
    )
    await client.start_agent({"prompt": "test"})
    await client.close()


@pytest.mark.asyncio
async def test_legacy_auth_key_still_works():
    """When api_key is empty, auth_key/auth_secret headers are sent."""

    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers.get("x-auth-key") == "legacy-key"
        assert request.headers.get("x-auth-secret") == "legacy-secret"
        assert "authorization" not in request.headers
        return httpx.Response(200, json={"executionId": "wf-1"})

    client = AgentHttpClient(
        server_url="http://test-server/api",
        api_key="",
        auth_key="legacy-key",
        auth_secret="legacy-secret",
    )
    client._client = httpx.AsyncClient(
        transport=httpx.MockTransport(handler),
        headers=client._base_headers(),
    )
    await client.start_agent({"prompt": "test"})
    await client.close()
