# sdk/python/src/agentspan/agents/frameworks/langgraph.py
# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""LangGraph worker support.

Three serialization paths (in priority order):

1. **Full extraction via _agentspan_meta** — graph built with
   ``agentspan.agents.langchain.create_agent()``.  LLM + tools extracted
   from the attached metadata; server builds AI_MODEL + SIMPLE tasks.

2. **create_react_agent extraction** — graph built with
   ``langgraph.prebuilt.create_react_agent()``.  LLM + tools are
   introspected from the compiled "agent"/"tools" node structure;
   server builds the same AI_MODEL + SIMPLE tasks workflow.

3. **Passthrough** (fallback) — for hand-built ``StateGraph`` objects whose
   internal structure cannot be reliably inspected.  The entire graph
   executes in a single Python worker task.

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

    Three paths (in priority order):

    1. **Full extraction via _agentspan_meta** — graph built with
       ``agentspan.agents.langchain.create_agent()``.
    2. **create_react_agent extraction** — graph built with
       ``langgraph.prebuilt.create_react_agent()``. LLM + tools are
       introspected from the compiled node structure and sent to the server
       so execution runs as AI_MODEL + SIMPLE tasks.
    3. **Passthrough** — any other CompiledStateGraph whose internals cannot
       be reliably inspected. The entire graph executes inside a single
       opaque SIMPLE worker task.
    """
    meta = getattr(graph, "_agentspan_meta", None)
    if meta is not None:
        return _serialize_full(graph, meta)

    # Try to introspect a create_react_agent graph
    extracted = _try_extract_react_agent(graph)
    if extracted is not None:
        return extracted

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
        # Sub-agent: another create_agent() graph — compile as AgentTool (SUB_WORKFLOW)
        sub_graph = getattr(t, "_agentspan_sub_graph", None)
        if sub_graph is not None and hasattr(sub_graph, "_agentspan_meta"):
            sub_raw, sub_workers = _serialize_full(sub_graph, sub_graph._agentspan_meta)
            agent_tool_name = getattr(sub_graph, "name", None) or getattr(t, "name", "sub_agent")
            agent_tool_desc = getattr(t, "description", "") or f"Call agent: {agent_tool_name}"
            tool_refs.append({
                "_type": "AgentTool",
                "name": agent_tool_name,
                "description": agent_tool_desc,
                "agent": sub_raw,
            })
            workers.extend(sub_workers)
            continue

        # Regular tool
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
    """Return 'provider/model' string from a LangChain chat model instance.

    Handles plain models (ChatOpenAI, etc.) and RunnableBinding wrappers
    produced by llm.bind_tools() / llm.with_structured_output().
    """
    if llm is None:
        return "openai/gpt-4o-mini"
    # Unwrap RunnableBinding layers before inspecting class/attributes
    base = _unwrap_binding(llm)
    cls = type(base).__name__
    model = (
        getattr(base, "model_name", None)
        or getattr(base, "model", None)
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


# ── create_react_agent extraction ─────────────────────────────────────────────

def _try_extract_react_agent(
    graph: Any,
) -> Optional[Tuple[Dict[str, Any], List[WorkerInfo]]]:
    """Try to extract LLM + tools from a langgraph.prebuilt.create_react_agent graph.

    ``create_react_agent`` produces a CompiledStateGraph with two canonical
    nodes: ``"agent"`` (calls the LLM) and ``"tools"`` (runs a ToolNode).
    We introspect both to reconstruct the same ``raw_config`` that
    ``_serialize_full`` would produce, so the server builds a proper
    AI_MODEL + SIMPLE-task workflow.

    Returns ``None`` on any failure — caller falls back to passthrough.
    """
    try:
        nodes = getattr(graph, "nodes", None)
        if not nodes or "agent" not in nodes:
            return None

        # Extract LLM from the agent node
        llm = _extract_llm_from_node(nodes["agent"])

        # Extract tools from the tools node (may be absent for no-tool graphs)
        lc_tools: List[Any] = []
        tools_node = nodes.get("tools")
        if tools_node is not None:
            lc_tools = _extract_tools_from_node(tools_node) or []

        # Need at least an LLM to build a meaningful raw_config
        if llm is None:
            logger.debug("create_react_agent extraction: could not find LLM, using passthrough")
            return None

        # Extract system prompt from state_modifier / messages_modifier if present
        instructions = _find_instructions_from_node(nodes["agent"])

        name = getattr(graph, "name", None) or _DEFAULT_NAME
        raw_config: Dict[str, Any] = {
            "name": name,
            "model": _get_model_string(llm),
        }
        if instructions:
            raw_config["instructions"] = instructions
        base_llm = _unwrap_binding(llm)
        if getattr(base_llm, "temperature", None) is not None:
            raw_config["temperature"] = base_llm.temperature

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
            "Extracted create_react_agent '%s': model=%s tools=%s",
            name, raw_config.get("model"), [w.name for w in workers],
        )
        return raw_config, workers

    except Exception as exc:
        logger.debug("Could not extract create_react_agent structure: %s", exc)
        return None


def _unwrap_binding(obj: Any) -> Any:
    """Unwrap RunnableBinding layers to reach the underlying runnable.

    ``llm.bind_tools(...)`` and ``llm.with_structured_output(...)`` return a
    ``RunnableBinding`` whose ``.bound`` attribute holds the real model.
    We recurse up to 5 levels to handle nested bindings.
    """
    current = obj
    for _ in range(5):
        bound = getattr(current, "bound", None)
        if bound is None:
            break
        current = bound
    return current


def _get_node_runnable(node: Any) -> Any:
    """Return the actual runnable stored inside a PregelNode."""
    bound = getattr(node, "bound", None)
    return bound if bound is not None else node


def _is_chat_model_instance(obj: Any) -> bool:
    """Return True if obj is (or looks like) a LangChain BaseChatModel."""
    try:
        for cls in type(obj).__mro__:
            if cls.__name__ in ("BaseChatModel", "BaseLanguageModel"):
                return True
    except Exception:
        pass
    return False


def _extract_llm_from_node(node: Any) -> Optional[Any]:
    """Find the LangChain chat model inside an agent node.

    Handles three cases:
    - Direct model stored in the node
    - RunnableBinding wrapping a model (from llm.bind_tools)
    - RunnableLambda / plain closure whose nonlocals contain the model
    """
    runnable = _get_node_runnable(node)

    # Direct chat model
    if _is_chat_model_instance(runnable):
        return runnable

    # RunnableBinding wrapping a model
    unwrapped = _unwrap_binding(runnable)
    if _is_chat_model_instance(unwrapped):
        return runnable  # return the binding so _get_model_string can unwrap it

    # RunnableLambda / plain callable — search closure
    func = getattr(runnable, "func", None) or (runnable if callable(runnable) else None)
    if func is not None:
        return _find_llm_in_closure(func)

    return None


def _extract_tools_from_node(node: Any) -> Optional[List[Any]]:
    """Extract the tools list from a ToolNode-backed graph node."""
    runnable = _get_node_runnable(node)

    # Direct ToolNode
    tools_by_name = getattr(runnable, "tools_by_name", None)
    if isinstance(tools_by_name, dict):
        return list(tools_by_name.values())

    # RunnableLambda wrapping a ToolNode
    func = getattr(runnable, "func", None)
    if func is not None:
        tools_by_name = getattr(func, "tools_by_name", None)
        if isinstance(tools_by_name, dict):
            return list(tools_by_name.values())

    return None


def _find_llm_in_closure(func: Any) -> Optional[Any]:
    """Walk a function's closure cells to find a LangChain chat model.

    In LangGraph ≥1.0 the model is stored in a ``RunnableSequence`` (named
    ``static_model``) in the closure rather than as a direct reference.
    We use ``_find_chat_model_in_runnable`` to recurse into sequences/bindings.
    """
    import inspect
    try:
        vars_ = inspect.getclosurevars(func)
        candidates = list(vars_.nonlocals.values()) + list(vars_.globals.values())
        for var in candidates:
            found = _find_chat_model_in_runnable(var)
            if found is not None:
                return found
    except Exception:
        pass
    return None


def _find_chat_model_in_runnable(obj: Any, _depth: int = 0) -> Optional[Any]:
    """Recursively search a runnable object for an embedded LangChain chat model.

    Handles:
    - Direct ``BaseChatModel`` instance
    - ``RunnableBinding`` (e.g. from ``llm.bind_tools()``) — unwrap and recurse
    - ``RunnableSequence`` — walk ``.steps`` (LLM is usually the last step)
    """
    if obj is None or _depth > 4:
        return None

    # Direct chat model
    if _is_chat_model_instance(obj):
        return obj

    # RunnableBinding — the real model is in .bound
    unwrapped = _unwrap_binding(obj)
    if unwrapped is not obj:
        if _is_chat_model_instance(unwrapped):
            return obj  # return the binding so _get_model_string can read it too
        return _find_chat_model_in_runnable(unwrapped, _depth + 1)

    # RunnableSequence — scan steps in reverse (LLM is typically last)
    steps = getattr(obj, "steps", None)
    if steps and isinstance(steps, (list, tuple)):
        for step in reversed(steps):
            found = _find_chat_model_in_runnable(step, _depth + 1)
            if found is not None:
                return found

    return None


def _find_instructions_from_node(node: Any) -> Optional[str]:
    """Try to extract a system prompt from a create_react_agent agent node.

    ``create_react_agent`` bakes ``state_modifier`` / ``messages_modifier`` /
    ``prompt`` into the agent node closure, either as a ``SystemMessage`` or
    as a preprocessing lambda that itself holds one.  We walk up to 2 closure
    levels to find it.
    """
    runnable = _get_node_runnable(node)
    func = getattr(runnable, "func", None) or (runnable if callable(runnable) else None)
    if func is None:
        return None
    return _find_system_message_in_closures(func, max_depth=2)


def _find_system_message_in_closures(
    func: Any, max_depth: int = 2, _depth: int = 0
) -> Optional[str]:
    """Recursively walk closure cells looking for a system prompt string.

    Checks for:
    - A ``SystemMessage`` object (by class name, framework-independent)
    - A nonlocal variable named ``state_modifier``, ``messages_modifier``,
      ``system_message``, or ``prompt`` holding a plain string
    Only recurses into nonlocals (not globals) to avoid scanning entire modules.
    """
    if _depth > max_depth:
        return None
    import inspect
    try:
        vars_ = inspect.getclosurevars(func)
        all_vars = {**vars_.nonlocals, **vars_.globals}
        for name, var in all_vars.items():
            # SystemMessage from langchain_core
            if type(var).__name__ == "SystemMessage":
                content = getattr(var, "content", None)
                if isinstance(content, str) and content.strip():
                    return content.strip()
            # Known instruction variable names holding a plain string
            if (
                name in ("state_modifier", "messages_modifier", "system_message", "prompt")
                and isinstance(var, str)
            ):
                return var
        # Recurse into nonlocal callables (state_modifier lambda may hold the SystemMessage)
        for name, var in vars_.nonlocals.items():
            if callable(var) and not isinstance(var, type) and name not in ("model", "tools"):
                result = _find_system_message_in_closures(var, max_depth, _depth + 1)
                if result is not None:
                    return result
    except Exception:
        pass
    return None


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
