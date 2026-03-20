# sdk/python/src/agentspan/agents/frameworks/claude.py
# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""Claude Agent SDK integration for Agentspan."""

from __future__ import annotations

import asyncio
import concurrent.futures
import dataclasses
import glob
import logging
import os
import urllib.parse
from typing import Any, Dict, List, Optional, Tuple

try:
    from claude_agent_sdk import ClaudeAgentOptions, HookMatcher, query
except ImportError:
    query = None  # type: ignore[assignment]

    class ClaudeAgentOptions:  # type: ignore[no-redef]
        """Stub for ClaudeAgentOptions when claude_agent_sdk is not installed."""

        def __init__(self, **kwargs: Any) -> None:
            for k, v in kwargs.items():
                setattr(self, k, v)

    class HookMatcher:  # type: ignore[no-redef]
        """Stub for HookMatcher when claude_agent_sdk is not installed."""

        def __init__(self, matcher: str, hooks: list) -> None:
            self.matcher = matcher
            self.hooks = hooks


logger = logging.getLogger(__name__)


@dataclasses.dataclass
class ClaudeCodeAgent:
    """A Claude Agent SDK agent that runs as an Agentspan passthrough worker."""

    name: str = "claude_agent"
    prompt: str = ""
    cwd: str = "."
    allowed_tools: List[str] = dataclasses.field(default_factory=list)
    disallowed_tools: List[str] = dataclasses.field(default_factory=list)
    max_turns: int = 100
    model: str = "claude-opus-4-6"
    max_tokens: int = 8192
    system_prompt: Optional[str] = None
    conductor_subagents: bool = False
    agentspan_routing: bool = False       # Deprecated: use mcp_tools + conductor_subagents
    mcp_tools: List[Any] = dataclasses.field(default_factory=list)
    agents: Dict[str, Any] = dataclasses.field(default_factory=dict)
    permission_mode: Optional[str] = None
    subagent_overrides: Dict[str, Any] = dataclasses.field(default_factory=dict)  # Deprecated


def serialize_claude(agent: ClaudeCodeAgent) -> Tuple[Dict[str, Any], List]:
    """Serialize a ClaudeCodeAgent to (raw_config, [WorkerInfo]).

    Returns func=None in WorkerInfo — filled later by _build_passthrough_func().
    Follows the same pattern as serialize_langgraph().
    """
    from agentspan.agents.frameworks.serializer import WorkerInfo

    worker_name = f"_fw_claude_{agent.name}"
    raw_config = {
        "_worker_name": worker_name,
        "cwd": agent.cwd,
        "allowed_tools": agent.allowed_tools,
        "disallowed_tools": agent.disallowed_tools,
        "max_turns": agent.max_turns,
        "model": agent.model,
        "max_tokens": agent.max_tokens,
        "system_prompt": agent.system_prompt,
        "conductor_subagents": agent.conductor_subagents,
        "agentspan_routing": agent.agentspan_routing,
        "permission_mode": agent.permission_mode,
    }
    worker = WorkerInfo(
        name=worker_name,
        description=f"Claude Agent SDK passthrough worker ({agent.name})",
        input_schema={
            "type": "object",
            "properties": {
                "prompt": {"type": "string"},
                "cwd": {"type": "string"},
            },
        },
        func=None,
    )
    return raw_config, [worker]


# ── Session helpers ────────────────────────────────────────────────────────────


def _find_session_file(session_id: str) -> Optional[str]:
    """Locate Claude CLI session JSONL by session_id using glob."""
    pattern = os.path.expanduser(f"~/.claude/projects/**/{session_id}.jsonl")
    matches = glob.glob(pattern, recursive=True)
    return matches[0] if matches else None


def _write_session_file(session_id: str, cwd: str, jsonl_content: str) -> str:
    """Write JSONL content to the path the CLI expects.

    Format: ~/.claude/projects/<url-encoded-abs-cwd>/<session-id>.jsonl
    """
    encoded_cwd = urllib.parse.quote(os.path.abspath(cwd), safe="")
    path = os.path.expanduser(f"~/.claude/projects/{encoded_cwd}/{session_id}.jsonl")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        f.write(jsonl_content)
    return path


def _restore_session(workflow_id: str, cwd: str, server_url: str, headers: dict) -> Optional[str]:
    """GET /api/agent-sessions/{workflowId}, write JSONL to disk, return session_id."""
    try:
        import requests

        resp = requests.get(
            f"{server_url}/api/agent-sessions/{workflow_id}",
            headers=headers,
            timeout=10,
        )
        if resp.status_code == 404:
            return None
        resp.raise_for_status()
        data = resp.json()
        session_id = data["sessionId"]
        _write_session_file(session_id, cwd, data["jsonlContent"])
        logger.info("Restored session %s for workflow %s", session_id, workflow_id)
        return session_id
    except Exception as exc:
        logger.warning("Failed to restore session for %s: %s", workflow_id, exc)
        return None


