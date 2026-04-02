# sdk/python/src/agentspan/agents/frameworks/claude_agent_sdk.py
# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""Claude Agent SDK passthrough worker support.

Provides:
- serialize_claude_agent_sdk(options) -> (raw_config, [WorkerInfo])
- make_claude_agent_sdk_worker(options, name, server_url, auth_key, auth_secret) -> tool_worker
"""

from __future__ import annotations

import asyncio
import copy
import logging
import re
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import is_dataclass, replace
from typing import Any, Dict, List, Tuple

from agentspan.agents.frameworks.serializer import WorkerInfo

logger = logging.getLogger("agentspan.agents.frameworks.claude_agent_sdk")

_DEFAULT_NAME = "claude_agent_sdk_agent"

_EVENT_PUSH_POOL = ThreadPoolExecutor(
    max_workers=4, thread_name_prefix="claude-code-sdk-event-push"
)

# Minimum seconds between IN_PROGRESS task updates to avoid spamming the server
_PROGRESS_UPDATE_INTERVAL_S = 30

# Max characters of tool output / assistant text to include in progress updates
_PROGRESS_SNIPPET_MAX_CHARS = 500

# Max characters for tool args/output stored per tool call entry
_TOOL_OUTPUT_MAX_CHARS = 1000


def _truncate_dict_values(d: Any, max_chars: int) -> Any:
    """Truncate long string values in a dict (shallow, one level)."""
    if not isinstance(d, dict):
        return d
    result = {}
    for k, v in d.items():
        if isinstance(v, str) and len(v) > max_chars:
            result[k] = v[:max_chars] + "…"
        else:
            result[k] = v
    return result


def serialize_claude_agent_sdk(agent_or_options: Any) -> Tuple[Dict[str, Any], List[WorkerInfo]]:
    """Serialize Claude Agent SDK options or Agent into (raw_config, [WorkerInfo]).

    Always produces a passthrough config — the entire query() runs in one worker.
    """
    from agentspan.agents.agent import Agent

    if isinstance(agent_or_options, Agent):
        name = agent_or_options.name
    else:
        name = _extract_name(agent_or_options)
    logger.info("Claude Agent SDK '%s': passthrough", name)

    raw_config: Dict[str, Any] = {"name": name, "_worker_name": name}
    worker = WorkerInfo(
        name=name,
        description=f"Claude Agent SDK passthrough worker for {name}",
        input_schema={
            "type": "object",
            "properties": {
                "prompt": {"type": "string"},
                "session_id": {"type": "string"},
            },
        },
        func=None,  # Filled by _build_passthrough_func()
    )
    return raw_config, [worker]


def _extract_name(options: Any) -> str:
    """Extract a sanitized name from options, falling back to default."""
    system_prompt = getattr(options, "system_prompt", None) or getattr(
        options, "systemPrompt", None
    )
    if not system_prompt or not isinstance(system_prompt, str):
        return _DEFAULT_NAME
    slug = re.sub(r"[^a-zA-Z0-9]+", "_", system_prompt[:40]).strip("_").lower()
    return slug or _DEFAULT_NAME


# ---------------------------------------------------------------------------
# Lazy SDK import
# ---------------------------------------------------------------------------


def _import_sdk():
    """Import and return the claude_code_sdk module lazily."""
    import claude_code_sdk

    return claude_code_sdk


# ---------------------------------------------------------------------------
# Agent -> ClaudeCodeOptions conversion
# ---------------------------------------------------------------------------


def agent_to_claude_code_options(agent: Any) -> Any:
    """Convert an Agent(model='claude-code/...') to a ClaudeCodeOptions dataclass.

    This is CRITICAL: make_claude_agent_sdk_worker requires a ClaudeCodeOptions
    dataclass because _merge_hooks calls dataclasses.replace().
    """
    from claude_code_sdk import ClaudeCodeOptions

    from agentspan.agents.claude_code import resolve_claude_code_model

    # Resolve model alias from "claude-code/opus" -> "claude-opus-4-6"
    model_str = getattr(agent, "model", "") or ""
    _, _, alias = model_str.partition("/")
    resolved_model = resolve_claude_code_model(alias) if alias else None

    # Get permission_mode from _claude_code_config if present
    cc_config = getattr(agent, "_claude_code_config", None)
    permission_mode = None
    if cc_config is not None:
        pm = getattr(cc_config, "permission_mode", None)
        if pm is not None:
            permission_mode = pm.value if hasattr(pm, "value") else str(pm)

    # Resolve instructions to string
    instructions = getattr(agent, "instructions", None)
    if callable(instructions):
        try:
            instructions = instructions()
        except TypeError:
            # Function expects arguments -- use docstring as fallback
            instructions = getattr(instructions, "__doc__", None) or ""

    # Get tools as strings
    tools = [str(t) for t in agent.tools] if agent.tools else []

    return ClaudeCodeOptions(
        allowed_tools=tools,
        system_prompt=str(instructions) if instructions else None,
        max_turns=getattr(agent, "max_turns", None),
        model=resolved_model,
        permission_mode=permission_mode or "acceptEdits",
    )


# ---------------------------------------------------------------------------
# Passthrough worker
# ---------------------------------------------------------------------------


def make_claude_agent_sdk_worker(
    options: Any,
    name: str,
    server_url: str,
    auth_key: str,
    auth_secret: str,
) -> Any:
    """Build a pre-wrapped tool_worker(task) -> TaskResult for a Claude Agent SDK agent."""
    from conductor.client.http.models.task import Task
    from conductor.client.http.models.task_result import TaskResult
    from conductor.client.http.models.task_result_status import TaskResultStatus

    def tool_worker(task: Task) -> TaskResult:
        execution_id = task.workflow_instance_id
        task_id = task.task_id
        prompt = task.input_data.get("prompt", "")
        cwd = (task.input_data.get("cwd") or "").strip() or None

        # Metadata dict -- hooks close over this to track counters and progress state
        metadata: Dict[str, Any] = {
            "tool_call_count": 0,
            "tool_error_count": 0,
            "subagent_count": 0,
            "tools_used": [],           # list of per-call dicts
            "_tool_use_index": {},       # tool_use_id -> list index for O(1) lookup
            "last_tool_output": "",
            "last_progress_time": 0.0,
        }

        # Resolve workflow-level credentials and inject into os.environ
        _injected_cred_keys: List[str] = []
        try:
            _injected_cred_keys = _inject_credentials(task, execution_id)
        except Exception as _cred_err:
            logger.warning("Failed to resolve credentials for Claude Agent SDK: %s", _cred_err)

        # Send initial IN_PROGRESS update so the server knows the worker has started
        _update_task_progress_nonblocking(
            task_id, execution_id, metadata, server_url, auth_key, auth_secret,
        )
        metadata["last_progress_time"] = time.monotonic()

        try:
            # Build agentspan instrumentation hooks
            agentspan_hooks = _build_agentspan_hooks(
                task_id, execution_id, server_url, auth_key, auth_secret, metadata
            )

            # Merge user hooks + agentspan hooks, then update options
            merged_options = _merge_hooks(options, agentspan_hooks)

            # Override cwd if provided in task input
            if cwd:
                if is_dataclass(merged_options) and not isinstance(merged_options, type):
                    merged_options = replace(merged_options, cwd=cwd)
                else:
                    merged_options.cwd = cwd

            # Run the async query
            result_output, token_usage = asyncio.run(_run_query(prompt, merged_options))

            output_data: Dict[str, Any] = {
                "result": result_output,
                "tool_call_count": metadata["tool_call_count"],
                "tool_error_count": metadata["tool_error_count"],
                "subagent_count": metadata["subagent_count"],
                "tools_used": metadata["tools_used"],
                "token_usage": token_usage,
            }

            return TaskResult(
                task_id=task.task_id,
                workflow_instance_id=execution_id,
                status=TaskResultStatus.COMPLETED,
                output_data=output_data,
            )
        except Exception as exc:
            logger.error("Claude Agent SDK worker error (execution_id=%s): %s", execution_id, exc)
            return TaskResult(
                task_id=task.task_id,
                workflow_instance_id=execution_id,
                status=TaskResultStatus.FAILED,
                reason_for_incompletion=str(exc),
            )
        finally:
            _cleanup_credentials(_injected_cred_keys)

    return tool_worker


# ---------------------------------------------------------------------------
# Async query runner
# ---------------------------------------------------------------------------


async def _run_query(prompt: str, options: Any) -> Tuple[str, Any]:
    """Run Claude Agent SDK query via ClaudeSDKClient and collect output.

    Uses ClaudeSDKClient (not the standalone query() function) because
    hooks require bidirectional streaming mode. The standalone query()
    with a string prompt runs in non-streaming mode where the control
    protocol is not initialized, so hook callbacks are never invoked.
    """
    sdk = _import_sdk()
    ClaudeSDKClient = sdk.ClaudeSDKClient
    AssistantMessage = sdk.AssistantMessage
    ResultMessage = sdk.ResultMessage

    result_output = ""
    collected_text: List[str] = []
    token_usage = None

    client = ClaudeSDKClient(options=options)
    logger.debug("ClaudeSDKClient: connecting...")
    await client.connect()
    logger.debug("ClaudeSDKClient: connected, sending query...")
    try:
        await client.query(prompt)
        logger.debug("ClaudeSDKClient: query sent, receiving response...")
        async for message in client.receive_response():
            if isinstance(message, AssistantMessage):
                for block in message.content:
                    if hasattr(block, "text"):
                        collected_text.append(block.text)
            elif isinstance(message, ResultMessage):
                result_output = getattr(message, "result", "") or ""
                token_usage = getattr(message, "usage", None)
                logger.debug("ClaudeSDKClient: ResultMessage received")
    finally:
        logger.debug("ClaudeSDKClient: disconnecting...")
        await client.disconnect()
        logger.debug("ClaudeSDKClient: disconnected")

    if not result_output and collected_text:
        result_output = "\n".join(collected_text)

    return result_output, token_usage


# ---------------------------------------------------------------------------
# Agentspan hooks
# ---------------------------------------------------------------------------


def _build_agentspan_hooks(
    task_id: str,
    execution_id: str,
    server_url: str,
    auth_key: str,
    auth_secret: str,
    metadata: Dict[str, Any],
) -> Dict[str, list]:
    """Build agentspan instrumentation hooks for the Claude Agent SDK.

    Returns a dict mapping event names to lists of HookMatcher dataclasses.
    All hook callbacks are defensive (try/except, return {}).

    Hooks push streaming events AND periodically update the Conductor task
    with IN_PROGRESS status so the server sees real-time progress for this
    long-running worker.
    """
    from claude_code_sdk.types import HookMatcher as SdkHookMatcher

    # -- PreToolUse hook: track tool calls and push events --
    async def _pre_tool_use(input_data: dict, tool_use_id: str | None, context: Any) -> dict:
        try:
            tool_name = input_data.get("tool_name", "")
            tool_input = input_data.get("tool_input", {})
            metadata["tool_call_count"] += 1
            entry = {
                "tool_name": tool_name,
                "args": _truncate_dict_values(tool_input, _TOOL_OUTPUT_MAX_CHARS),
                "status": "running",
                "stdout": "",
                "stderr": "",
            }
            metadata["tools_used"].append(entry)
            if tool_use_id:
                metadata["_tool_use_index"][tool_use_id] = len(metadata["tools_used"]) - 1
            _push_event_nonblocking(
                execution_id,
                {"type": "tool_call", "toolName": tool_name, "toolUseId": tool_use_id},
                server_url,
                auth_key,
                auth_secret,
            )
        except Exception as exc:
            logger.debug("PreToolUse hook error: %s", exc)
        return {}

    # -- PostToolUse hook: push tool result events + throttled task progress --
    async def _post_tool_use(input_data: dict, tool_use_id: str | None, context: Any) -> dict:
        try:
            tool_name = input_data.get("tool_name", "")
            tool_output = str(input_data.get("tool_output", ""))[:_TOOL_OUTPUT_MAX_CHARS]
            metadata["last_tool_output"] = tool_output

            # Update the matching entry with success result
            idx = metadata["_tool_use_index"].get(tool_use_id)
            if idx is not None and idx < len(metadata["tools_used"]):
                metadata["tools_used"][idx]["status"] = "success"
                metadata["tools_used"][idx]["stdout"] = tool_output

            _push_event_nonblocking(
                execution_id,
                {
                    "type": "tool_result",
                    "toolName": tool_name,
                    "toolUseId": tool_use_id,
                },
                server_url,
                auth_key,
                auth_secret,
            )

            # Throttled IN_PROGRESS task update
            now = time.monotonic()
            if now - metadata["last_progress_time"] >= _PROGRESS_UPDATE_INTERVAL_S:
                metadata["last_progress_time"] = now
                _update_task_progress_nonblocking(
                    task_id, execution_id, metadata,
                    server_url, auth_key, auth_secret,
                )
        except Exception as exc:
            logger.debug("PostToolUse hook error: %s", exc)
        return {}

    # -- PostToolUseFailure hook: capture tool errors --
    async def _post_tool_use_failure(input_data: dict, tool_use_id: str | None, context: Any) -> dict:
        try:
            tool_name = input_data.get("tool_name", "")
            error_msg = str(input_data.get("error", ""))[:_TOOL_OUTPUT_MAX_CHARS]
            metadata["tool_error_count"] += 1
            metadata["last_tool_output"] = f"ERROR: {error_msg}"

            # Update the matching entry with error result
            idx = metadata["_tool_use_index"].get(tool_use_id)
            if idx is not None and idx < len(metadata["tools_used"]):
                metadata["tools_used"][idx]["status"] = "error"
                metadata["tools_used"][idx]["stderr"] = error_msg

            _push_event_nonblocking(
                execution_id,
                {
                    "type": "tool_error",
                    "toolName": tool_name,
                    "toolUseId": tool_use_id,
                },
                server_url,
                auth_key,
                auth_secret,
            )

            # Throttled IN_PROGRESS task update
            now = time.monotonic()
            if now - metadata["last_progress_time"] >= _PROGRESS_UPDATE_INTERVAL_S:
                metadata["last_progress_time"] = now
                _update_task_progress_nonblocking(
                    task_id, execution_id, metadata,
                    server_url, auth_key, auth_secret,
                )
        except Exception as exc:
            logger.debug("PostToolUseFailure hook error: %s", exc)
        return {}

    # -- SubagentStop hook: track subagent completions --
    async def _subagent_stop(input_data: dict, tool_use_id: str | None, context: Any) -> dict:
        try:
            metadata["subagent_count"] += 1
            _push_event_nonblocking(
                execution_id,
                {"type": "subagent_stop"},
                server_url,
                auth_key,
                auth_secret,
            )
        except Exception as exc:
            logger.debug("SubagentStop hook error: %s", exc)
        return {}

    # -- Stop hook: signal agent completion --
    async def _stop(input_data: dict, tool_use_id: str | None, context: Any) -> dict:
        try:
            _push_event_nonblocking(
                execution_id,
                {"type": "agent_stop"},
                server_url,
                auth_key,
                auth_secret,
            )
        except Exception as exc:
            logger.debug("Stop hook error: %s", exc)
        return {}

    return {
        "PreToolUse": [SdkHookMatcher(hooks=[_pre_tool_use])],
        "PostToolUse": [SdkHookMatcher(hooks=[_post_tool_use])],
        "PostToolUseFailure": [SdkHookMatcher(hooks=[_post_tool_use_failure])],
        "SubagentStop": [SdkHookMatcher(hooks=[_subagent_stop])],
        "Stop": [SdkHookMatcher(hooks=[_stop])],
    }


# ---------------------------------------------------------------------------
# Hook merging
# ---------------------------------------------------------------------------


def _merge_hooks(options: Any, agentspan_hooks: Dict[str, list]) -> Any:
    """Merge user hooks and agentspan hooks, preserving user hooks first.

    Returns a new options object with the merged hooks dict.
    """
    user_hooks = getattr(options, "hooks", None) or {}
    merged: Dict[str, list] = {}
    all_events = set(list(user_hooks.keys()) + list(agentspan_hooks.keys()))
    for event_name in all_events:
        user_matchers = user_hooks.get(event_name, [])
        as_matchers = agentspan_hooks.get(event_name, [])
        merged[event_name] = list(user_matchers) + as_matchers

    # ClaudeCodeOptions is a dataclass -- use replace()
    if is_dataclass(options) and not isinstance(options, type):
        return replace(options, hooks=merged)
    # Fallback for mock or other types
    new_opts = copy.copy(options)
    new_opts.hooks = merged
    return new_opts


# ---------------------------------------------------------------------------
# Event push (fire-and-forget)
# ---------------------------------------------------------------------------


def _push_event_nonblocking(
    execution_id: str,
    event: Dict[str, Any],
    server_url: str,
    auth_key: str,
    auth_secret: str,
) -> None:
    """Fire-and-forget HTTP POST to {server_url}/agent/events/{executionId}."""

    def _do_push():
        try:
            import requests

            url = f"{server_url}/agent/events/{execution_id}"
            headers: Dict[str, str] = {}
            if auth_key:
                headers["X-Auth-Key"] = auth_key
            if auth_secret:
                headers["X-Auth-Secret"] = auth_secret
            requests.post(url, json=event, headers=headers, timeout=5)
        except Exception as exc:
            logger.debug("Event push failed (execution_id=%s): %s", execution_id, exc)

    _EVENT_PUSH_POOL.submit(_do_push)


def _update_task_progress_nonblocking(
    task_id: str,
    execution_id: str,
    metadata: Dict[str, Any],
    server_url: str,
    auth_key: str,
    auth_secret: str,
) -> None:
    """Fire-and-forget Conductor task update with IN_PROGRESS status.

    Sends current tool counts, tools used, and a snippet of the last output
    so the server (and any polling clients) can see real-time progress from
    this long-running Claude Code worker.
    """

    # Snapshot mutable metadata to avoid races with the hook thread
    all_calls = metadata.get("tools_used", [])
    progress_data: Dict[str, Any] = {
        "tool_call_count": metadata.get("tool_call_count", 0),
        "tool_error_count": metadata.get("tool_error_count", 0),
        "subagent_count": metadata.get("subagent_count", 0),
        "tools_used": all_calls[-5:],  # last 5 calls for progress payload
        "last_tool_output": str(metadata.get("last_tool_output", ""))[:_PROGRESS_SNIPPET_MAX_CHARS],
    }

    def _do_update():
        try:
            import requests

            url = f"{server_url}/tasks"
            headers: Dict[str, str] = {"Content-Type": "application/json"}
            if auth_key:
                headers["X-Auth-Key"] = auth_key
            if auth_secret:
                headers["X-Auth-Secret"] = auth_secret
            body = {
                "taskId": task_id,
                "workflowInstanceId": execution_id,
                "status": "IN_PROGRESS",
                "outputData": progress_data,
            }
            requests.post(url, json=body, headers=headers, timeout=5)
        except Exception as exc:
            logger.debug(
                "Task progress update failed (task_id=%s, execution_id=%s): %s",
                task_id, execution_id, exc,
            )

    _EVENT_PUSH_POOL.submit(_do_update)


# ---------------------------------------------------------------------------
# Credential injection / cleanup (same pattern as LangChain)
# ---------------------------------------------------------------------------


def _inject_credentials(task: Any, execution_id: str) -> List[str]:
    """Resolve workflow-level credentials and inject into os.environ.

    Returns list of env var keys that were injected (for cleanup).
    """
    import os as _os

    from agentspan.agents.runtime._dispatch import (
        _extract_execution_token,
        _get_credential_fetcher,
        _workflow_credentials,
        _workflow_credentials_lock,
    )

    injected_keys: List[str] = []
    exec_id = execution_id or ""
    with _workflow_credentials_lock:
        cred_names = list(_workflow_credentials.get(exec_id, []))
    if cred_names:
        token = _extract_execution_token(task)
        if token:
            fetcher = _get_credential_fetcher()
            resolved = fetcher.fetch(token, cred_names)
            for k, v in resolved.items():
                if isinstance(v, str):
                    _os.environ[k] = v
                    injected_keys.append(k)
    return injected_keys


def _cleanup_credentials(injected_keys: List[str]) -> None:
    """Remove previously injected credential env vars."""
    import os as _os

    for k in injected_keys:
        _os.environ.pop(k, None)
