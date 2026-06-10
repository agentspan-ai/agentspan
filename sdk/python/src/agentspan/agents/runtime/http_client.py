# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""Async HTTP client for the Agent Runtime API.

Centralizes all ``httpx`` usage for the 5 agent API endpoints:
- POST /agent/start
- POST /agent/compile
- GET  /agent/{id}/status
- POST /agent/{id}/respond
- GET  /agent/stream/{id} (SSE)
"""

from __future__ import annotations

import json
import logging
import time
from typing import Any, AsyncIterator, Dict, List, Optional

import httpx

from agentspan.agents._internal.token_utils import decode_jwt_exp
from agentspan.agents.exceptions import _raise_api_error

logger = logging.getLogger("agentspan.agents.runtime.http_client")

_SSE_NO_EVENT_TIMEOUT = 15  # seconds to wait for first real event before fallback


class SSEUnavailableError(Exception):
    """Raised when the server doesn't support SSE streaming."""


class AgentHttpClient:
    """Async HTTP client for the Agent Runtime API."""

    def __init__(
        self,
        server_url: str,
        api_key: str = "",
        auth_key: str = "",
        auth_secret: str = "",
    ) -> None:
        self._server_url = server_url.rstrip("/")
        self._api_key = api_key
        self._auth_key = auth_key
        self._auth_secret = auth_secret
        self._client: Optional[httpx.AsyncClient] = None
        self._token: str = ""
        self._token_exp: float = 0.0

    async def _auth_headers(self) -> Dict[str, str]:
        """``X-Authorization`` header for secured hosts (orkes); {} when anonymous.

        An explicit api_key is already a token. Otherwise a JWT is minted from
        auth_key/auth_secret via ``POST {server}/token`` and cached until ~expiry.
        """
        if self._api_key:
            return {"X-Authorization": self._api_key}
        if not self._auth_key or not self._auth_secret:
            return {}

        if self._token and (self._token_exp == 0.0 or time.time() < self._token_exp - 30):
            return {"X-Authorization": self._token}

        try:
            client = await self._get_client()
            resp = await client.post(
                f"{self._server_url}/token",
                json={"keyId": self._auth_key, "keySecret": self._auth_secret},
            )
            resp.raise_for_status()
            token = resp.json().get("token") or ""
        except Exception as e:  # pragma: no cover - network/credential failures
            logger.warning("Failed to mint agent API token: %s", e)
            return {}
        if not token:
            return {}
        self._token = token
        self._token_exp = decode_jwt_exp(token)
        return {"X-Authorization": token}

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(timeout=httpx.Timeout(30.0, connect=5.0))
        return self._client

    def _url(self, path: str) -> str:
        return f"{self._server_url}/agent{path}"

    # ── Agent API endpoints ──────────────────────────────────────────

    async def start_agent(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """POST /agent/start — start an agent execution."""
        client = await self._get_client()
        url = self._url("/start")
        resp = await client.post(url, json=payload, headers=await self._auth_headers())
        try:
            resp.raise_for_status()
        except httpx.HTTPStatusError as exc:
            _raise_api_error(exc, url=url)
        return resp.json()

    async def deploy_agent(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """POST /agent/deploy — deploy agent (compile + register, no execution)."""
        client = await self._get_client()
        url = self._url("/deploy")
        resp = await client.post(url, json=payload, headers=await self._auth_headers())
        try:
            resp.raise_for_status()
        except httpx.HTTPStatusError as exc:
            _raise_api_error(exc, url=url)
        return resp.json()

    async def compile_agent(self, config_json: Dict[str, Any]) -> Dict[str, Any]:
        """POST /agent/compile — compile agent config to agent def."""
        client = await self._get_client()
        url = self._url("/compile")
        resp = await client.post(url, json=config_json, headers=await self._auth_headers())
        try:
            resp.raise_for_status()
        except httpx.HTTPStatusError as exc:
            _raise_api_error(exc, url=url)
        return resp.json()

    async def get_status(self, execution_id: str) -> Dict[str, Any]:
        """GET /agent/{id}/status — fetch execution status."""
        client = await self._get_client()
        url = self._url(f"/{execution_id}/status")
        resp = await client.get(url, headers=await self._auth_headers())
        try:
            resp.raise_for_status()
        except httpx.HTTPStatusError as exc:
            _raise_api_error(exc, url=url)
        return resp.json()

    async def respond(self, execution_id: str, body: Dict[str, Any]) -> None:
        """POST /agent/{id}/respond — complete a pending human task."""
        client = await self._get_client()
        url = self._url(f"/{execution_id}/respond")
        resp = await client.post(url, json=body, headers=await self._auth_headers())
        try:
            resp.raise_for_status()
        except httpx.HTTPStatusError as exc:
            _raise_api_error(exc, url=url)

    async def stop(self, execution_id: str) -> None:
        """POST /agent/{id}/stop — graceful deterministic stop."""
        client = await self._get_client()
        url = self._url(f"/{execution_id}/stop")
        resp = await client.post(url, headers=await self._auth_headers())
        try:
            resp.raise_for_status()
        except httpx.HTTPStatusError as exc:
            _raise_api_error(exc, url=url)

    async def signal(self, execution_id: str, message: str) -> None:
        """POST /agent/{id}/signal — inject persistent context."""
        client = await self._get_client()
        url = self._url(f"/{execution_id}/signal")
        resp = await client.post(url, json={"message": message}, headers=await self._auth_headers())
        try:
            resp.raise_for_status()
        except httpx.HTTPStatusError as exc:
            _raise_api_error(exc, url=url)

    async def stream_sse(self, execution_id: str) -> AsyncIterator[Dict[str, Any]]:
        """GET /agent/stream/{id} — consume SSE events.

        Yields parsed event dicts. Auto-reconnects with ``Last-Event-ID``
        on connection drops. Raises :class:`SSEUnavailableError` if the
        server doesn't support SSE or sends only heartbeats.
        """
        url = f"{self._server_url}/agent/stream/{execution_id}"
        headers = {**(await self._auth_headers()), "Accept": "text/event-stream"}

        last_event_id: Optional[str] = None
        first_connect = True
        got_real_event = False

        while True:
            try:
                req_headers = dict(headers)
                if last_event_id is not None:
                    req_headers["Last-Event-ID"] = last_event_id

                client = await self._get_client()
                async with client.stream(
                    "GET",
                    url,
                    headers=req_headers,
                    timeout=httpx.Timeout(30.0, connect=5.0),
                ) as resp:
                    if resp.status_code != 200:
                        if first_connect:
                            raise SSEUnavailableError(f"Server returned {resp.status_code}")
                        logger.warning(
                            "SSE reconnect failed (status=%s), stopping stream",
                            resp.status_code,
                        )
                        return

                    first_connect = False
                    connect_time = time.monotonic()

                    async for sse_event in self._parse_sse_async(resp.aiter_lines()):
                        if sse_event.get("_heartbeat"):
                            if (
                                not got_real_event
                                and time.monotonic() - connect_time > _SSE_NO_EVENT_TIMEOUT
                            ):
                                raise SSEUnavailableError(
                                    "SSE connected but no events received "
                                    f"(only heartbeats for {_SSE_NO_EVENT_TIMEOUT}s)"
                                )
                            continue

                        if sse_event.get("id"):
                            last_event_id = sse_event["id"]

                        got_real_event = True
                        yield sse_event

                # Stream ended cleanly
                return

            except SSEUnavailableError:
                raise
            except Exception as e:
                if first_connect:
                    raise SSEUnavailableError(str(e))
                logger.warning("SSE connection lost (%s), reconnecting in 1s...", e)
                import asyncio

                await asyncio.sleep(1)

    @staticmethod
    async def _parse_sse_async(
        lines: AsyncIterator[str],
    ) -> AsyncIterator[Dict[str, Any]]:
        """Parse SSE wire format into event dicts (async version).

        Comment lines (heartbeats) yield ``{"_heartbeat": True}``.
        """
        event_type: Optional[str] = None
        event_id: Optional[str] = None
        data_lines: List[str] = []

        async for raw_line in lines:
            line = raw_line.decode("utf-8") if isinstance(raw_line, bytes) else raw_line

            if line.startswith(":"):
                yield {"_heartbeat": True}
                continue
            if line == "":
                if data_lines:
                    data_str = "\n".join(data_lines)
                    try:
                        data = json.loads(data_str)
                    except (json.JSONDecodeError, ValueError):
                        data = {"content": data_str}
                    yield {
                        "event": event_type,
                        "id": event_id,
                        "data": data,
                    }
                event_type = None
                event_id = None
                data_lines = []
                continue

            if line.startswith("event:"):
                event_type = line[6:].strip()
            elif line.startswith("id:"):
                event_id = line[3:].strip()
            elif line.startswith("data:"):
                data_lines.append(line[5:].strip())

    # ── Lifecycle ────────────────────────────────────────────────────

    async def close(self) -> None:
        """Close the underlying httpx client."""
        if self._client is not None and not self._client.is_closed:
            await self._client.aclose()
            self._client = None