def _checkpoint_session(
    workflow_id: str, session_id: Optional[str], cwd: str, server_url: str, headers: dict
) -> None:
    """POST /api/agent-sessions/{workflowId} with current JSONL file contents."""
    if not session_id:
        return
    session_file = _find_session_file(session_id)
    if not session_file:
        logger.warning("Cannot checkpoint: session file not found for %s", session_id)
        return
    try:
        import requests

        with open(session_file) as f:
            jsonl_content = f.read()
        requests.post(
            f"{server_url}/api/agent-sessions/{workflow_id}",
            json={"sessionId": session_id, "jsonlContent": jsonl_content},
            headers=headers,
            timeout=10,
        )
    except Exception as exc:
        logger.warning("Failed to checkpoint session for %s: %s", workflow_id, exc)


# ── Event push ─────────────────────────────────────────────────────────────────

_push_executor = concurrent.futures.ThreadPoolExecutor(
    max_workers=4, thread_name_prefix="claude-events"
)


def _push_event_nonblocking(
    workflow_id: str, event_type: str, payload: dict, server_url: str, headers: dict
) -> None:
    """Fire-and-forget POST to /api/agent/events/{workflowId}."""

    def _post():
        try:
            import requests

            requests.post(
                f"{server_url}/api/agent/events/{workflow_id}",
                json={"type": event_type, **payload},
                headers=headers,
                timeout=5,
            )
        except Exception as exc:
            logger.debug("Event push failed for %s/%s: %s", workflow_id, event_type, exc)

    _push_executor.submit(_post)


# ── Tier 2/3 helper clients ─────────────────────────────────────────────────


class _ConductorSubagentClient:
    """Async Conductor HTTP client for starting and polling SUB_WORKFLOWs (Tier 2 & 3)."""

    def __init__(self, server_url: str, auth_key: str, auth_secret: str) -> None:
        self._server_url = server_url.rstrip("/")
        self._headers: Dict[str, str] = {"Content-Type": "application/json"}
        if auth_key:
            self._headers["X-Auth-Key"] = auth_key
        if auth_secret:
            self._headers["X-Auth-Secret"] = auth_secret

    async def start_workflow(self, workflow_name: str, input_data: dict) -> str:
        """POST /api/workflow/{workflow_name} and return the new workflow instance ID."""
        import httpx

        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                f"{self._server_url}/api/workflow/{workflow_name}",
                json=input_data,
                headers=self._headers,
            )
            resp.raise_for_status()
            # Conductor returns a plain UUID string (possibly JSON-quoted)
            return resp.text.strip().strip('"')

    async def poll_until_done(self, workflow_id: str, poll_interval: float = 2.0) -> str:
        """Poll GET /api/workflow/{workflow_id} until terminal status, return output."""
        import asyncio

        import httpx

        async with httpx.AsyncClient(timeout=30) as client:
            while True:
                resp = await client.get(
                    f"{self._server_url}/api/workflow/{workflow_id}",
                    headers=self._headers,
                )
                resp.raise_for_status()
                data = resp.json()
                status = data.get("status")
                if status == "COMPLETED":
                    return data.get("output", {}).get("result", "")
                if status in ("FAILED", "TIMED_OUT", "TERMINATED"):
                    raise RuntimeError(f"Subworkflow {workflow_id} ended with status {status}")
                await asyncio.sleep(poll_interval)

    async def start_tool_workflow(self, tool_name: str, input_data: dict) -> str:
        """Register a single-task tool wrapper workflow (idempotent) and start it.

        Workflow name: _mcp_tool_<tool_name>  (prefixed to avoid collision with
        the Conductor task definition of the same name).
        """
        import httpx

        workflow_name = f"_mcp_tool_{tool_name}"
        workflow_def = {
            "name": workflow_name,
            "version": 1,
            "schemaVersion": 2,
            "tasks": [
                {
                    "name": tool_name,
                    "taskReferenceName": f"{tool_name}_ref",
                    "type": "SIMPLE",
                    "inputParameters": {k: f"${{workflow.input.{k}}}" for k in input_data},
                }
            ],
            "outputParameters": {"result": f"${{{tool_name}_ref.output.result}}"},
            "inputParameters": list(input_data.keys()),
            "timeoutSeconds": 0,
            "timeoutPolicy": "ALERT_ONLY",
            "restartable": True,
        }
        async with httpx.AsyncClient(timeout=15) as client:
            await client.put(
                f"{self._server_url}/metadata/workflow",
                json=[workflow_def],
                headers=self._headers,
            )
            resp = await client.post(
                f"{self._server_url}/workflow/{workflow_name}",
                json=input_data,
                headers=self._headers,
            )
            resp.raise_for_status()
            return resp.text.strip().strip('"')


