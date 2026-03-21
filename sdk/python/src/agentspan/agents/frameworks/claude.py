# sdk/python/src/agentspan/agents/frameworks/claude.py
# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""Claude Agent SDK integration for Agentspan."""

from __future__ import annotations

import asyncio
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
    mcp_tools: List[Any] = dataclasses.field(default_factory=list)
    agents: Dict[str, Any] = dataclasses.field(default_factory=dict)
    permission_mode: Optional[str] = None


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


def _read_last_result_from_transcript(transcript_path: str) -> str:
    """Read the final ResultMessage text from a Claude JSONL transcript file.

    Returns empty string if the file cannot be read or has no ResultMessage.
    """
    import json

    if not transcript_path:
        return ""
    try:
        result = ""
        with open(transcript_path) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                    if entry.get("type") == "result":
                        result = entry.get("result", "")
                except json.JSONDecodeError:
                    continue
        return result
    except Exception as exc:
        logger.debug("Could not read transcript %s: %s", transcript_path, exc)
        return ""


class _AgentDagClient:
    """Async HTTP client for injecting tasks into running Conductor workflow instances.

    All methods are non-fatal: exceptions are caught, logged at DEBUG, and swallowed.
    Claude must never be blocked by observability failures.
    """

    def __init__(self, server_url: str, auth_key: str, auth_secret: str) -> None:
        self._server_url = server_url.rstrip("/")
        self._headers: Dict[str, str] = {"Content-Type": "application/json"}
        if auth_key:
            self._headers["X-Auth-Key"] = auth_key
        if auth_secret:
            self._headers["X-Auth-Secret"] = auth_secret

    async def inject_task(
        self,
        workflow_id: str,
        task_def_name: str,
        reference_name: str,
        input_data: Dict[str, Any],
        task_type: str = "SIMPLE",
        sub_workflow_param: Optional[Dict[str, Any]] = None,
    ) -> Optional[str]:
        """Inject a new IN_PROGRESS task into a running workflow. Returns conductor task_id."""
        import httpx

        payload: Dict[str, Any] = {
            "taskDefName": task_def_name,
            "referenceTaskName": reference_name,
            "type": task_type,
            "inputData": input_data,
            "status": "IN_PROGRESS",
        }
        if sub_workflow_param is not None:
            payload["subWorkflowParam"] = sub_workflow_param
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.post(
                    f"{self._server_url}/api/agent/{workflow_id}/tasks",
                    json=payload,
                    headers=self._headers,
                )
                resp.raise_for_status()
                return resp.json().get("taskId")
        except Exception as exc:
            logger.debug("inject_task failed (%s/%s): %s", workflow_id, task_def_name, exc)
            return None

    async def create_tracking_workflow(
        self, workflow_name: str, input_data: Dict[str, Any]
    ) -> Optional[str]:
        """Create a bare tracking workflow shell. Returns new workflow_id."""
        import httpx

        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.post(
                    f"{self._server_url}/api/agent/workflow",
                    json={"workflowName": workflow_name, "input": input_data},
                    headers=self._headers,
                )
                resp.raise_for_status()
                return resp.json().get("workflowId")
        except Exception as exc:
            logger.debug("create_tracking_workflow failed (%s): %s", workflow_name, exc)
            return None

    async def complete_task(
        self, workflow_id: str, task_id: str, output_data: Dict[str, Any]
    ) -> None:
        """Mark a Conductor task as COMPLETED with output. Non-fatal: silently logs on failure."""
        import httpx

        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.post(
                    f"{self._server_url}/api/task",
                    json={
                        "taskId": task_id,
                        "workflowInstanceId": workflow_id,
                        "status": "COMPLETED",
                        "outputData": output_data,
                    },
                    headers=self._headers,
                )
                resp.raise_for_status()
        except Exception as exc:
            logger.debug("complete_task failed (%s/%s): %s", workflow_id, task_id, exc)

    async def fail_task(self, workflow_id: str, task_id: str, error: str) -> None:
        """Mark a Conductor task as FAILED with a reason. Non-fatal: silently logs on failure."""
        import httpx

        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.post(
                    f"{self._server_url}/api/task",
                    json={
                        "taskId": task_id,
                        "workflowInstanceId": workflow_id,
                        "status": "FAILED",
                        "reasonFailed": error,
                    },
                    headers=self._headers,
                )
                resp.raise_for_status()
        except Exception as exc:
            logger.debug("fail_task failed (%s/%s): %s", workflow_id, task_id, exc)

    async def push_event(self, workflow_id: str, event_type: str, payload: Dict[str, Any]) -> None:
        """POST an SSE event to the Agentspan server (non-fatal)."""
        import httpx

        try:
            async with httpx.AsyncClient(timeout=5) as client:
                resp = await client.post(
                    f"{self._server_url}/api/agent/events/{workflow_id}",
                    json={"type": event_type, **payload},
                    headers=self._headers,
                )
                resp.raise_for_status()
        except Exception as exc:
            logger.debug("push_event failed (%s/%s): %s", workflow_id, event_type, exc)


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
            # Used by DAG hooks (Task 3: new hook implementation)
            _AgentDagClient,
            _checkpoint_session,
            _read_last_result_from_transcript,
            _restore_session,
            query,
        )

        workflow_id = task.workflow_instance_id
        prompt = task.input_data.get("prompt", "")
        cwd = task.input_data.get("cwd", ".")
        headers = _make_headers()

        restored_session_id = _restore_session(workflow_id, cwd, server_url, headers)
        session_id_ref = {"value": restored_session_id}

        # ── Build MCP server if needed ─────────────────────────────────────────
        mcp_server_config = None
        needs_mcp = bool(agent_obj.mcp_tools)

        if needs_mcp:
            from agentspan.agents.frameworks.claude_mcp_server import AgentspanMcpServer

            mcp_server = AgentspanMcpServer(tools=agent_obj.mcp_tools)
            mcp_server_config = mcp_server.build()

        # ── DAG client + per-execution state ───────────────────────────────────
        dag = _AgentDagClient(server_url, auth_key, auth_secret)
        # tool_use_id → (workflow_id, conductor_task_id)
        tool_task_map: Dict[str, Tuple[str, str]] = {}

        # ── Hooks ──────────────────────────────────────────────────────────────

        async def pre_tool_hook(input_data, tool_use_id, context):
            if tool_use_id is None:
                return {}
            tool_name = input_data.get("tool_name", "")
            tool_input = input_data.get("tool_input", {})

            try:
                if tool_name == "Agent":
                    # Subagent spawn: create child tracking workflow + SUB_WORKFLOW task.
                    # NOTE: SDK 0.1.26 has no SubagentStart — we intercept here instead.
                    sub_wf_id = await dag.create_tracking_workflow(
                        name, {"prompt": tool_input.get("prompt", "")}
                    )
                    if sub_wf_id:
                        task_id = await dag.inject_task(
                            workflow_id,
                            "claude-sub-agent",
                            tool_use_id,
                            tool_input,
                            "SUB_WORKFLOW",
                            sub_workflow_param={
                                "name": name,
                                "version": 1,
                                "workflowId": sub_wf_id,
                            },
                        )
                        if task_id:
                            tool_task_map[tool_use_id] = (workflow_id, task_id)
                    else:
                        logger.debug(
                            "Skipping Agent tool DAG tracking: create_tracking_workflow returned None"
                        )
                else:
                    task_id = await dag.inject_task(workflow_id, tool_name, tool_use_id, tool_input)
                    if task_id:
                        tool_task_map[tool_use_id] = (workflow_id, task_id)
            except Exception as exc:
                logger.debug("pre_tool_hook failed (non-fatal): %s", exc)

            return {}

        async def post_tool_hook(input_data, tool_use_id, context):
            if tool_use_id and tool_use_id in tool_task_map:
                wf_id, task_id = tool_task_map.pop(tool_use_id)
                tool_response = input_data.get("tool_response")
                try:
                    await dag.complete_task(wf_id, task_id, {"result": tool_response})
                except Exception as exc:
                    logger.debug("post_tool_hook failed (non-fatal): %s", exc)
            _checkpoint_session(workflow_id, session_id_ref["value"], cwd, server_url, headers)
            return {}

        async def post_tool_failure_hook(input_data, tool_use_id, context):
            if tool_use_id and tool_use_id in tool_task_map:
                wf_id, task_id = tool_task_map.pop(tool_use_id)
                error = input_data.get("error", "tool failed")
                try:
                    await dag.fail_task(wf_id, task_id, error)
                except Exception as exc:
                    logger.debug("post_tool_failure_hook failed (non-fatal): %s", exc)
            return {}

        async def subagent_stop_hook(input_data, tool_use_id, context):
            # SubagentStop fires after a subagent completes.
            # tool_use_id matches the Agent tool call's tool_use_id from PreToolUse.
            # (If the SDK changes this contract, update accordingly during E2E testing.)
            if tool_use_id and tool_use_id in tool_task_map:
                wf_id, task_id = tool_task_map.pop(tool_use_id)
                transcript_path = input_data.get("transcript_path", "")
                result = _read_last_result_from_transcript(transcript_path)
                try:
                    await dag.complete_task(wf_id, task_id, {"result": result})
                except Exception as exc:
                    logger.debug("subagent_stop_hook failed (non-fatal): %s", exc)
            _checkpoint_session(workflow_id, session_id_ref["value"], cwd, server_url, headers)
            return {}

        hooks = {
            "PreToolUse": [HookMatcher(matcher=".*", hooks=[pre_tool_hook])],
            "PostToolUse": [HookMatcher(matcher=".*", hooks=[post_tool_hook])],
            "PostToolUseFailure": [HookMatcher(matcher=".*", hooks=[post_tool_failure_hook])],
            "SubagentStop": [HookMatcher(matcher=".*", hooks=[subagent_stop_hook])],
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
