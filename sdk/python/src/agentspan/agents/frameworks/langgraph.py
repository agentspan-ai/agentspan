# sdk/python/src/agentspan/agents/frameworks/langgraph.py
# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""LangGraph worker support.

Two serialization paths:

1. **Full extraction** (preferred) — when the graph was built via
   ``agentspan.agents.langchain.create_agent()``.  The LLM model, tools, and
   instructions are extracted and sent to the server so that the LLM call runs
   server-side (AI_MODEL task) and each tool runs as a separate SIMPLE task —
   identical to the OpenAI/ADK integration pattern.

2. **Passthrough** (fallback) — for hand-built ``StateGraph`` objects whose
   internal structure cannot be inspected.  The entire graph executes in a
   single Python worker task.

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


# ── Public serializer ──────────────────────────────────────────────────────────

def serialize_langgraph(graph: Any) -> Tuple[Dict[str, Any], List[WorkerInfo]]:
    """Serialize a CompiledStateGraph into (raw_config, [WorkerInfo]).

    If the graph carries ``._agentspan_meta`` (set by
    ``agentspan.agents.langchain.create_agent``), performs full extraction:
    the LLM model/instructions/tools are included in ``raw_config`` so the
    server can build a proper AI_MODEL + SIMPLE-task workflow.

    Otherwise falls back to the passthrough pattern (single opaque worker).
    """
    meta = getattr(graph, "_agentspan_meta", None)
    if meta is not None:
        return _serialize_full(graph, meta)
    return _serialize_passthrough(graph)


# ── Full-extraction path ───────────────────────────────────────────────────────

def _serialize_full(
    graph: Any,
    meta: Dict[str, Any],
) -> Tuple[Dict[str, Any], List[WorkerInfo]]:
    """Extract model + tools and build an OpenAI-compatible rawConfig."""
    name = getattr(graph, "name", None) or _DEFAULT_NAME
    llm = meta.get("llm")
    lc_tools = meta.get("tools") or []
    instructions = meta.get("instructions")

    raw_config: Dict[str, Any] = {
        "name": name,
        "model": _get_model_string(llm),
    }
    if getattr(llm, "temperature", None) is not None:
        raw_config["temperature"] = llm.temperature
    if instructions:
        raw_config["instructions"] = instructions

    tool_refs: List[Dict[str, Any]] = []
    workers: List[WorkerInfo] = []
    for t in lc_tools:
        tool_name, description, schema, func = _extract_tool_parts(t)
        tool_refs.append({
            "_worker_ref": tool_name,
            "description": description,
            "parameters": schema,
        })
        workers.append(WorkerInfo(
            name=tool_name,
            description=description,
            input_schema=schema,
            func=func,
        ))

    if tool_refs:
        raw_config["tools"] = tool_refs

    logger.debug(
        "Full extraction for '%s': model=%s tools=%s",
        name, raw_config.get("model"), [w.name for w in workers],
    )
    return raw_config, workers


def _get_model_string(llm: Any) -> str:
    """Return 'provider/model' string from a LangChain chat model instance."""
    if llm is None:
        return "openai/gpt-4o-mini"
    cls = type(llm).__name__
    model = (
        getattr(llm, "model_name", None)
        or getattr(llm, "model", None)
        or "gpt-4o-mini"
    )
    if "OpenAI" in cls:
        return f"openai/{model}"
    if "Anthropic" in cls:
        return f"anthropic/{model}"
    if "Google" in cls or "Gemini" in cls or "VertexAI" in cls:
        return f"google_gemini/{model}"
    if "Bedrock" in cls:
        return f"bedrock/{model}"
    if "Cohere" in cls:
        return f"cohere/{model}"
    # Unknown — pass as-is (server will try to resolve)
    return str(model)


def _extract_tool_parts(tool: Any) -> Tuple[str, str, Dict[str, Any], Any]:
    """Return (name, description, json_schema, callable) for a LangChain tool."""
    tool_name = getattr(tool, "name", None)
    func = getattr(tool, "func", None) or tool  # @tool stores original fn in .func
    if tool_name is None:
        tool_name = getattr(func, "__name__", "unknown_tool")
    description = getattr(tool, "description", "") or ""

    # Extract JSON schema from the tool's args_schema (Pydantic model)
    schema: Dict[str, Any] = {"type": "object", "properties": {}}
    try:
        args_schema = getattr(tool, "args_schema", None)
        if args_schema is not None:
            js = args_schema.model_json_schema()
            schema = {
                "type": "object",
                "properties": js.get("properties", {}),
            }
            if "required" in js:
                schema["required"] = js["required"]
        else:
            # Fallback: derive from function signature
            import inspect
            sig = inspect.signature(func)
            props: Dict[str, Any] = {}
            required = []
            for pname, param in sig.parameters.items():
                props[pname] = {"type": "string"}
                if param.default is inspect.Parameter.empty:
                    required.append(pname)
            schema = {"type": "object", "properties": props}
            if required:
                schema["required"] = required
    except Exception as exc:
        logger.debug("Could not extract schema for tool '%s': %s", tool_name, exc)

    return tool_name, description, schema, func


# ── Passthrough path ───────────────────────────────────────────────────────────

def _serialize_passthrough(graph: Any) -> Tuple[Dict[str, Any], List[WorkerInfo]]:
    """Fallback: wrap the entire graph as a single opaque SIMPLE worker."""
    name = getattr(graph, "name", None) or _DEFAULT_NAME
    raw_config = {"name": name, "_worker_name": name}

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
        func=None,  # placeholder — filled by runtime._build_passthrough_func()
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