class _AgentspanEventClient:
    """Async HTTP client for pushing SSE events to the Agentspan server (Tier 2 & 3)."""

    def __init__(self, server_url: str, auth_key: str, auth_secret: str) -> None:
        self._server_url = server_url.rstrip("/")
        self._headers: Dict[str, str] = {"Content-Type": "application/json"}
        if auth_key:
            self._headers["X-Auth-Key"] = auth_key
        if auth_secret:
            self._headers["X-Auth-Secret"] = auth_secret

    async def push(self, workflow_id: str, event_type: str, payload: dict) -> None:
        """Fire-and-forget POST to /api/agent/events/{workflowId}."""
        import httpx

        try:
            async with httpx.AsyncClient(timeout=5) as client:
                await client.post(
                    f"{self._server_url}/api/agent/events/{workflow_id}",
                    json={"type": event_type, **payload},
                    headers=self._headers,
                )
        except Exception as exc:
            logger.debug("Async event push failed for %s/%s: %s", workflow_id, event_type, exc)


# ── Tier 2 subagent hook ────────────────────────────────────────────────────


def make_subagent_hook(
    workflow_name: str,
    workflow_id: str,
    conductor: "_ConductorSubagentClient",
    events: "_AgentspanEventClient",
):
    """Create a PreToolUse hook that intercepts Agent tool calls for Tier 2.

    Instead of running an in-process subagent, starts a real Conductor
    SUB_WORKFLOW with the same workflow definition, polls for completion,
    and returns the result via a hook denial so Claude sees it as the
    Agent tool's output.
    """

    async def hook(input_data, tool_use_id, context):
        if input_data.get("tool_name") != "Agent":
            return {}  # pass through all non-Agent tools

        prompt = input_data.get("tool_input", {}).get("prompt", "")
        try:
            sub_id = await conductor.start_workflow(
                workflow_name, {"prompt": prompt, "_is_subagent": True}
            )
            logger.info("Tier 2 sub-workflow started: %s", sub_id)
            await events.push(workflow_id, "subagent_start", {"subWorkflowId": sub_id})
            result = await conductor.poll_until_done(sub_id)
            await events.push(
                workflow_id,
                "subagent_stop",
                {"subWorkflowId": sub_id, "result": result},
            )
        except Exception as exc:
            logger.error("Tier 2 subagent workflow failed: %s", exc)
            result = f"Subagent failed: {exc}"

        return {
            "hookSpecificOutput": {
                "hookEventName": "PreToolUse",
                "permissionDecision": "deny",
                "permissionDecisionReason": result,
            }
        }

    return hook


# ── Worker factory ─────────────────────────────────────────────────────────────


