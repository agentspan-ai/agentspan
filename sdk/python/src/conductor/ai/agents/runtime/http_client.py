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

import asyncio
import json
import logging
import time
from typing import Any, AsyncIterator, Dict, List, Optional, Union

import httpx

from conductor.ai.agents._internal.token_utils import decode_jwt_exp
from conductor.ai.agents.exceptions import _raise_api_error

logger = logging.getLogger("conductor.ai.agents.runtime.http_client")

_SSE_NO_EVENT_TIMEOUT = 15  # seconds to wait for first real event before fallback


class SSEUnavailableError(Exception):
    """Raised when the server doesn't support SSE streaming."""


class AgentClient:
    """Async HTTP client for the Agent Runtime API.

    This is the ``/agent/*`` control-plane client (compile / deploy / start /
    status / respond / stream). On top of those raw endpoints it gains
    agent-level convenience methods — :meth:`run`, :meth:`start`,
    :meth:`deploy`, :meth:`schedule` — and a :attr:`schedules` accessor for the
    cron schedule lifecycle.

    **Run is control-plane only.** :meth:`run` compiles + starts the agent and
    polls to a result; it does **not** register or poll local tool workers.
    Agents that use local ``@tool`` functions must run through
    :class:`AgentRuntime`, which owns worker orchestration. For LLM-only
    agents, remote tools (HTTP/MCP), or pre-deployed workflows, this client is
    sufficient.

    Two construction modes:

    - **Bound to a runtime** (``AgentClient(runtime=rt)``): reuses the
      runtime's Conductor clients, schedule client, and result helpers so
      there is a single shared schedule surface and no duplicated state.
    - **Standalone** (``AgentClient(server_url=..., ...)``): builds its own
      Conductor clients lazily for the schedule lifecycle and status/token
      lookups.
    """

    def __init__(
        self,
        server_url: str = "",
        api_key: str = "",
        auth_key: str = "",
        auth_secret: str = "",
        *,
        runtime: Any = None,
    ) -> None:
        # When bound to a runtime, inherit its connection settings so the two
        # share a single schedule/result surface (no duplicated state).
        self._runtime = runtime
        if runtime is not None:
            cfg = runtime._config
            server_url = server_url or cfg.server_url
            api_key = api_key or (cfg.api_key or "")
            auth_key = auth_key or (cfg.auth_key or "")
            auth_secret = auth_secret or (cfg.auth_secret or "")

        self._server_url = server_url.rstrip("/")
        self._api_key = api_key
        self._auth_key = auth_key
        self._auth_secret = auth_secret
        self._client: Optional[httpx.AsyncClient] = None
        self._token: str = ""
        self._token_exp: float = 0.0

        # Lazily-built Conductor clients + schedule client for standalone use.
        self._orkes_clients: Any = None
        self._workflow_client_instance: Any = None
        self._schedule_client_instance: Any = None

    async def _auth_headers(self) -> Dict[str, str]:
        """``X-Authorization`` header for secured hosts (orkes); {} when anonymous.

        An explicit api_key is already a token. Otherwise a JWT is minted from
        auth_key/auth_secret via ``POST {server}/token`` and cached until ~expiry.
        """
        if self._api_key:
            return {"X-Authorization": self._api_key}
        if not self._auth_key or not self._auth_secret:
            return {}

        # Reuse the cached token only if it has a decodable expiry and isn't near
        # it. A token with no decodable exp (_token_exp == 0.0) is NOT cached —
        # re-mint it (matches the C# SDK; avoids serving a stale token forever).
        if self._token and self._token_exp != 0.0 and time.time() < self._token_exp - 30:
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

    # ── Conductor clients (lazy; reused from runtime when bound) ─────

    def _get_orkes_clients(self) -> Any:
        """Build (or reuse the runtime's) ``OrkesClients`` for schedule/status."""
        if self._runtime is not None:
            return self._runtime._clients
        if self._orkes_clients is None:
            from dataclasses import replace

            from conductor.ai.agents.runtime.config import AgentConfig
            from conductor.client.orkes_clients import OrkesClients

            cfg = replace(
                AgentConfig.from_env(),
                server_url=self._server_url,
                api_key=self._api_key or None,
                auth_key=self._auth_key or None,
                auth_secret=self._auth_secret or None,
            )
            self._orkes_clients = OrkesClients(configuration=cfg.to_conductor_configuration())
        return self._orkes_clients

    @property
    def _workflow_client(self) -> Any:
        """Conductor workflow client (reused from runtime when bound)."""
        if self._runtime is not None:
            return self._runtime._workflow_client
        if self._workflow_client_instance is None:
            self._workflow_client_instance = self._get_orkes_clients().get_workflow_client()
        return self._workflow_client_instance

    @property
    def schedules(self) -> Any:
        """Cron schedule lifecycle client (:class:`ScheduleClient`).

        Exposes ``save/get/list_for_agent/pause/resume/delete/run_now/
        preview_next/reconcile``. When bound to a runtime, this is the
        *same* :class:`ScheduleClient` instance the runtime uses — there is
        one shared schedule surface, not two.
        """
        if self._runtime is not None:
            return self._runtime.schedules_client()
        if self._schedule_client_instance is None:
            from conductor.ai.agents.schedule.client import ScheduleClient

            self._schedule_client_instance = ScheduleClient(
                self._get_orkes_clients().get_scheduler_client(),
                self._workflow_client,
            )
        return self._schedule_client_instance

    # ── Agent-level convenience (control-plane only — NO local workers) ──

    async def run_async(
        self,
        agent: Any,
        prompt: "Union[str, Any]" = None,
        *,
        media: Optional[List[str]] = None,
        session_id: Optional[str] = None,
        idempotency_key: Optional[str] = None,
        timeout: Optional[int] = None,
        context: Optional[Dict[str, Any]] = None,
        static_plan: Optional[Dict[str, Any]] = None,
    ) -> Any:
        """Compile + start an agent, then poll to an :class:`AgentResult`.

        **Control-plane only** — does NOT register or poll local tool workers.
        Use :meth:`AgentRuntime.run` for agents with local ``@tool`` functions.
        Suitable for LLM-only agents, remote tools (HTTP/MCP), and pre-deployed
        agents.
        """
        handle = await self.start_async(
            agent,
            prompt,
            media=media,
            session_id=session_id,
            idempotency_key=idempotency_key,
            timeout=timeout,
            context=context,
            static_plan=static_plan,
        )
        return await handle.join_async(timeout=timeout)

    def run(
        self,
        agent: Any,
        prompt: "Union[str, Any]" = None,
        *,
        media: Optional[List[str]] = None,
        session_id: Optional[str] = None,
        idempotency_key: Optional[str] = None,
        timeout: Optional[int] = None,
        context: Optional[Dict[str, Any]] = None,
        static_plan: Optional[Dict[str, Any]] = None,
    ) -> Any:
        """Synchronous :meth:`run_async`."""
        return _run_sync(
            self.run_async(
                agent,
                prompt,
                media=media,
                session_id=session_id,
                idempotency_key=idempotency_key,
                timeout=timeout,
                context=context,
                static_plan=static_plan,
            )
        )

    async def start_async(
        self,
        agent: Any,
        prompt: "Union[str, Any]" = None,
        *,
        media: Optional[List[str]] = None,
        session_id: Optional[str] = None,
        idempotency_key: Optional[str] = None,
        timeout: Optional[int] = None,
        context: Optional[Dict[str, Any]] = None,
        static_plan: Optional[Dict[str, Any]] = None,
    ) -> Any:
        """Compile + start an agent; return an :class:`AgentHandle`. No workers."""
        from conductor.ai.agents.config_serializer import AgentConfigSerializer
        from conductor.ai.agents.result import AgentHandle

        prompt_str = prompt if isinstance(prompt, str) else (prompt or "")
        config_json = AgentConfigSerializer().serialize(agent)
        payload: Dict[str, Any] = {
            "agentConfig": config_json,
            "prompt": prompt_str,
            "sessionId": session_id or "",
            "media": media or [],
        }
        if context:
            payload["context"] = context
        if idempotency_key:
            payload["idempotencyKey"] = idempotency_key
        if timeout is not None:
            payload["timeoutSeconds"] = timeout
        if static_plan is not None:
            payload["static_plan"] = static_plan

        data = await self.start_agent(payload)
        execution_id = data.get("executionId", "")
        logger.info(
            "Started agent '%s' via control-plane (execution_id=%s)", agent.name, execution_id
        )
        # Wrap in an AgentHandle backed by this client via a runtime-shaped
        # adapter (no AgentRuntime, no local workers).
        return AgentHandle(execution_id, _ClientRuntimeAdapter(self))

    def start(
        self,
        agent: Any,
        prompt: "Union[str, Any]" = None,
        *,
        media: Optional[List[str]] = None,
        session_id: Optional[str] = None,
        idempotency_key: Optional[str] = None,
        timeout: Optional[int] = None,
        context: Optional[Dict[str, Any]] = None,
        static_plan: Optional[Dict[str, Any]] = None,
    ) -> Any:
        """Synchronous :meth:`start_async`."""
        return _run_sync(
            self.start_async(
                agent,
                prompt,
                media=media,
                session_id=session_id,
                idempotency_key=idempotency_key,
                timeout=timeout,
                context=context,
                static_plan=static_plan,
            )
        )

    async def deploy_async(self, *agents: Any) -> List[Any]:
        """Compile + register one or more agents (no execution, no workers)."""
        from conductor.ai.agents.config_serializer import AgentConfigSerializer
        from conductor.ai.agents.frameworks.serializer import detect_framework, serialize_agent
        from conductor.ai.agents.result import DeploymentInfo

        if not agents:
            raise ValueError("deploy() requires at least one agent.")

        results: List[Any] = []
        for agent in agents:
            framework = detect_framework(agent)
            if framework:
                raw_config, _ = serialize_agent(agent)
                payload = {"framework": framework, "rawConfig": raw_config}
            else:
                payload = {"agentConfig": AgentConfigSerializer().serialize(agent)}
            data = await self.deploy_agent(payload)
            registered_name = data.get("agentName", "") or getattr(agent, "name", "")
            agent_name = getattr(agent, "name", registered_name)
            results.append(DeploymentInfo(registered_name=registered_name, agent_name=agent_name))
            logger.info("Deployed agent '%s' as '%s'", agent_name, registered_name)
        return results

    def deploy(self, *agents: Any) -> List[Any]:
        """Synchronous :meth:`deploy_async`."""
        return _run_sync(self.deploy_async(*agents))

    def schedule(self, agent: Any, schedules: Optional[List[Any]]) -> Any:
        """Deploy *agent* and reconcile its cron *schedules* declaratively.

        Upserts the listed schedules and prunes any others for the agent.
        Pass ``[]`` to purge all schedules; ``None`` to leave them untouched.
        Returns the :class:`DeploymentInfo` for the deployed agent.
        """
        info = self.deploy(agent)[0]
        self.schedules.reconcile(agent.name, schedules)
        return info

    # ── Runtime-compatible surface for AgentHandle (poll / build result) ──
    #
    # AgentHandle is normally backed by an AgentRuntime; a client-backed
    # handle (from start()/run()) needs the same sync+async methods AgentHandle
    # calls on its ``_runtime``. We expose them here. The raw async endpoint
    # methods above (``get_status``/``respond``/``stop``) take an execution id
    # and the same names are used by the runtime-compat surface below — the
    # sync variants are the *_sync helpers, the async variants reuse them.

    def _status(self, execution_id: str, data: Dict[str, Any]) -> Any:
        from conductor.ai.agents.result import AgentStatus

        return AgentStatus(
            execution_id=execution_id,
            is_complete=data.get("isComplete", False),
            is_running=data.get("isRunning", False),
            is_waiting=data.get("isWaiting", False),
            output=data.get("output"),
            status=data.get("status", "UNKNOWN"),
            reason=data.get("reasonForIncompletion"),
            pending_tool=data.get("pendingTool"),
        )

    async def get_status_async(self, execution_id: str) -> Any:
        """Fetch current status as an :class:`AgentStatus` (async)."""
        return self._status(execution_id, await self.get_status(execution_id))

    def get_status_sync(self, execution_id: str) -> Any:
        """Fetch current status as an :class:`AgentStatus` (sync)."""
        return _run_sync(self.get_status_async(execution_id))

    async def respond_async(self, execution_id: str, output: Any) -> None:
        """Complete a pending human task (async)."""
        body = output if isinstance(output, dict) else {"output": output}
        await self.respond(execution_id, body)

    async def stop_async(self, execution_id: str) -> None:
        """Gracefully stop an execution (async)."""
        await self.stop(execution_id)

    def _extract_token_usage(self, execution_id: str) -> Any:
        """Fetch aggregated token usage from the full execution tree."""
        from conductor.ai.agents.result import TokenUsage

        if not execution_id:
            return None
        prompt, completion, total, found = self._collect_tokens_by_id(execution_id, set())
        if not found:
            return None
        if total == 0 and (prompt > 0 or completion > 0):
            total = prompt + completion
        return TokenUsage(prompt_tokens=prompt, completion_tokens=completion, total_tokens=total)

    def _collect_tokens_by_id(self, execution_id: str, visited: set) -> tuple:
        """Recursively collect token counts via GET /api/agent/execution/{id}."""
        import requests

        if execution_id in visited:
            return 0, 0, 0, False
        visited.add(execution_id)

        try:
            url = f"{self._server_url}/agent/execution/{execution_id}"
            resp = requests.get(url, headers=self._sync_headers(), timeout=10)
            resp.raise_for_status()
            data = resp.json()
        except Exception:
            return 0, 0, 0, False

        total_prompt = total_completion = total_total = 0
        found_any = False
        token_usage = data.get("tokenUsage")
        if token_usage:
            p = int(token_usage.get("promptTokens", 0))
            c = int(token_usage.get("completionTokens", 0))
            t = int(token_usage.get("totalTokens", 0))
            if p or c or t:
                found_any = True
                total_prompt, total_completion, total_total = p, c, t
        for task in data.get("tasks", []):
            if "SUB_WORKFLOW" in str(task.get("taskType", "")).upper():
                sub_id = task.get("subWorkflowId")
                if sub_id and sub_id not in visited:
                    p, c, t, f = self._collect_tokens_by_id(sub_id, visited)
                    if f:
                        found_any = True
                        total_prompt += p
                        total_completion += c
                        total_total += t
        return total_prompt, total_completion, total_total, found_any

    def _sync_headers(self) -> Dict[str, str]:
        """Build X-Authorization headers for synchronous ``requests`` calls."""
        from conductor.ai.agents._internal.token_utils import resolve_agent_api_token

        token = resolve_agent_api_token(
            self._server_url,
            api_key=self._api_key or None,
            auth_key=self._auth_key or None,
            auth_secret=self._auth_secret or None,
        )
        return {"X-Authorization": token} if token else {}

    @staticmethod
    def _normalize_output(
        output: Any, raw_status: str, reason: Optional[str] = None
    ) -> Dict[str, Any]:
        """Normalize execution output to always be a dict.

        Delegates to :meth:`AgentRuntime._normalize_output` so the contract
        stays identical across the worker-managed and control-plane paths.
        """
        from conductor.ai.agents.runtime.runtime import AgentRuntime

        return AgentRuntime._normalize_output(output, raw_status, reason)

    @staticmethod
    def _derive_finish_reason(raw_status: str, output: Any) -> Any:
        """Derive a :class:`FinishReason` (delegates to AgentRuntime)."""
        from conductor.ai.agents.runtime.runtime import AgentRuntime

        return AgentRuntime._derive_finish_reason(raw_status, output)

    # ── Lifecycle ────────────────────────────────────────────────────

    async def close(self) -> None:
        """Close the underlying httpx client."""
        if self._client is not None and not self._client.is_closed:
            await self._client.aclose()
            self._client = None


