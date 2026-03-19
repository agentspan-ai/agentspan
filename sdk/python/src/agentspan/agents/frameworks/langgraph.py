# sdk/python/src/agentspan/agents/frameworks/langgraph.py
# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""LangGraph passthrough worker support.

Provides:
- serialize_langgraph(graph) -> (raw_config, [WorkerInfo])
- make_langgraph_worker(graph, name, server_url, auth_key, auth_secret) -> tool_worker
"""

from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Dict, List, Optional, Tuple

from agentspan.agents.frameworks.serializer import WorkerInfo

logger = logging.getLogger("agentspan.agents.frameworks.langgraph")

# Shared thread pool for non-blocking event push (process lifetime)
_EVENT_PUSH_POOL = ThreadPoolExecutor(max_workers=4, thread_name_prefix="langgraph-event-push")

_DEFAULT_NAME = "langgraph_agent"


def serialize_langgraph(graph: Any) -> Tuple[Dict[str, Any], List[WorkerInfo]]:
    """Serialize a CompiledStateGraph into (raw_config, [WorkerInfo]).

    The WorkerInfo contains a pre-wrapped tool_worker — it does NOT go through
    make_tool_worker to avoid double-wrapping.
    """
    name = getattr(graph, "name", None) or _DEFAULT_NAME
    raw_config = {"name": name, "_worker_name": name}

    # server_url/auth will be injected at registration time via closure
    # For serialization we only need the name
    worker = WorkerInfo(
        name=name,
        description=f"LangGraph passthrough worker for {name}",
        input_schema={
            "type": "object",
            "properties": {
                "prompt": {"type": "string"},
                "session_id": {"type": "string"},
            },
        },
        func=None,  # placeholder — replaced at registration time
    )
    return raw_config, [worker]


def make_langgraph_worker(
    graph: Any,
    name: str,
    server_url: str,
    auth_key: str,
    auth_secret: str,
) -> Any:
    """Build a pre-wrapped tool_worker(task) -> TaskResult for a LangGraph graph.

    The returned function has the correct signature for @worker_task registration
    and does NOT go through make_tool_worker.
    """
    from conductor.client.http.models.task import Task
    from conductor.client.http.models.task_result import TaskResult
    from conductor.client.http.models.task_result_status import TaskResultStatus

    def tool_worker(task: Task) -> TaskResult:
        workflow_id = task.workflow_instance_id
        prompt = task.input_data.get("prompt", "")
        session_id = (task.input_data.get("session_id") or "").strip()

        try:
            graph_input = _build_input(graph, prompt)
            config = {}
            if session_id:
                config = {"configurable": {"thread_id": session_id}}

            final_state = None
            for mode, chunk in graph.stream(graph_input, config, stream_mode=["updates", "values"]):
                if mode == "updates":
                    _process_updates_chunk(chunk, workflow_id, server_url, auth_key, auth_secret)
                elif mode == "values":
                    final_state = chunk

            output = _extract_output(final_state)
            return TaskResult(
                task_id=task.task_id,
                workflow_instance_id=workflow_id,
                status=TaskResultStatus.COMPLETED,
                output_data={"result": output},
            )

        except Exception as exc:
            logger.error("LangGraph worker error (workflow_id=%s): %s", workflow_id, exc)
            return TaskResult(
                task_id=task.task_id,
                workflow_instance_id=workflow_id,
                status=TaskResultStatus.FAILED,
                reason_for_incompletion=str(exc),
            )

    return tool_worker


def _build_input(graph: Any, prompt: str) -> Dict[str, Any]:
    """Auto-detect input format from graph's JSON schema."""
    try:
        schema = graph.get_input_jsonschema()
        props = schema.get("properties", {})
        if "messages" in props:
            from langchain_core.messages import HumanMessage

            return {"messages": [HumanMessage(content=prompt)]}
        # Find first required string property
        required = schema.get("required", list(props.keys()))
        for key in required:
            prop = props.get(key, {})
            if prop.get("type") == "string":
                return {key: prompt}
    except Exception:
        pass
    return {"prompt": prompt}


