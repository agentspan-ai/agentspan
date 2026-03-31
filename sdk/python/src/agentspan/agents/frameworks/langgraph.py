# sdk/python/src/agentspan/agents/frameworks/langgraph.py
# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""LangGraph worker support — full extraction, graph-structure, and passthrough.

Provides:
- serialize_langgraph(graph) -> (raw_config, [WorkerInfo])
- make_langgraph_worker(graph, name, server_url, auth_key, auth_secret) -> tool_worker
- make_node_worker(node_func, node_name) -> task_worker
- make_router_worker(router_func, router_name) -> task_worker

Three serialization paths (tried in order):
1. Full extraction — model + ToolNode tools → AI_MODEL + SIMPLE per tool
2. Graph-structure — model found, custom StateGraph with nodes/edges
   → each node becomes a SIMPLE task, edges define workflow structure
3. Passthrough — fallback, entire graph in a single SIMPLE task
"""

from __future__ import annotations

import inspect
import logging
import threading
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Dict, List, Optional, Tuple

from agentspan.agents.frameworks.serializer import WorkerInfo

logger = logging.getLogger("agentspan.agents.frameworks.langgraph")

# Shared thread pool for non-blocking event push (process lifetime)
_EVENT_PUSH_POOL = ThreadPoolExecutor(max_workers=4, thread_name_prefix="langgraph-event-push")

_DEFAULT_NAME = "langgraph_agent"


def human_task(func=None, *, prompt=""):
    """Mark a LangGraph node function as requiring human input.

    When compiled, this node becomes a Conductor HUMAN task that pauses
    execution until a human provides input via the API or UI.

    The server generates the response form schema and validation pipeline
    automatically — the SDK only needs to declare intent and an optional prompt.

    Usage::

        @human_task(prompt="Review the draft and provide verdict + feedback.")
        def review_email(state):
            pass

        # Or without arguments:
        @human_task
        def review_email(state):
            pass
    """
    def decorator(f):
        f._agentspan_human_task = True
        f._agentspan_human_prompt = prompt
        return f
    if func is not None:
        return decorator(func)
    return decorator


def serialize_langgraph(graph: Any) -> Tuple[Dict[str, Any], List[WorkerInfo]]:
    """Serialize a CompiledStateGraph into (raw_config, [WorkerInfo]).

    Tries three paths in order:
    1. Full extraction (model + ToolNode tools) → AI_MODEL + SIMPLE per tool
       Also used for create_agent graphs (detected via _agentspan_meta)
    2. Graph-structure (model found, custom StateGraph) → node/edge workflow
    3. Passthrough (fallback) → single SIMPLE task
    """
    name = getattr(graph, "name", None) or _DEFAULT_NAME

    # Try full extraction: find model and tools in the compiled graph
    model_str = _find_model_in_graph(graph)
    tool_objs = _find_tools_in_graph(graph)

    if model_str and tool_objs:
        system_prompt = _extract_system_prompt_from_graph(graph)
        logger.info(
            "LangGraph '%s': full extraction — model=%s, %d tools, system_prompt=%s",
            name,
            model_str,
            len(tool_objs),
            bool(system_prompt),
        )
        return _serialize_full_extraction(name, model_str, tool_objs, instructions=system_prompt)

    # Try graph-structure: extract nodes and edges
    # Model may be None for parent graphs that only have subgraph/pure-function nodes
    result = _serialize_graph_structure(name, model_str, graph)
    if result is not None:
        return result

    # If model found but graph-structure failed (e.g. create_agent with no tools —
    # model_node(state, runtime) has 2 args so graph-structure can't extract it),
    # use full extraction as a pure LLM call with no tools.
    if model_str:
        system_prompt = _extract_system_prompt_from_graph(graph)
        logger.info(
            "LangGraph '%s': full extraction (no tools) — model=%s, system_prompt=%s",
            name,
            model_str,
            bool(system_prompt),
        )
        return _serialize_full_extraction(name, model_str, tool_objs, instructions=system_prompt)

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
    name: str, model_str: str, tool_objs: List[Any], *, instructions: Optional[str] = None
) -> Tuple[Dict[str, Any], List[WorkerInfo]]:
    """Build raw_config with model+tools and WorkerInfo per tool."""
    raw_config: Dict[str, Any] = {"name": name, "model": model_str}
    if instructions:
        raw_config["instructions"] = instructions
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


# ── Graph-structure serialization ────────────────────────────────────


def _serialize_graph_structure(
    name: str, model_str: str, graph: Any
) -> Optional[Tuple[Dict[str, Any], List[WorkerInfo]]]:
    """Serialize a custom StateGraph into a graph-structure raw_config.

    Each graph node becomes a SIMPLE task worker.  Edges and conditional
    edges are encoded so the server can build a Conductor workflow that
    mirrors the graph's flow.

    Returns None if graph structure cannot be extracted.
    """
    node_funcs = _extract_node_functions(graph)
    if not node_funcs:
        return None

    edges, conditional_edges = _extract_edges(graph)
    if not edges and not conditional_edges:
        return None

    logger.info(
        "LangGraph '%s': graph-structure — model=%s, %d nodes, %d edges, %d conditional",
        name,
        model_str,
        len(node_funcs),
        len(edges),
        len(conditional_edges),
    )

    # Build raw_config with _graph structure
    graph_nodes: List[Dict[str, Any]] = []
    workers: List[WorkerInfo] = []

    for node_name, func in node_funcs.items():
        worker_name = f"{name}_{node_name}"

        # Human node: no worker needed, compiled as Conductor HUMAN task
        if getattr(func, "_agentspan_human_task", False):
            human_prompt = getattr(func, "_agentspan_human_prompt", "")
            logger.info("Human node '%s': will compile as Conductor HUMAN task", node_name)
            graph_nodes.append({
                "name": node_name,
                "_worker_ref": worker_name,
                "_human_node": True,
                "_human_prompt": human_prompt,
            })
            # No worker registered — HUMAN is a Conductor system task
            continue

        llm_info = _find_llm_in_func(func)

        if llm_info is not None:
            # LLM node: create prep + finish workers instead of a single node worker
            llm_var_name, _llm_obj = llm_info
            prep_name = f"{worker_name}_prep"
            finish_name = f"{worker_name}_finish"
            logger.info(
                "LLM node '%s': intercepting %s.invoke() → prep/LLM_CHAT_COMPLETE/finish",
                node_name,
                llm_var_name,
            )
            graph_nodes.append({
                "name": node_name,
                "_worker_ref": worker_name,
                "_llm_node": True,
                "_llm_prep_ref": prep_name,
                "_llm_finish_ref": finish_name,
            })
            # Prep worker: captures llm.invoke() messages
            workers.append(WorkerInfo(
                name=prep_name,
                description=f"LLM prep for node '{node_name}'",
                input_schema={"type": "object", "properties": {"state": {"type": "object"}}},
                func=func,  # original func — make_llm_prep_worker wraps it at registration
                _pre_wrapped=True,
                _extra={"llm_var_name": llm_var_name, "llm_role": "prep"},
            ))
            # Finish worker: re-runs node with mock LLM response
            workers.append(WorkerInfo(
                name=finish_name,
                description=f"LLM finish for node '{node_name}'",
                input_schema={
                    "type": "object",
                    "properties": {
                        "state": {"type": "object"},
                        "llm_result": {"type": "string"},
                    },
                },
                func=func,  # original func — make_llm_finish_worker wraps it at registration
                _pre_wrapped=True,
                _extra={"llm_var_name": llm_var_name, "llm_role": "finish"},
            ))
        else:
            # Check for subgraph invocation (e.g. compiled_graph.invoke({...}))
            subgraph_info = _find_subgraph_in_func(func)
            if subgraph_info is not None:
                subgraph_var_name, subgraph_obj = subgraph_info
                prep_name = f"{worker_name}_sg_prep"
                finish_name = f"{worker_name}_sg_finish"
                logger.info(
                    "Subgraph node '%s': intercepting %s.invoke() → prep/SUB_WORKFLOW/finish",
                    node_name,
                    subgraph_var_name,
                )

                # Recursively serialize the subgraph with a unique name prefix
                sub_name = f"{name}_{node_name}"
                sub_model = _find_model_in_graph(subgraph_obj) or model_str
                sub_result = _serialize_graph_structure(sub_name, sub_model, subgraph_obj)
                if sub_result is not None:
                    sub_config, sub_workers = sub_result
                    # Mark as subgraph for compiler (affects input/output handling)
                    sub_config["_graph"]["_is_subgraph"] = True

                    graph_nodes.append({
                        "name": node_name,
                        "_worker_ref": worker_name,
                        "_subgraph_node": True,
                        "_subgraph_prep_ref": prep_name,
                        "_subgraph_finish_ref": finish_name,
                        "_subgraph_config": sub_config,
                    })
                    # Prep worker: captures subgraph.invoke() input
                    workers.append(WorkerInfo(
                        name=prep_name,
                        description=f"Subgraph prep for node '{node_name}'",
                        input_schema={"type": "object", "properties": {"state": {"type": "object"}}},
                        func=func,
                        _pre_wrapped=True,
                        _extra={"subgraph_var_name": subgraph_var_name, "subgraph_role": "prep"},
                    ))
                    # Finish worker: re-runs node with mock subgraph result
                    workers.append(WorkerInfo(
                        name=finish_name,
                        description=f"Subgraph finish for node '{node_name}'",
                        input_schema={
                            "type": "object",
                            "properties": {
                                "state": {"type": "object"},
                                "subgraph_result": {"type": "object"},
                            },
                        },
                        func=func,
                        _pre_wrapped=True,
                        _extra={"subgraph_var_name": subgraph_var_name, "subgraph_role": "finish"},
                    ))
                    # Include all subgraph workers for registration
                    workers.extend(sub_workers)
                else:
                    # Subgraph couldn't be serialized as graph-structure, fall back to regular node
                    logger.info(
                        "Subgraph node '%s': subgraph cannot be extracted, running as regular node",
                        node_name,
                    )
                    graph_nodes.append({"name": node_name, "_worker_ref": worker_name})
                    workers.append(WorkerInfo(
                        name=worker_name,
                        description=f"Graph node '{node_name}'",
                        input_schema={"type": "object", "properties": {"state": {"type": "object"}}},
                        func=func,
                        _pre_wrapped=True,
                    ))
            else:
                # Non-LLM, non-subgraph node: regular node worker
                graph_nodes.append({"name": node_name, "_worker_ref": worker_name})
                workers.append(WorkerInfo(
                    name=worker_name,
                    description=f"Graph node '{node_name}'",
                    input_schema={"type": "object", "properties": {"state": {"type": "object"}}},
                    func=func,
                    _pre_wrapped=True,
                ))

    graph_edges: List[Dict[str, str]] = []
    for src, tgt in edges:
        graph_edges.append({"source": src, "target": tgt})

    # Collect nodes that are dynamic fanout targets (need direct workers for FORK_JOIN_DYNAMIC)
    dynamic_fanout_targets: set = set()

    graph_conditional: List[Dict[str, Any]] = []
    for src, router_func, targets, is_dynamic in conditional_edges:
        router_name = f"{name}_{src}_router"
        ce_entry: Dict[str, Any] = {
            "source": src,
            "_router_ref": router_name,
            "targets": targets,
        }
        if is_dynamic:
            ce_entry["_dynamic_fanout"] = True
            # Collect target nodes for direct worker registration
            for target_node in targets.values():
                if target_node != "__end__":
                    dynamic_fanout_targets.add(target_node)
            logger.info(
                "LangGraph '%s': conditional edge from '%s' uses Send API (dynamic fan-out)",
                name, src,
            )
        graph_conditional.append(ce_entry)
        workers.append(WorkerInfo(
            name=router_name,
            description=f"Router for conditional edge from '{src}'",
            input_schema={"type": "object", "properties": {"state": {"type": "object"}}},
            func=router_func,
            _pre_wrapped=True,
            _extra={"is_dynamic_fanout": is_dynamic},
        ))

    # For dynamic fanout targets that are LLM nodes, register a direct (non-intercepted)
    # node worker under the base worker name. FORK_JOIN_DYNAMIC invokes each branch as a
    # single SIMPLE task, so it needs a worker that calls the original function directly.
    for target_node in dynamic_fanout_targets:
        func = node_funcs.get(target_node)
        if func is None:
            continue
        worker_name = f"{name}_{target_node}"
        # Check if this node already has a direct worker (non-LLM nodes do)
        existing_names = {w.name for w in workers}
        if worker_name not in existing_names:
            logger.info(
                "LangGraph '%s': registering direct worker '%s' for dynamic fanout target",
                name, worker_name,
            )
            workers.append(WorkerInfo(
                name=worker_name,
                description=f"Direct worker for dynamic fanout node '{target_node}'",
                input_schema={"type": "object", "properties": {"state": {"type": "object"}}},
                func=func,
                _pre_wrapped=True,
                _extra={"direct_node_worker": True},
            ))

    raw_config: Dict[str, Any] = {
        "name": name,
        "model": model_str,
        "_graph": {
            "nodes": graph_nodes,
            "edges": graph_edges,
            "conditional_edges": graph_conditional,
        },
    }

    # Try to extract initial state field name from input schema
    try:
        input_schema = graph.get_input_jsonschema()
        props = input_schema.get("properties", {})
        required = input_schema.get("required", list(props.keys()))
        for key in required:
            prop = props.get(key, {})
            if prop.get("type") == "string":
                raw_config["_graph"]["input_key"] = key
                break
    except Exception:
        pass

    # Extract state reducer annotations from graph channels
    # (e.g. Annotated[list, operator.add] → {"field": "add"})
    try:
        reducers: Dict[str, str] = {}
        channels = getattr(graph, "channels", {})
        for ch_name, ch_obj in channels.items():
            if ch_name.startswith("__") or ch_name.startswith("branch:"):
                continue
            if type(ch_obj).__name__ == "BinaryOperatorAggregate":
                op = getattr(ch_obj, "operator", None)
                if op is not None:
                    reducers[ch_name] = getattr(op, "__name__", str(op))
        if reducers:
            raw_config["_graph"]["_reducers"] = reducers
            logger.info("LangGraph '%s': reducers detected: %s", name, reducers)
            # Warn about unsupported custom reducers
            supported = {"add"}
            unsupported = {k: v for k, v in reducers.items() if v not in supported}
            if unsupported:
                logger.warning(
                    "LangGraph '%s': custom reducers %s are not supported server-side "
                    "(only operator.add is mapped). These fields will use last-write-wins "
                    "in FORK_JOIN merge, which may cause data loss.",
                    name,
                    unsupported,
                )
    except Exception:
        pass

    # Extract retry policies from node metadata
    try:
        retry_policies: Dict[str, Dict[str, Any]] = {}
        builder_obj = getattr(graph, "builder", None)
        if builder_obj is not None:
            node_specs = getattr(builder_obj, "_nodes", {})
            for node_name, node_spec in node_specs.items():
                retry = getattr(node_spec, "retry", None)
                if retry is not None:
                    policy: Dict[str, Any] = {}
                    if hasattr(retry, "max_attempts"):
                        policy["max_attempts"] = retry.max_attempts
                    if hasattr(retry, "initial_interval"):
                        policy["initial_interval"] = retry.initial_interval
                    if hasattr(retry, "backoff_factor"):
                        policy["backoff_factor"] = retry.backoff_factor
                    if hasattr(retry, "max_interval"):
                        policy["max_interval"] = retry.max_interval
                    if policy:
                        retry_policies[node_name] = policy
        if retry_policies:
            raw_config["_graph"]["_retry_policies"] = retry_policies
            logger.info("LangGraph '%s': retry policies: %s", name, retry_policies)
    except Exception:
        pass

    return raw_config, workers


def _extract_node_functions(graph: Any) -> Dict[str, Any]:
    """Extract {node_name: callable} from the compiled graph.

    Skips __start__ and __end__ nodes.
    """
    nodes = getattr(graph, "nodes", None)
    if not nodes or not isinstance(nodes, dict):
        return {}

    result: Dict[str, Any] = {}
    for node_name, node in nodes.items():
        if node_name in ("__start__", "__end__"):
            continue
        func = _get_node_function(node)
        if func is not None:
            result[node_name] = func
    return result


def _get_node_function(node: Any) -> Optional[Any]:
    """Get the underlying callable from a PregelNode.

    Skips functions that require more than 1 positional argument
    (e.g. ``model_node(state, runtime)`` from ``create_agent``),
    since graph-structure workers can only pass ``state``.
    """
    bound = getattr(node, "bound", None)
    if bound is None:
        return None
    func = getattr(bound, "func", None)
    if func and callable(func):
        # Skip lambda/internal functions
        func_name = getattr(func, "__name__", "")
        if func_name.startswith("<") or func_name == "<lambda>":
            return None
        # Skip functions that need more than 1 positional argument
        # (e.g. create_agent's model_node(state, runtime))
        try:
            sig = inspect.signature(func)
            required = sum(
                1
                for p in sig.parameters.values()
                if p.default is inspect.Parameter.empty
                and p.kind in (inspect.Parameter.POSITIONAL_ONLY, inspect.Parameter.POSITIONAL_OR_KEYWORD)
            )
            if required > 1:
                return None
        except (ValueError, TypeError):
            pass
        return func
    return None


def _extract_edges(
    graph: Any,
) -> Tuple[List[Tuple[str, str]], List[Tuple[str, Any, Dict[str, str], bool]]]:
    """Extract edges and conditional edges from the graph builder.

    Returns:
        (edges, conditional_edges) where:
        - edges: list of (source, target) tuples
        - conditional_edges: list of (source, router_func, {return_value: target_node}, is_dynamic_fanout)
    """
    builder = getattr(graph, "builder", None)
    if builder is None:
        return [], []

    # Simple edges from builder.edges (set of (source, target) tuples)
    edges: List[Tuple[str, str]] = []
    raw_edges = getattr(builder, "edges", set())
    for src, tgt in raw_edges:
        edges.append((src, tgt))

    # Conditional edges from builder.branches
    conditional: List[Tuple[str, Any, Dict[str, str], bool]] = []
    branches = getattr(builder, "branches", {})
    for src_node, branch_map in branches.items():
        for _branch_name, branch_spec in branch_map.items():
            # Get the routing function from the BranchSpec
            path = getattr(branch_spec, "path", None)
            if path is None:
                continue
            router_func = getattr(path, "func", None)
            if router_func is None or not callable(router_func):
                continue
            # Get target mapping: {return_value: target_node_name}
            targets = getattr(branch_spec, "ends", None)
            if not targets or not isinstance(targets, dict):
                continue
            # Detect Send API pattern (dynamic fan-out)
            is_dynamic = _is_send_router(router_func)
            conditional.append((src_node, router_func, dict(targets), is_dynamic))

    return edges, conditional


def _is_send_router(func: Any) -> bool:
    """Check if a router function likely returns Send objects (dynamic fan-out).

    Inspects the function's bytecode (co_names) for references to 'Send'.
    """
    code = getattr(func, "__code__", None)
    if code is None:
        return False
    # co_names contains global names referenced in the function bytecode
    names = getattr(code, "co_names", ())
    return "Send" in names


# ── Node/Router worker builders ─────────────────────────────────────


def _reconstitute_state(state: Dict[str, Any]) -> Dict[str, Any]:
    """Reconstitute rich objects in state that were serialized to dicts by Conductor JSON.

    Handles:
    - LangChain Document objects: dicts with ``page_content`` → Document instances
    - Dict-serialized string values: string that looks like a Python dict literal
      (from str(dict) passed as prompt) → parsed back to dict fields
    """
    # Reconstitute Document objects in list fields
    try:
        from langchain_core.documents import Document
    except ImportError:
        Document = None  # type: ignore[assignment]

    for key, val in state.items():
        if isinstance(val, list) and val and Document is not None:
            reconstituted = []
            for item in val:
                if isinstance(item, dict) and "page_content" in item:
                    reconstituted.append(
                        Document(
                            page_content=item["page_content"],
                            metadata=item.get("metadata", {}),
                        )
                    )
                else:
                    reconstituted.append(item)
            if reconstituted != val:
                state[key] = reconstituted

    # Handle str(dict)-as-prompt: if there's exactly one non-empty string field
    # and it looks like a Python dict literal, parse it and spread into state
    str_fields = [(k, v) for k, v in state.items() if isinstance(v, str) and v.strip()]
    if len(str_fields) == 1:
        field_key, field_val = str_fields[0]
        stripped = field_val.strip()
        if stripped.startswith("{") and stripped.endswith("}"):
            try:
                import ast
                parsed = ast.literal_eval(stripped)
                if isinstance(parsed, dict):
                    state.update(parsed)
            except (ValueError, SyntaxError):
                pass

    return state


def make_node_worker(node_func: Any, node_name: str) -> Any:
    """Wrap a graph node function as a Conductor task worker.

    The worker receives ``{state: {...}}`` as input, calls the node function
    with the state, merges the update into the state, and returns
    ``{state: {...}, result: "..."}`` as output.
    """
    from conductor.client.http.models.task import Task
    from conductor.client.http.models.task_result import TaskResult
    from conductor.client.http.models.task_result_status import TaskResultStatus

    def worker(task: Task) -> TaskResult:
        state = task.input_data.get("state") or {}
        if not isinstance(state, dict):
            state = {}
        state = _reconstitute_state(state)
        logger.debug(
            "Node worker '%s' received state keys: %s",
            node_name,
            list(state.keys()) if state else "empty",
        )
        try:
            update = node_func(state)
            merged = {**state, **(update if isinstance(update, dict) else {})}
            result_str = _state_to_result(merged)
            return TaskResult(
                task_id=task.task_id,
                workflow_instance_id=task.workflow_instance_id,
                status=TaskResultStatus.COMPLETED,
                output_data={"state": merged, "result": result_str},
            )
        except Exception as exc:
            logger.error("Node worker '%s' failed: %s (state=%s)", node_name, exc, state)
            return TaskResult(
                task_id=task.task_id,
                workflow_instance_id=task.workflow_instance_id,
                status=TaskResultStatus.FAILED,
                reason_for_incompletion=str(exc),
            )

    worker.__name__ = f"node_worker_{node_name}"
    worker.__annotations__ = {"task": object, "return": object}
    return worker


def make_router_worker(
    router_func: Any, router_name: str, *, is_dynamic_fanout: bool = False
) -> Any:
    """Wrap a conditional edge routing function as a Conductor task worker.

    The worker receives ``{state: {...}}`` as input, calls the routing
    function, and returns ``{decision: "target_name", state: {...}}``.

    For dynamic fan-out (Send API), returns ``{dynamic_tasks: [...], state: {...}}``
    where each task is ``{node: "node_name", input: {...}}``.
    """
    from conductor.client.http.models.task import Task
    from conductor.client.http.models.task_result import TaskResult
    from conductor.client.http.models.task_result_status import TaskResultStatus

    def worker(task: Task) -> TaskResult:
        state = task.input_data.get("state") or {}
        if not isinstance(state, dict):
            state = {}
        state = _reconstitute_state(state)
        try:
            decision = router_func(state)

            # Handle Send objects (dynamic fan-out)
            if is_dynamic_fanout and isinstance(decision, list):
                dynamic_tasks = []
                for item in decision:
                    # langgraph.types.Send has .node and .arg attributes
                    node = getattr(item, "node", None)
                    arg = getattr(item, "arg", None)
                    if node is not None:
                        task_input = arg if isinstance(arg, dict) else {}
                        dynamic_tasks.append({"node": node, "input": task_input})
                if dynamic_tasks:
                    logger.info(
                        "Router '%s': dynamic fan-out → %d Send tasks to nodes: %s",
                        router_name,
                        len(dynamic_tasks),
                        list({t["node"] for t in dynamic_tasks}),
                    )
                    return TaskResult(
                        task_id=task.task_id,
                        workflow_instance_id=task.workflow_instance_id,
                        status=TaskResultStatus.COMPLETED,
                        output_data={"dynamic_tasks": dynamic_tasks, "state": state},
                    )

            return TaskResult(
                task_id=task.task_id,
                workflow_instance_id=task.workflow_instance_id,
                status=TaskResultStatus.COMPLETED,
                output_data={"decision": str(decision), "state": state},
            )
        except Exception as exc:
            logger.error("Router worker '%s' failed: %s", router_name, exc)
            return TaskResult(
                task_id=task.task_id,
                workflow_instance_id=task.workflow_instance_id,
                status=TaskResultStatus.FAILED,
                reason_for_incompletion=str(exc),
            )

    worker.__name__ = f"router_worker_{router_name}"
    worker.__annotations__ = {"task": object, "return": object}
    return worker


def _state_to_result(state: Dict[str, Any]) -> str:
    """Extract a human-readable result string from accumulated state."""
    # Try common output field names
    for key in ("result", "final_email", "output", "answer", "response"):
        if key in state and state[key]:
            return str(state[key])
    # Serialize the whole state
    import json

    try:
        return json.dumps(state)
    except Exception:
        return str(state)


# ── LLM intercept workers ────────────────────────────────────────────

# Lock to protect global-replacement during LLM interception.
# Concurrent workers for the same node function must not clash.
_llm_intercept_lock = threading.Lock()


class _CapturedLLMCall(Exception):
    """Raised by _LLMCaptureProxy to capture messages without calling the real LLM."""

    def __init__(self, messages: list):
        self.messages = messages


class _LLMCaptureProxy:
    """Drop-in replacement for an LLM object that captures invoke() arguments."""

    def invoke(self, messages: Any, **kwargs: Any) -> Any:
        raise _CapturedLLMCall(messages)

    def __call__(self, messages: Any, **kwargs: Any) -> Any:
        raise _CapturedLLMCall(messages)


class _LLMMockResponse:
    """Mimics a LangChain AIMessage response with a .content attribute."""

    def __init__(self, content: str):
        self.content = content
        self.tool_calls: list = []
        self.type = "ai"


class _LLMMockProxy:
    """Drop-in replacement for an LLM that returns a pre-set response."""

    def __init__(self, response_content: str):
        self._response = _LLMMockResponse(response_content)

    def invoke(self, messages: Any, **kwargs: Any) -> Any:
        return self._response

    def __call__(self, messages: Any, **kwargs: Any) -> Any:
        return self._response


def _find_llm_in_func(func: Any) -> Optional[Tuple[str, Any]]:
    """Find the LLM variable name and object used in a node function.

    Checks the function's bytecode references (co_names) against its globals
    for objects that look like LLMs (have model_name attribute).

    Returns (variable_name, llm_object) or None.
    """
    code = getattr(func, "__code__", None)
    if code is None:
        return None
    func_globals = getattr(func, "__globals__", None)
    if not func_globals:
        return None
    # co_names = global variable names referenced in the function's bytecode
    names = set(code.co_names)
    for name in names:
        val = func_globals.get(name)
        if val is not None and _try_get_model_string(val) is not None:
            return name, val
    return None


def _serialize_langchain_messages(messages: Any) -> List[Dict[str, str]]:
    """Convert LangChain message objects to Conductor LLM_CHAT_COMPLETE format.

    Conductor expects: [{"role": "system", "message": "..."}, ...]
    LangChain uses: SystemMessage, HumanMessage, AIMessage objects.
    """
    result: List[Dict[str, str]] = []
    if not isinstance(messages, (list, tuple)):
        return result
    for msg in messages:
        role = _langchain_role(msg)
        content = getattr(msg, "content", None)
        if content is None and isinstance(msg, dict):
            content = msg.get("content", "")
        if content is None:
            content = str(msg)
        result.append({"role": role, "message": str(content)})
    return result


def _langchain_role(msg: Any) -> str:
    """Map a LangChain message to a Conductor role string."""
    type_name = type(msg).__name__
    if "System" in type_name:
        return "system"
    if "Human" in type_name or "User" in type_name:
        return "user"
    if "AI" in type_name or "Assistant" in type_name:
        return "assistant"
    # Dict-style messages
    if isinstance(msg, dict):
        role = msg.get("role", "user")
        if role == "human":
            return "user"
        if role == "ai":
            return "assistant"
        return role
    return "user"


def make_llm_prep_worker(node_func: Any, node_name: str, llm_var_name: str) -> Any:
    """Build a prep worker that intercepts llm.invoke() and captures messages.

    The worker runs the node function with a proxy LLM.  When the function
    calls llm.invoke(messages), the proxy raises _CapturedLLMCall.
    The worker catches it, serializes the messages, and returns them as output.

    Returns a Task → TaskResult worker function.
    """
    from conductor.client.http.models.task import Task
    from conductor.client.http.models.task_result import TaskResult
    from conductor.client.http.models.task_result_status import TaskResultStatus

    def worker(task: Task) -> TaskResult:
        state = task.input_data.get("state") or {}
        if not isinstance(state, dict):
            state = {}
        state = _reconstitute_state(state)
        logger.debug("LLM prep worker '%s' capturing messages (state keys: %s)", node_name, list(state.keys()))

        with _llm_intercept_lock:
            original = node_func.__globals__.get(llm_var_name)
            node_func.__globals__[llm_var_name] = _LLMCaptureProxy()
            try:
                # Run the function — it should hit llm.invoke() and raise
                update = node_func(state)
                # If we get here, the function didn't call llm.invoke().
                # This happens when the function conditionally skips the LLM
                # (e.g. early return when no relevant docs). Complete the
                # operation directly — the compiler's SWITCH will skip the
                # LLM_CHAT_COMPLETE task.
                logger.info(
                    "LLM prep worker '%s': function completed without calling llm.invoke(), "
                    "returning direct result (_skip_llm=true)",
                    node_name,
                )
                merged = {**state, **(update if isinstance(update, dict) else {})}
                result_str = _state_to_result(merged)
                return TaskResult(
                    task_id=task.task_id,
                    workflow_instance_id=task.workflow_instance_id,
                    status=TaskResultStatus.COMPLETED,
                    output_data={
                        "messages": [],
                        "state": merged,
                        "result": result_str,
                        "_skip_llm": True,
                    },
                )
            except _CapturedLLMCall as cap:
                messages = _serialize_langchain_messages(cap.messages)
                return TaskResult(
                    task_id=task.task_id,
                    workflow_instance_id=task.workflow_instance_id,
                    status=TaskResultStatus.COMPLETED,
                    output_data={"messages": messages, "state": state},
                )
            except Exception as exc:
                logger.error("LLM prep worker '%s' failed: %s", node_name, exc)
                return TaskResult(
                    task_id=task.task_id,
                    workflow_instance_id=task.workflow_instance_id,
                    status=TaskResultStatus.FAILED,
                    reason_for_incompletion=str(exc),
                )
            finally:
                node_func.__globals__[llm_var_name] = original

    worker.__name__ = f"llm_prep_{node_name}"
    worker.__annotations__ = {"task": object, "return": object}
    return worker


def make_llm_finish_worker(node_func: Any, node_name: str, llm_var_name: str) -> Any:
    """Build a finish worker that re-runs the node function with a mock LLM.

    The worker replaces the LLM with a mock that returns the server's
    LLM_CHAT_COMPLETE response.  The node function runs to completion,
    producing the state update as usual.

    Returns a Task → TaskResult worker function.
    """
    from conductor.client.http.models.task import Task
    from conductor.client.http.models.task_result import TaskResult
    from conductor.client.http.models.task_result_status import TaskResultStatus

    def worker(task: Task) -> TaskResult:
        state = task.input_data.get("state") or {}
        if not isinstance(state, dict):
            state = {}
        state = _reconstitute_state(state)
        llm_result = task.input_data.get("llm_result", "")
        logger.debug(
            "LLM finish worker '%s' with llm_result length=%d",
            node_name,
            len(str(llm_result)),
        )

        with _llm_intercept_lock:
            original = node_func.__globals__.get(llm_var_name)
            node_func.__globals__[llm_var_name] = _LLMMockProxy(str(llm_result))
            try:
                update = node_func(state)
                merged = {**state, **(update if isinstance(update, dict) else {})}
                result_str = _state_to_result(merged)
                return TaskResult(
                    task_id=task.task_id,
                    workflow_instance_id=task.workflow_instance_id,
                    status=TaskResultStatus.COMPLETED,
                    output_data={"state": merged, "result": result_str},
                )
            except Exception as exc:
                logger.error("LLM finish worker '%s' failed: %s", node_name, exc)
                return TaskResult(
                    task_id=task.task_id,
                    workflow_instance_id=task.workflow_instance_id,
                    status=TaskResultStatus.FAILED,
                    reason_for_incompletion=str(exc),
                )
            finally:
                node_func.__globals__[llm_var_name] = original

    worker.__name__ = f"llm_finish_{node_name}"
    worker.__annotations__ = {"task": object, "return": object}
    return worker


# ── Subgraph intercept workers ────────────────────────────────────────


class _CapturedSubgraphCall(Exception):
    """Raised by _SubgraphCaptureProxy to capture invoke() arguments."""

    def __init__(self, input_data: dict):
        self.input_data = input_data


class _SubgraphCaptureProxy:
    """Drop-in replacement for a compiled subgraph that captures invoke() arguments."""

    def invoke(self, input_data: Any, **kwargs: Any) -> Any:
        raise _CapturedSubgraphCall(input_data if isinstance(input_data, dict) else {})

    def __call__(self, input_data: Any, **kwargs: Any) -> Any:
        raise _CapturedSubgraphCall(input_data if isinstance(input_data, dict) else {})


class _SubgraphMockProxy:
    """Drop-in replacement for a compiled subgraph that returns a pre-set result."""

    def __init__(self, result: dict):
        self._result = result

    def invoke(self, input_data: Any, **kwargs: Any) -> Any:
        return self._result

    def __call__(self, input_data: Any, **kwargs: Any) -> Any:
        return self._result


def _is_compiled_graph(obj: Any) -> bool:
    """Check if obj is a compiled LangGraph StateGraph."""
    type_name = type(obj).__name__
    return "CompiledStateGraph" in type_name or "CompiledGraph" in type_name


def _find_subgraph_in_func(func: Any) -> Optional[Tuple[str, Any]]:
    """Find a compiled subgraph variable referenced in a node function.

    Checks the function's bytecode references (co_names) against its globals
    for objects that are compiled LangGraph StateGraphs.

    Returns (variable_name, compiled_graph_object) or None.
    """
    code = getattr(func, "__code__", None)
    if code is None:
        return None
    func_globals = getattr(func, "__globals__", None)
    if not func_globals:
        return None
    names = set(code.co_names)
    for name in names:
        val = func_globals.get(name)
        if val is not None and _is_compiled_graph(val):
            return name, val
    return None


def make_subgraph_prep_worker(node_func: Any, node_name: str, subgraph_var_name: str) -> Any:
    """Build a prep worker that intercepts subgraph.invoke() and captures input.

    The worker runs the node function with a proxy subgraph.  When the function
    calls subgraph.invoke(input), the proxy raises _CapturedSubgraphCall.
    The worker catches it and returns the captured input as output.

    Returns a Task → TaskResult worker function.
    """
    from conductor.client.http.models.task import Task
    from conductor.client.http.models.task_result import TaskResult
    from conductor.client.http.models.task_result_status import TaskResultStatus

    def worker(task: Task) -> TaskResult:
        state = task.input_data.get("state") or {}
        if not isinstance(state, dict):
            state = {}
        state = _reconstitute_state(state)
        logger.debug("Subgraph prep worker '%s' capturing input (state keys: %s)", node_name, list(state.keys()))

        with _llm_intercept_lock:
            original = node_func.__globals__.get(subgraph_var_name)
            node_func.__globals__[subgraph_var_name] = _SubgraphCaptureProxy()
            try:
                update = node_func(state)
                # Function completed without calling subgraph.invoke()
                logger.info(
                    "Subgraph prep worker '%s': function completed without calling subgraph.invoke(), "
                    "returning direct result (_skip_subgraph=true)",
                    node_name,
                )
                merged = {**state, **(update if isinstance(update, dict) else {})}
                result_str = _state_to_result(merged)
                return TaskResult(
                    task_id=task.task_id,
                    workflow_instance_id=task.workflow_instance_id,
                    status=TaskResultStatus.COMPLETED,
                    output_data={
                        "subgraph_input": {},
                        "state": merged,
                        "result": result_str,
                        "_skip_subgraph": True,
                    },
                )
            except _CapturedSubgraphCall as cap:
                return TaskResult(
                    task_id=task.task_id,
                    workflow_instance_id=task.workflow_instance_id,
                    status=TaskResultStatus.COMPLETED,
                    output_data={"subgraph_input": cap.input_data, "state": state},
                )
            except Exception as exc:
                logger.error("Subgraph prep worker '%s' failed: %s", node_name, exc)
                return TaskResult(
                    task_id=task.task_id,
                    workflow_instance_id=task.workflow_instance_id,
                    status=TaskResultStatus.FAILED,
                    reason_for_incompletion=str(exc),
                )
            finally:
                node_func.__globals__[subgraph_var_name] = original

    worker.__name__ = f"subgraph_prep_{node_name}"
    worker.__annotations__ = {"task": object, "return": object}
    return worker


def make_subgraph_finish_worker(node_func: Any, node_name: str, subgraph_var_name: str) -> Any:
    """Build a finish worker that re-runs the node function with a mock subgraph.

    The worker replaces the subgraph with a mock that returns the SUB_WORKFLOW's
    output state.  The node function runs to completion, producing the state
    update as usual.

    Returns a Task → TaskResult worker function.
    """
    from conductor.client.http.models.task import Task
    from conductor.client.http.models.task_result import TaskResult
    from conductor.client.http.models.task_result_status import TaskResultStatus

    def worker(task: Task) -> TaskResult:
        state = task.input_data.get("state") or {}
        if not isinstance(state, dict):
            state = {}
        state = _reconstitute_state(state)
        subgraph_result = task.input_data.get("subgraph_result") or {}
        if not isinstance(subgraph_result, dict):
            subgraph_result = {}
        logger.debug(
            "Subgraph finish worker '%s' with subgraph_result keys=%s",
            node_name,
            list(subgraph_result.keys()) if subgraph_result else "empty",
        )

        with _llm_intercept_lock:
            original = node_func.__globals__.get(subgraph_var_name)
            node_func.__globals__[subgraph_var_name] = _SubgraphMockProxy(subgraph_result)
            try:
                update = node_func(state)
                merged = {**state, **(update if isinstance(update, dict) else {})}
                result_str = _state_to_result(merged)
                return TaskResult(
                    task_id=task.task_id,
                    workflow_instance_id=task.workflow_instance_id,
                    status=TaskResultStatus.COMPLETED,
                    output_data={"state": merged, "result": result_str},
                )
            except Exception as exc:
                logger.error("Subgraph finish worker '%s' failed: %s", node_name, exc)
                return TaskResult(
                    task_id=task.task_id,
                    workflow_instance_id=task.workflow_instance_id,
                    status=TaskResultStatus.FAILED,
                    reason_for_incompletion=str(exc),
                )
            finally:
                node_func.__globals__[subgraph_var_name] = original

    worker.__name__ = f"subgraph_finish_{node_name}"
    worker.__annotations__ = {"task": object, "return": object}
    return worker


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


def _extract_system_prompt_from_graph(graph: Any) -> Optional[str]:
    """Extract system prompt from a create_agent graph's model_node closure.

    create_agent stores the system prompt as a ``SystemMessage`` object in
    ``model_node``'s ``__closure__`` under the free variable ``system_message``.
    Returns the text content if found, otherwise None.
    """
    nodes = getattr(graph, "nodes", None)
    if not nodes or not isinstance(nodes, dict):
        return None

    for node_name, node in nodes.items():
        if node_name in ("__start__", "__end__"):
            continue
        bound = getattr(node, "bound", None)
        if bound is None:
            continue
        func = getattr(bound, "func", None)
        if func is None or not callable(func):
            continue
        code = getattr(func, "__code__", None)
        closure = getattr(func, "__closure__", None)
        if code is None or closure is None:
            continue
        freevars = getattr(code, "co_freevars", ())
        if "system_message" not in freevars:
            continue
        idx = freevars.index("system_message")
        if idx >= len(closure):
            continue
        try:
            val = closure[idx].cell_contents
        except ValueError:
            continue
        if val is None:
            continue
        # SystemMessage has .content attribute
        content = getattr(val, "content", None)
        if content and isinstance(content, str):
            return content
    return None


def _find_model_in_graph(graph: Any) -> Optional[str]:
    """Find the LLM model string ('provider/model') from graph nodes.

    Searches three locations:
    1. Node attributes and closures (for create_react_agent-style graphs)
    2. Node function __globals__ (for custom StateGraphs with module-level LLM)
    """
    nodes = getattr(graph, "nodes", None)
    if not nodes or not isinstance(nodes, dict):
        return None

    # 1. Search node attributes and closures (original path)
    for node in nodes.values():
        model = _search_for_model(node, depth=5)
        if model:
            return model

    # 2. Search globals of node functions (for module-level LLMs like `llm = ChatOpenAI(...)`)
    seen_globals: set = set()
    for node_name, node in nodes.items():
        if node_name in ("__start__", "__end__"):
            continue
        func = _get_node_function(node) if hasattr(node, "bound") else None
        if func is None:
            continue
        func_globals = getattr(func, "__globals__", None)
        if func_globals is None or id(func_globals) in seen_globals:
            continue
        seen_globals.add(id(func_globals))
        for var_name, val in func_globals.items():
            if var_name.startswith("_") or var_name.startswith("__"):
                continue
            model = _try_get_model_string(val)
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
        execution_id = task.workflow_instance_id
        prompt = task.input_data.get("prompt", "")
        session_id = (task.input_data.get("session_id") or "").strip()

        # Resolve workflow-level credentials and inject into os.environ
        _injected_cred_keys = []
        try:
            import os as _os
            from agentspan.agents.runtime._dispatch import (
                _extract_execution_token,
                _get_credential_fetcher,
                _workflow_credentials,
                _workflow_credentials_lock,
            )
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
                            _injected_cred_keys.append(k)
        except Exception as _cred_err:
            import logging as _log
            _log.getLogger("agentspan.agents.frameworks.langgraph").warning(
                "Failed to resolve credentials for LangGraph: %s", _cred_err)

        try:
            graph_input = _build_input(graph, prompt)
            config = {}
            if session_id:
                config = {"configurable": {"thread_id": session_id}}

            final_state = None
            for mode, chunk in graph.stream(graph_input, config, stream_mode=["updates", "values"]):
                if mode == "updates":
                    _process_updates_chunk(chunk, execution_id, server_url, auth_key, auth_secret)
                elif mode == "values":
                    final_state = chunk

            output = _extract_output(final_state)
            return TaskResult(
                task_id=task.task_id,
                workflow_instance_id=execution_id,
                status=TaskResultStatus.COMPLETED,
                output_data={"result": output},
            )

        except Exception as exc:
            logger.error("LangGraph worker error (execution_id=%s): %s", execution_id, exc)
            return TaskResult(
                task_id=task.task_id,
                workflow_instance_id=execution_id,
                status=TaskResultStatus.FAILED,
                reason_for_incompletion=str(exc),
            )
        finally:
            # Clean up injected credential env vars
            import os as _os
            for k in _injected_cred_keys:
                _os.environ.pop(k, None)

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
    execution_id: str,
    server_url: str,
    auth_key: str,
    auth_secret: str,
) -> None:
    """Map a LangGraph 'updates' chunk to Agentspan SSE events and push non-blocking."""
    for node_name, state_updates in chunk.items():
        # Always emit a thinking event for each node execution
        _push_event_nonblocking(
            execution_id,
            {"type": "thinking", "content": node_name},
            server_url,
            auth_key,
            auth_secret,
        )

        # Check for tool calls and tool results in messages
        messages = state_updates.get("messages", []) if isinstance(state_updates, dict) else []
        for msg in messages if isinstance(messages, list) else []:
            _emit_message_events(msg, execution_id, server_url, auth_key, auth_secret)


def _emit_message_events(
    msg: Any,
    execution_id: str,
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
            execution_id,
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
                execution_id,
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
            headers = {}
            if auth_key:
                headers["X-Auth-Key"] = auth_key
            if auth_secret:
                headers["X-Auth-Secret"] = auth_secret
            requests.post(url, json=event, headers=headers, timeout=5)
        except Exception as exc:
            logger.debug("Event push failed (execution_id=%s): %s", execution_id, exc)

    _EVENT_PUSH_POOL.submit(_do_push)