def _run_sync(coro: Any) -> Any:
    """Run a coroutine from a sync context, handling nested event loops."""
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None

    if loop is not None and loop.is_running():
        import concurrent.futures

        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            return pool.submit(asyncio.run, coro).result()
    return asyncio.run(coro)


class _ClientRuntimeAdapter:
    """Adapts an :class:`AgentClient` to the runtime surface :class:`AgentHandle` expects.

    :class:`AgentHandle` was written against :class:`AgentRuntime`. For a
    control-plane handle (returned by :meth:`AgentClient.start`) there is no
    runtime — this thin shim provides the same sync+async methods AgentHandle
    calls (``get_status`` / ``get_status_async`` / ``respond`` / ``stop`` /
    ``_normalize_output`` / ``_derive_finish_reason`` / ``_extract_token_usage``)
    by delegating to the client. It does NOT manage workers; ``_config`` is
    absent so AgentHandle's liveness monitor stays disabled.
    """

    def __init__(self, client: "AgentClient") -> None:
        self._client = client
        self._workflow_client = client._workflow_client

    # ── status (sync + async) ──
    def get_status(self, execution_id: str) -> Any:
        return self._client.get_status_sync(execution_id)

    async def get_status_async(self, execution_id: str) -> Any:
        return await self._client.get_status_async(execution_id)

    # ── HITL / control (sync + async) ──
    def respond(self, execution_id: str, output: Any) -> None:
        _run_sync(self._client.respond_async(execution_id, output))

    async def respond_async(self, execution_id: str, output: Any) -> None:
        await self._client.respond_async(execution_id, output)

    def stop(self, execution_id: str) -> None:
        _run_sync(self._client.stop_async(execution_id))

    async def stop_async(self, execution_id: str) -> None:
        await self._client.stop_async(execution_id)

    def pause(self, execution_id: str) -> None:
        self._workflow_client.pause_workflow(execution_id)

    async def pause_async(self, execution_id: str) -> None:
        _run_sync(asyncio.sleep(0))  # keep coroutine semantics
        self._workflow_client.pause_workflow(execution_id)

    def _resume_workflow(self, execution_id: str) -> None:
        self._workflow_client.resume_workflow(execution_id)

    async def _resume_workflow_async(self, execution_id: str) -> None:
        self._workflow_client.resume_workflow(execution_id)

    def cancel(self, execution_id: str, reason: str = "") -> None:
        self._workflow_client.terminate_workflow(workflow_id=execution_id, reason=reason)

    async def cancel_async(self, execution_id: str, reason: str = "") -> None:
        self._workflow_client.terminate_workflow(workflow_id=execution_id, reason=reason)

    # ── streaming (delegates to the client's SSE endpoint) ──
    def _stream_workflow(self, execution_id: str):
        from conductor.ai.agents.result import AgentEvent, EventType

        async def _aiter():
            async for sse in self._client.stream_sse(execution_id):
                yield sse

        # Bridge async SSE → sync iterator for AgentHandle.stream().
        gen = _aiter()

        def _sync_iter():
            loop = asyncio.new_event_loop()
            try:
                while True:
                    try:
                        sse = loop.run_until_complete(gen.__anext__())
                    except StopAsyncIteration:
                        return
                    ev = _sse_to_event(sse, execution_id, AgentEvent, EventType)
                    if ev is not None:
                        yield ev
            finally:
                loop.close()

        return _sync_iter()

    async def _stream_workflow_async(self, execution_id: str):
        from conductor.ai.agents.result import AgentEvent, EventType

        async for sse in self._client.stream_sse(execution_id):
            ev = _sse_to_event(sse, execution_id, AgentEvent, EventType)
            if ev is not None:
                yield ev

    # ── result helpers (delegate to client / AgentRuntime statics) ──
    def _normalize_output(self, output: Any, raw_status: str, reason: Optional[str] = None) -> Any:
        return self._client._normalize_output(output, raw_status, reason)

    def _derive_finish_reason(self, raw_status: str, output: Any) -> Any:
        return self._client._derive_finish_reason(raw_status, output)

    def _extract_token_usage(self, execution_id: str) -> Any:
        return self._client._extract_token_usage(execution_id)


