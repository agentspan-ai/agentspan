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
            "_active_subagents": [],     # stack of {"ref_name", "sub_exec_id", "tool_use_id"}
            "_tool_target_exec": {},     # tool_use_id -> execution_id it was injected into
            "_pending_agent_calls": [],  # FIFO queue of deferred Agent tool PreToolUse data
            "_agent_tool_map": {},       # tool_use_id -> {"ref_name", "sub_exec_id", "agent_id"}
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
            now_ms = int(time.time() * 1000)
            truncated_input = _truncate_dict_values(tool_input, _TOOL_OUTPUT_MAX_CHARS)
            entry = {
                "tool_name": tool_name,
                "args": truncated_input,
                "status": "running",
                "start_time": now_ms,
                "end_time": 0,
                "duration_ms": 0,
                "stdout": "",
                "stderr": "",
            }
            metadata["tools_used"].append(entry)
            if tool_use_id:
                metadata["_tool_use_index"][tool_use_id] = len(metadata["tools_used"]) - 1

            # Agent tool spawns a subagent — defer injection to SubagentStart
            # so we produce a single SUB_WORKFLOW task instead of SIMPLE + SUB_WORKFLOW.
            if tool_name == "Agent" and tool_use_id:
                metadata["_pending_agent_calls"].append({
                    "tool_use_id": tool_use_id,
                    "tool_input": truncated_input,
                    "start_time": now_ms,
                })
                _push_event_nonblocking(
                    execution_id,
                    {"type": "tool_call", "toolName": tool_name, "toolUseId": tool_use_id},
                    server_url, auth_key, auth_secret,
                )
                return {}

            # If a subagent is active, inject into the sub-workflow instead
            active_sub = metadata["_active_subagents"]
            target_exec = execution_id
            if active_sub and active_sub[-1].get("sub_exec_id"):
                target_exec = active_sub[-1]["sub_exec_id"]

            _push_event_nonblocking(
                target_exec,
                {"type": "tool_call", "toolName": tool_name, "toolUseId": tool_use_id},
                server_url,
                auth_key,
                auth_secret,
            )

            # Inject a display task into the workflow DAG (awaited so it
            # exists before the tool actually runs)
            if tool_use_id:
                metadata["_tool_target_exec"][tool_use_id] = target_exec
                loop = asyncio.get_event_loop()
                await loop.run_in_executor(
                    _EVENT_PUSH_POOL,
                    _inject_tool_task,
                    target_exec, tool_name, tool_use_id,
                    truncated_input, server_url, auth_key, auth_secret,
                )
        except Exception as exc:
            logger.debug("PreToolUse hook error: %s", exc)
        return {}

    # -- PostToolUse hook: push tool result events + throttled task progress --
    async def _post_tool_use(input_data: dict, tool_use_id: str | None, context: Any) -> dict:
        try:
            tool_name = input_data.get("tool_name", "")
            raw_response = input_data.get("tool_response") or input_data.get("tool_output", "")
            tool_output = str(raw_response)[:_TOOL_OUTPUT_MAX_CHARS] if raw_response else ""
            metadata["last_tool_output"] = tool_output

            # Update the matching entry with success result
            now_ms = int(time.time() * 1000)
            duration_ms = 0
            idx = metadata["_tool_use_index"].get(tool_use_id)
            if idx is not None and idx < len(metadata["tools_used"]):
                entry = metadata["tools_used"][idx]
                entry["status"] = "success"
                entry["stdout"] = tool_output
                entry["end_time"] = now_ms
                entry["duration_ms"] = now_ms - entry["start_time"]
                duration_ms = entry["duration_ms"]

            # Agent tool → complete the consolidated SUB_WORKFLOW task + tracking workflow
            agent_info = metadata["_agent_tool_map"].get(tool_use_id) if tool_use_id else None
            if agent_info:
                ref_name = agent_info["ref_name"]
                sub_exec_id = agent_info["sub_exec_id"]
                output_payload: Dict[str, Any] = {"duration_ms": duration_ms}
                if sub_exec_id:
                    output_payload["subWorkflowId"] = sub_exec_id
                if isinstance(raw_response, dict):
                    output_payload["tool_response"] = raw_response
                elif tool_output:
                    output_payload["result"] = tool_output
                _complete_tool_task_nonblocking(
                    execution_id, ref_name, "COMPLETED",
                    output_payload, server_url, auth_key, auth_secret,
                )
                if sub_exec_id:
                    wf_output = {"result": tool_output} if tool_output else {}
                    _complete_workflow_nonblocking(
                        sub_exec_id, server_url, auth_key, auth_secret,
                        output_data=wf_output,
                    )

                _push_event_nonblocking(
                    execution_id,
                    {"type": "tool_result", "toolName": tool_name, "toolUseId": tool_use_id},
                    server_url, auth_key, auth_secret,
                )
            else:
                # Regular tool — use the target execution from PreToolUse
                target_exec = metadata["_tool_target_exec"].get(tool_use_id, execution_id)

                _push_event_nonblocking(
                    target_exec,
                    {"type": "tool_result", "toolName": tool_name, "toolUseId": tool_use_id},
                    server_url, auth_key, auth_secret,
                )

                # Complete the injected DAG task
                if tool_use_id:
                    output_payload2: Dict[str, Any] = {"duration_ms": duration_ms}
                    if isinstance(raw_response, dict):
                        output_payload2["tool_response"] = raw_response
                    else:
                        output_payload2["stdout"] = tool_output
                    _complete_tool_task_nonblocking(
                        target_exec, tool_use_id, "COMPLETED",
                        output_payload2, server_url, auth_key, auth_secret,
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
            now_ms = int(time.time() * 1000)
            duration_ms = 0
            idx = metadata["_tool_use_index"].get(tool_use_id)
            if idx is not None and idx < len(metadata["tools_used"]):
                entry = metadata["tools_used"][idx]
                entry["status"] = "error"
                entry["stderr"] = error_msg
                entry["end_time"] = now_ms
                entry["duration_ms"] = now_ms - entry["start_time"]
                duration_ms = entry["duration_ms"]

            # Agent tool failure → fail the consolidated SUB_WORKFLOW task
            agent_info = metadata["_agent_tool_map"].get(tool_use_id) if tool_use_id else None
            if agent_info:
                ref_name = agent_info["ref_name"]
                sub_exec_id = agent_info["sub_exec_id"]
                _complete_tool_task_nonblocking(
                    execution_id, ref_name, "FAILED",
                    {"stderr": error_msg, "duration_ms": duration_ms},
                    server_url, auth_key, auth_secret,
                )
                if sub_exec_id:
                    _complete_workflow_nonblocking(
                        sub_exec_id, server_url, auth_key, auth_secret,
                        output_data={"error": error_msg},
                    )
                _push_event_nonblocking(
                    execution_id,
                    {"type": "tool_error", "toolName": tool_name, "toolUseId": tool_use_id},
                    server_url, auth_key, auth_secret,
                )
            else:
                # Regular tool failure
                target_exec = metadata["_tool_target_exec"].get(tool_use_id, execution_id)

                _push_event_nonblocking(
                    target_exec,
                    {"type": "tool_error", "toolName": tool_name, "toolUseId": tool_use_id},
                    server_url, auth_key, auth_secret,
                )

                if tool_use_id:
                    _complete_tool_task_nonblocking(
                        target_exec, tool_use_id, "FAILED",
                        {"stderr": error_msg, "duration_ms": duration_ms},
                        server_url, auth_key, auth_secret,
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

    # -- SubagentStart hook: inject a single SUB_WORKFLOW task for the subagent --
    async def _subagent_start(input_data: dict, tool_use_id: str | None, context: Any) -> dict:
        try:
            agent_id = input_data.get("agent_id", "")
            agent_name = input_data.get("agent_name", "") or input_data.get("agent_type", "") or "subagent"
            metadata["subagent_count"] += 1

            # Pop the deferred Agent tool call (PreToolUse fires before SubagentStart)
            pending = metadata["_pending_agent_calls"]
            agent_call = pending.pop(0) if pending else None
            # Use the Agent tool's tool_use_id as ref_name so we produce one task
            ref_name = (agent_call["tool_use_id"] if agent_call else None) or agent_id or f"subagent_{metadata['subagent_count'] - 1}"
            # The actual prompt/args the user gave the subagent
            agent_input = agent_call["tool_input"] if agent_call else {}

            _push_event_nonblocking(
                execution_id,
                {"type": "subagent_start", "agentId": agent_id},
                server_url, auth_key, auth_secret,
            )

            # Create a tracking sub-workflow and inject as SUB_WORKFLOW task
            loop = asyncio.get_event_loop()
            workflow_name = f"Agent({agent_name})"
            sub_exec_id = await loop.run_in_executor(
                _EVENT_PUSH_POOL,
                lambda: _create_tracking_workflow(
                    workflow_name, agent_input,
                    server_url, auth_key, auth_secret,
                    parent_workflow_id=execution_id,
                ),
            )
            sub_wf_param = None
            if sub_exec_id:
                sub_wf_param = {
                    "name": workflow_name,
                    "version": 1,
                    "executionId": sub_exec_id,
                }
                # Push onto active subagent stack so subsequent tool calls
                # get injected into the sub-workflow
                metadata["_active_subagents"].append({
                    "ref_name": ref_name,
                    "sub_exec_id": sub_exec_id,
                    "tool_use_id": agent_call["tool_use_id"] if agent_call else None,
                })
                # Map the Agent tool's tool_use_id for PostToolUse completion
                if agent_call:
                    metadata["_agent_tool_map"][agent_call["tool_use_id"]] = {
                        "ref_name": ref_name,
                        "sub_exec_id": sub_exec_id,
                        "agent_id": agent_id,
                    }

            # Store sub_exec_id on the tools_used entry created by PreToolUse
            if agent_call:
                idx = metadata["_tool_use_index"].get(agent_call["tool_use_id"])
                if idx is not None and idx < len(metadata["tools_used"]):
                    metadata["tools_used"][idx]["_sub_exec_id"] = sub_exec_id
                    metadata["tools_used"][idx]["tool_name"] = workflow_name

            await loop.run_in_executor(
                _EVENT_PUSH_POOL,
                lambda: _inject_tool_task(
                    execution_id, workflow_name, ref_name,
                    agent_input, server_url, auth_key, auth_secret,
                    task_type="SUB_WORKFLOW",
                    sub_workflow_param=sub_wf_param,
                ),
            )
        except Exception as exc:
            logger.debug("SubagentStart hook error: %s", exc)
        return {}

    # -- SubagentStop hook: pop the active stack (completion deferred to PostToolUse) --
    async def _subagent_stop(input_data: dict, tool_use_id: str | None, context: Any) -> dict:
        try:
            agent_id = input_data.get("agent_id", "")

            _push_event_nonblocking(
                execution_id,
                {"type": "subagent_stop", "agentId": agent_id},
                server_url, auth_key, auth_secret,
            )

            # Pop the subagent from the active stack so subsequent tool calls
            # go back to the parent (or outer subagent).
            active_sub = metadata["_active_subagents"]
            if active_sub:
                active_sub.pop()
        except Exception as exc:
            logger.debug("SubagentStop hook error: %s", exc)
        return {}

    # -- Notification hook: inject an info task --
    async def _notification(input_data: dict, tool_use_id: str | None, context: Any) -> dict:
        try:
            message = input_data.get("message", "")
            ref_name = f"notification_{int(time.time() * 1000)}"
            _push_event_nonblocking(
                execution_id,
                {"type": "notification", "message": message},
                server_url,
                auth_key,
                auth_secret,
            )
            # Inject and immediately complete a notification task
            loop = asyncio.get_event_loop()
            injected = await loop.run_in_executor(
                _EVENT_PUSH_POOL,
                _inject_tool_task,
                execution_id, "Notification", ref_name,
                {"message": str(message)[:_TOOL_OUTPUT_MAX_CHARS]},
                server_url, auth_key, auth_secret,
            )
            if injected:
                _complete_tool_task_nonblocking(
                    execution_id, ref_name, "COMPLETED",
                    {"message": str(message)[:_TOOL_OUTPUT_MAX_CHARS]},
                    server_url, auth_key, auth_secret,
                )
        except Exception as exc:
            logger.debug("Notification hook error: %s", exc)
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
        "SubagentStart": [SdkHookMatcher(hooks=[_subagent_start])],
        "SubagentStop": [SdkHookMatcher(hooks=[_subagent_stop])],
        "Notification": [SdkHookMatcher(hooks=[_notification])],
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
# DAG task injection (display tasks for each tool call)
# ---------------------------------------------------------------------------


def _create_tracking_workflow(
    workflow_name: str,
    input_data: Dict[str, Any],
    server_url: str,
    auth_key: str,
    auth_secret: str,
    parent_workflow_id: str | None = None,
    parent_workflow_task_id: str | None = None,
) -> str | None:
    """Create a bare tracking workflow for a subagent.

    Returns the execution ID of the new workflow, or None on failure.
    Uses POST /api/agent/execution (Agentspan custom endpoint).
    """
    try:
        import requests

        url = f"{server_url}/agent/execution"
        headers: Dict[str, str] = {"Content-Type": "application/json"}
        if auth_key:
            headers["X-Auth-Key"] = auth_key
        if auth_secret:
            headers["X-Auth-Secret"] = auth_secret
        body: Dict[str, Any] = {"workflowName": workflow_name, "input": input_data}
        if parent_workflow_id:
            body["parentWorkflowId"] = parent_workflow_id
        if parent_workflow_task_id:
            body["parentWorkflowTaskId"] = parent_workflow_task_id
        resp = requests.post(url, json=body, headers=headers, timeout=5)
        if resp.status_code < 400:
            return resp.json().get("executionId")
        return None
    except Exception as exc:
        logger.debug("Create tracking workflow failed: %s", exc)
        return None


def _inject_tool_task(
    execution_id: str,
    tool_name: str,
    ref_name: str,
    input_data: Dict[str, Any],
    server_url: str,
    auth_key: str,
    auth_secret: str,
    task_type: str = "SIMPLE",
    sub_workflow_param: Dict[str, Any] | None = None,
) -> bool:
    """Inject a display-only task into the running workflow execution.

    Called synchronously from PreToolUse so the task exists before the tool runs.
    Uses POST /api/agent/{executionId}/tasks (Agentspan custom endpoint).

    For SUB_WORKFLOW tasks, pass sub_workflow_param with keys:
      name, version, executionId (the tracking sub-workflow).
    """
    try:
        import requests

        url = f"{server_url}/agent/{execution_id}/tasks"
        headers: Dict[str, str] = {"Content-Type": "application/json"}
        if auth_key:
            headers["X-Auth-Key"] = auth_key
        if auth_secret:
            headers["X-Auth-Secret"] = auth_secret
        body: Dict[str, Any] = {
            "taskDefName": tool_name,
            "referenceTaskName": ref_name,
            "type": task_type,
            "inputData": input_data,
        }
        if sub_workflow_param:
            body["subWorkflowParam"] = sub_workflow_param
        resp = requests.post(url, json=body, headers=headers, timeout=5)
        return resp.status_code < 400
    except Exception as exc:
        logger.debug(
            "Inject tool task failed (execution_id=%s, ref=%s): %s",
            execution_id, ref_name, exc,
        )
        return False


def _complete_tool_task_nonblocking(
    execution_id: str,
    ref_name: str,
    status: str,
    output_data: Dict[str, Any],
    server_url: str,
    auth_key: str,
    auth_secret: str,
) -> None:
    """Fire-and-forget update of an injected task's status.

    Uses POST /api/agent/tasks/{executionId}/{refTaskName}/{status}.
    """

    def _do_complete():
        try:
            import requests

            url = f"{server_url}/agent/tasks/{execution_id}/{ref_name}/{status}"
            headers: Dict[str, str] = {"Content-Type": "application/json"}
            if auth_key:
                headers["X-Auth-Key"] = auth_key
            if auth_secret:
                headers["X-Auth-Secret"] = auth_secret
            requests.post(url, json=output_data, headers=headers, timeout=5)
        except Exception as exc:
            logger.debug(
                "Complete tool task failed (execution_id=%s, ref=%s): %s",
                execution_id, ref_name, exc,
            )

    _EVENT_PUSH_POOL.submit(_do_complete)


def _complete_workflow_nonblocking(
    workflow_execution_id: str,
    server_url: str,
    auth_key: str,
    auth_secret: str,
    output_data: Dict[str, Any] | None = None,
) -> None:
    """Fire-and-forget: mark a tracking sub-workflow as COMPLETED.

    Uses POST /api/agent/execution/{executionId}/complete.
    """

    def _do_complete():
        try:
            import requests

            url = f"{server_url}/agent/execution/{workflow_execution_id}/complete"
            headers: Dict[str, str] = {"Content-Type": "application/json"}
            if auth_key:
                headers["X-Auth-Key"] = auth_key
            if auth_secret:
                headers["X-Auth-Secret"] = auth_secret
            requests.post(url, json=output_data or {}, headers=headers, timeout=5)
        except Exception as exc:
            logger.debug(
                "Complete workflow failed (execution_id=%s): %s",
                workflow_execution_id, exc,
            )

    _EVENT_PUSH_POOL.submit(_do_complete)



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
