# sdk/python/src/agentspan/agents/frameworks/langgraph.py
# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""LangGraph worker support — full extraction and passthrough.

Provides:
- serialize_langgraph(graph) -> (raw_config, [WorkerInfo])
- make_langgraph_worker(graph, name, server_url, auth_key, auth_secret) -> tool_worker

Full extraction: when the graph's LLM model and tools can be identified, the
serializer returns them so the server compiles a proper multi-task workflow
(AI_MODEL + SIMPLE per tool).  Falls back to passthrough (single SIMPLE task)
when extraction is not possible.
"""

from __future__ import annotations

import inspect
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

    Tries full extraction first (model + tools → proper workflow).
    Falls back to passthrough (single SIMPLE task) when extraction fails.
    """
    name = getattr(graph, "name", None) or _DEFAULT_NAME

    # Try full extraction: find model and tools in the compiled graph
    model_str = _find_model_in_graph(graph)
    tool_objs = _find_tools_in_graph(graph)

    if model_str and tool_objs:
        logger.info(
            "LangGraph '%s': full extraction — model=%s, %d tools",
            name,
            model_str,
            len(tool_objs),
        )
        return _serialize_full_extraction(name, model_str, tool_objs)

    # Passthrough: entire graph runs in a single SIMPLE task
    logger.info("LangGraph '%s': passthrough (model=%s, tools=%d)", name, model_str, len(tool_objs))
    raw_config: Dict[str, Any] = {"name": name, "_worker_name": name}
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


def _serialize_full_extraction(
    name: str, model_str: str, tool_objs: List[Any]
) -> Tuple[Dict[str, Any], List[WorkerInfo]]:
    """Build raw_config with model+tools and WorkerInfo per tool."""
    raw_config: Dict[str, Any] = {"name": name, "model": model_str}
    tool_dicts: List[Dict[str, Any]] = []
    workers: List[WorkerInfo] = []

    for tool_obj in tool_objs:
        tool_name = getattr(tool_obj, "name", "") or ""
        description = getattr(tool_obj, "description", "") or ""
        schema = _get_tool_schema(tool_obj)

        tool_dicts.append(
            {"_worker_ref": tool_name, "description": description, "parameters": schema}
        )

        func = _get_tool_callable(tool_obj)
        if func is not None:
            workers.append(
                WorkerInfo(
                    name=tool_name,
                    description=description.strip().split("\n")[0] if description else "",
                    input_schema=schema,
                    func=func,
                )
            )

    raw_config["tools"] = tool_dicts
    return raw_config, workers


# ── Graph introspection helpers ──────────────────────────────────────


def _find_tools_in_graph(graph: Any) -> List[Any]:
    """Find tool objects from a ToolNode inside the compiled graph."""
    nodes = getattr(graph, "nodes", None)
    if not nodes or not isinstance(nodes, dict):
        return []
    for node in nodes.values():
        tools = _search_for_tools(node, depth=3)
        if tools:
            return tools
    return []


def _search_for_tools(obj: Any, depth: int = 3) -> List[Any]:
    if depth <= 0:
        return []
    tools_by_name = getattr(obj, "tools_by_name", None)
    if tools_by_name and isinstance(tools_by_name, dict):
        return list(tools_by_name.values())
    for attr in ("bound", "runnable", "func"):
        child = getattr(obj, attr, None)
        if child is not None and child is not obj:
            result = _search_for_tools(child, depth - 1)
            if result:
                return result
    return []


def _find_model_in_graph(graph: Any) -> Optional[str]:
    """Find the LLM model string ('provider/model') from graph nodes."""
    nodes = getattr(graph, "nodes", None)
    if not nodes or not isinstance(nodes, dict):
        return None
    for node in nodes.values():
        model = _search_for_model(node, depth=5)
        if model:
            return model
    return None


def _search_for_model(obj: Any, depth: int = 5) -> Optional[str]:
    if depth <= 0:
        return None
    result = _try_get_model_string(obj)
    if result:
        return result
    for attr in ("bound", "first", "last", "runnable", "func"):
        child = getattr(obj, attr, None)
        if child is not None and child is not obj:
            found = _search_for_model(child, depth - 1)
            if found:
                return found
    middle = getattr(obj, "middle", None)
    if isinstance(middle, list):
        for child in middle:
            found = _search_for_model(child, depth - 1)
            if found:
                return found
    steps = getattr(obj, "steps", None)
    if isinstance(steps, dict):
        for child in steps.values():
            found = _search_for_model(child, depth - 1)
            if found:
                return found
    # Search inside closures of callable objects (LangGraph wraps the LLM in closures)
    func_obj = getattr(obj, "func", None) or getattr(obj, "afunc", None)
    if func_obj is not None and hasattr(func_obj, "__closure__") and func_obj.__closure__:
        for cell in func_obj.__closure__:
            try:
                val = cell.cell_contents
            except ValueError:
                continue
            if val is obj or val is func_obj:
                continue
            found = _search_for_model(val, depth - 1)
            if found:
                return found
    return None


def _try_get_model_string(obj: Any) -> Optional[str]:
    """Extract 'provider/model' from an LLM-like object."""
    cls_name = type(obj).__name__
    model_name = getattr(obj, "model_name", None) or getattr(obj, "model", None)
    if not model_name or not isinstance(model_name, str):
        return None
    if model_name.startswith("<") or model_name.startswith("(") or len(model_name) > 100:
        return None
    if "/" in model_name:
        return model_name
    provider = _infer_provider(cls_name, model_name)
    return f"{provider}/{model_name}" if provider else model_name


def _infer_provider(cls_name: str, model_name: str) -> Optional[str]:
    if "OpenAI" in cls_name or "openai" in cls_name:
        return "openai"
    if "Anthropic" in cls_name or "anthropic" in cls_name:
        return "anthropic"
    if "Google" in cls_name or "google" in cls_name:
        return "google"
    if "Bedrock" in cls_name:
        return "bedrock"
    if model_name.startswith("gpt-") or model_name.startswith(("o1", "o3", "o4")):
        return "openai"
    if "claude" in model_name:
        return "anthropic"
    if "gemini" in model_name:
        return "google"
    return None


def _get_tool_schema(tool_obj: Any) -> Dict[str, Any]:
    """Extract JSON schema from a LangChain BaseTool."""
    if hasattr(tool_obj, "args_schema") and tool_obj.args_schema is not None:
        try:
            return tool_obj.args_schema.model_json_schema()
        except Exception:
            pass
    if hasattr(tool_obj, "get_input_schema"):
        try:
            return tool_obj.get_input_schema().model_json_schema()
        except Exception:
            pass
    return {"type": "object", "properties": {}}


def _get_tool_callable(tool_obj: Any) -> Any:
    """Get the underlying callable from a LangChain tool."""
    func = getattr(tool_obj, "func", None)
    if func and callable(func):
        return func
    run = getattr(tool_obj, "_run", None)
    if run and callable(run):
        return run
    if callable(tool_obj):
        try:
            inspect.signature(tool_obj)
            return tool_obj
        except (ValueError, TypeError):
            pass
    return None


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