def make_claude_worker(
    agent_obj: "ClaudeCodeAgent", name: str, server_url: str, auth_key: str, auth_secret: str
):
    """Build the passthrough worker function for a ClaudeCodeAgent.

    Returned function signature: tool_worker(task: Task) -> TaskResult
    """
    # Module-level imports from claude_agent_sdk are deferred to avoid import errors
    # in environments where claude_agent_sdk is not installed.
    # They are imported at the top of tool_worker() so patches in tests work correctly.

    def _is_system_init(msg) -> bool:
        return msg.__class__.__name__ == "SystemMessage" and getattr(msg, "subtype", None) == "init"

    def _is_result(msg) -> bool:
        return msg.__class__.__name__ == "ResultMessage"

    def _make_headers() -> dict:
        headers = {"Content-Type": "application/json"}
        if auth_key:
            headers["X-Auth-Key"] = auth_key
        if auth_secret:
            headers["X-Auth-Secret"] = auth_secret
        return headers

    def tool_worker(task):
        from conductor.client.http.models.task_result import TaskResult
        from conductor.client.http.models.task_result_status import TaskResultStatus

        # Import all names at function call time so tests can patch them at module level
        from agentspan.agents.frameworks.claude import (
            ClaudeAgentOptions,
            HookMatcher,
            _AgentspanEventClient,
            _checkpoint_session,
            _ConductorSubagentClient,
            _push_event_nonblocking,
            _restore_session,
            query,
        )

        workflow_id = task.workflow_instance_id
        prompt = task.input_data.get("prompt", "")
        cwd = task.input_data.get("cwd", ".")
        headers = _make_headers()
        _is_subagent = task.input_data.get("_is_subagent", False)

        restored_session_id = _restore_session(workflow_id, cwd, server_url, headers)
        session_id_ref = {"value": restored_session_id}

        # ── Build MCP server if needed ─────────────────────────────────────────
        mcp_server_config = None
        needs_mcp = (agent_obj.mcp_tools or agent_obj.conductor_subagents) and not _is_subagent

        if needs_mcp:
            from agentspan.agents.frameworks.claude_mcp_server import AgentspanMcpServer

            conductor_client = _ConductorSubagentClient(server_url, auth_key, auth_secret)
            event_client = _AgentspanEventClient(server_url, auth_key, auth_secret)

            mcp_server = AgentspanMcpServer(
                tools=agent_obj.mcp_tools,
                subagent_workflow_name=name if agent_obj.conductor_subagents else None,
                conductor_client=conductor_client,
                event_client=event_client,
                parent_workflow_id=workflow_id,
            )
            mcp_server_config = mcp_server.build()

        # ── Observability hooks (always on) ────────────────────────────────────
        async def pre_tool_hook(input_data, tool_use_id, context):
            _push_event_nonblocking(
                workflow_id,
                "tool_call",
                {
                    "source": "builtin",
                    "toolName": input_data.get("tool_name", ""),
                    "args": input_data.get("tool_input", {}),
                },
                server_url,
                headers,
            )
            return {}

        async def post_tool_hook(input_data, tool_use_id, context):
            _push_event_nonblocking(
                workflow_id,
                "tool_result",
                {
                    "source": "builtin",
                    "toolName": input_data.get("tool_name", ""),
                    "result": input_data.get("tool_response"),
                },
                server_url,
                headers,
            )
            _checkpoint_session(workflow_id, session_id_ref["value"], cwd, server_url, headers)
            return {}

        hooks = {
            "PreToolUse": [HookMatcher(matcher=".*", hooks=[pre_tool_hook])],
            "PostToolUse": [HookMatcher(matcher=".*", hooks=[post_tool_hook])],
        }

        async def run():
            result_text = None
            options_kwargs: Dict[str, Any] = {}
            query_kwargs: Dict[str, Any] = {}

            if mcp_server_config is not None:
                options_kwargs["mcp_servers"] = {"agentspan": mcp_server_config}

            if agent_obj.disallowed_tools:
                options_kwargs["disallowed_tools"] = agent_obj.disallowed_tools

            if agent_obj.permission_mode:
                options_kwargs["permission_mode"] = agent_obj.permission_mode

            # Tier 3 backward compat: agentspan_routing passes transport to query()
            if agent_obj.agentspan_routing and not _is_subagent:
                from agentspan.agents.frameworks.claude_transport import AgentspanTransport

                conductor_client_t3 = _ConductorSubagentClient(server_url, auth_key, auth_secret)
                event_client_t3 = _AgentspanEventClient(server_url, auth_key, auth_secret)
                query_kwargs["transport"] = AgentspanTransport(
                    agent_config={
                        "_worker_name": name,
                        "cwd": cwd,
                        "allowed_tools": agent_obj.allowed_tools,
                        "max_turns": agent_obj.max_turns,
                        "model": agent_obj.model,
                        "max_tokens": agent_obj.max_tokens,
                        "system_prompt": agent_obj.system_prompt,
                    },
                    conductor_client=conductor_client_t3,
                    event_client=event_client_t3,
                    workflow_id=workflow_id,
                    cwd=cwd,
                )

            async for msg in query(
                prompt=prompt,
                options=ClaudeAgentOptions(
                    cwd=cwd,
                    allowed_tools=agent_obj.allowed_tools,
                    max_turns=agent_obj.max_turns,
                    resume=restored_session_id,
                    system_prompt=agent_obj.system_prompt,
                    hooks=hooks,
                    **options_kwargs,
                ),
                **query_kwargs,
            ):
                if _is_system_init(msg):
                    session_id_ref["value"] = msg.data.get("session_id")
                elif _is_result(msg):
                    result_text = msg.result
            return result_text

        try:
            result = asyncio.run(run())
            task_result = TaskResult(
                status=TaskResultStatus.COMPLETED,
                output_data={"result": result},
            )
            task_result.task_id = task.task_id
            return task_result
        except Exception as exc:
            logger.error("Claude worker failed for %s: %s", workflow_id, exc)
            task_result = TaskResult(
                status=TaskResultStatus.FAILED,
                output_data={"error": str(exc)},
            )
            task_result.task_id = task.task_id
            return task_result

    return tool_worker