def _process_updates_chunk(
    chunk: Dict[str, Any],
    workflow_id: str,
    server_url: str,
    auth_key: str,
    auth_secret: str,
) -> None:
    """Map a LangGraph 'updates' chunk to Agentspan SSE events and push non-blocking."""
    for node_name, state_updates in chunk.items():
        # Always emit a thinking event for each node execution
        _push_event_nonblocking(
            workflow_id,
            {"type": "thinking", "content": node_name},
            server_url,
            auth_key,
            auth_secret,
        )

        # Check for tool calls and tool results in messages
        messages = state_updates.get("messages", []) if isinstance(state_updates, dict) else []
        for msg in messages if isinstance(messages, list) else []:
            _emit_message_events(msg, workflow_id, server_url, auth_key, auth_secret)


def _emit_message_events(
    msg: Any,
    workflow_id: str,
    server_url: str,
    auth_key: str,
    auth_secret: str,
) -> None:
    """Emit tool_call / tool_result events from a LangChain message object or dict."""
    # Handle both dict-style (from stream) and object-style messages
    msg_type = getattr(msg, "type", None) or (msg.get("type") if isinstance(msg, dict) else None)
    if msg_type == "tool":
        # ToolMessage = tool result
        name = getattr(msg, "name", None) or (msg.get("name", "") if isinstance(msg, dict) else "")
        content = getattr(msg, "content", "") or (
            msg.get("content", "") if isinstance(msg, dict) else ""
        )
        _push_event_nonblocking(
            workflow_id,
            {"type": "tool_result", "toolName": name, "result": str(content)},
            server_url,
            auth_key,
            auth_secret,
        )
    elif msg_type == "ai":
        # AIMessage — check for tool calls
        tool_calls = getattr(msg, "tool_calls", None) or (
            msg.get("tool_calls", []) if isinstance(msg, dict) else []
        )
        for tc in tool_calls or []:
            tc_name = getattr(tc, "name", None) or (
                tc.get("name", "") if isinstance(tc, dict) else ""
            )
            tc_args = getattr(tc, "args", {}) or (
                tc.get("args", {}) if isinstance(tc, dict) else {}
            )
            _push_event_nonblocking(
                workflow_id,
                {"type": "tool_call", "toolName": tc_name, "args": tc_args},
                server_url,
                auth_key,
                auth_secret,
            )


def _extract_output(final_state: Optional[Dict[str, Any]]) -> str:
    """Extract the agent's final text output from the accumulated state."""
    if final_state is None:
        return ""
    messages = final_state.get("messages", [])
    # Walk in reverse to find the last AIMessage with content and no tool calls
    for msg in reversed(messages):
        msg_type = getattr(msg, "type", None) or (
            msg.get("type") if isinstance(msg, dict) else None
        )
        if msg_type == "ai":
            content = getattr(msg, "content", "") or (
                msg.get("content", "") if isinstance(msg, dict) else ""
            )
            tool_calls = getattr(msg, "tool_calls", []) or (
                msg.get("tool_calls", []) if isinstance(msg, dict) else []
            )
            if content and not tool_calls:
                return str(content)
    # No messages key — serialize the whole state
    if "messages" not in final_state:
        import json

        try:
            return json.dumps(final_state)
        except Exception:
            return str(final_state)
    return ""


def _push_event_nonblocking(
    workflow_id: str,
    event: Dict[str, Any],
    server_url: str,
    auth_key: str,
    auth_secret: str,
) -> None:
    """Fire-and-forget HTTP POST to {server_url}/agent/events/{workflowId}."""

    def _do_push():
        try:
            import requests

            url = f"{server_url}/agent/events/{workflow_id}"
            headers = {}
            if auth_key:
                headers["X-Auth-Key"] = auth_key
            if auth_secret:
                headers["X-Auth-Secret"] = auth_secret
            requests.post(url, json=event, headers=headers, timeout=5)
        except Exception as exc:
            logger.debug("Event push failed (workflow_id=%s): %s", workflow_id, exc)

    _EVENT_PUSH_POOL.submit(_do_push)