def _sse_to_event(sse: Dict[str, Any], execution_id: str, AgentEvent: Any, EventType: Any) -> Any:
    """Map a raw SSE event dict to an :class:`AgentEvent` (minimal mapping)."""
    event_type = sse.get("event")
    data = sse.get("data") or {}
    if not isinstance(data, dict):
        data = {"content": data}
    type_map = {
        "thinking": EventType.THINKING,
        "tool_call": EventType.TOOL_CALL,
        "tool_result": EventType.TOOL_RESULT,
        "handoff": EventType.HANDOFF,
        "waiting": EventType.WAITING,
        "message": EventType.MESSAGE,
        "error": EventType.ERROR,
        "done": EventType.DONE,
        "guardrail_pass": EventType.GUARDRAIL_PASS,
        "guardrail_fail": EventType.GUARDRAIL_FAIL,
    }
    mapped = type_map.get(event_type)
    if mapped is None:
        return None
    return AgentEvent(
        type=mapped,
        content=data.get("content") or data.get("message"),
        tool_name=data.get("toolName") or data.get("tool_name"),
        args=data.get("args"),
        result=data.get("result"),
        target=data.get("target"),
        output=data.get("output"),
        execution_id=execution_id,
        guardrail_name=data.get("guardrailName") or data.get("guardrail_name"),
    )


# ── Backward-compatibility alias ────────────────────────────────────────
# ``AgentHttpClient`` was renamed to ``AgentClient``; keep the old name so
# existing imports (``from ...http_client import AgentHttpClient``) still work.
AgentHttpClient = AgentClient
