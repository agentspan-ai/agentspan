# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""Generic agent serializer — zero framework-specific code.

Provides:
- Framework auto-detection from object module name
- Deep serialization of any agent object to JSON-compatible dict
- Callable extraction with JSON schema generation from type hints
"""

from __future__ import annotations

import enum
import inspect
import logging
from dataclasses import dataclass, is_dataclass
from dataclasses import fields as dc_fields
from typing import Any, Callable, Dict, List, Optional, Set, Tuple

logger = logging.getLogger("agentspan.agents.frameworks")


# ── Framework detection ──────────────────────────────────────────────

# Maps module name prefixes to framework identifiers.
# Adding a new framework = adding one line here.
_FRAMEWORK_DETECTION: Dict[str, str] = {
    "agents": "openai",  # openai-agents package
    "google.adk": "google_adk",  # google-adk package
}


def detect_framework(agent_obj: Any) -> Optional[str]:
    """Detect the agent framework from the object's type name and module.

    Returns the framework identifier (e.g. ``"openai"``, ``"google_adk"``,
    ``"langgraph"``, ``"langchain"``, ``"google_adk"``) or ``None`` for native
    Conductor Agents.
    """
    # Skill framework detection — must be checked before native Agent check
    # since skill agents are Agent instances with a _framework marker.
    if hasattr(agent_obj, "_framework") and agent_obj._framework == "skill":
        return "skill"

    # Native Agent — check for claude-code model first
    from agentspan.agents.agent import Agent

    if isinstance(agent_obj, Agent):
        # Native Agent instances are always native, even with claude-code models.
        # The server handles claude-code model routing during execution.
        return None

    # Precise type-name check for LangGraph (avoid fragile module prefix matching
    # since langgraph uses internal Pregel/CompiledStateGraph class names)
    type_name = type(agent_obj).__name__
    if type_name in ("CompiledStateGraph", "Pregel", "CompiledGraph"):
        return "langgraph"

    # LangChain AgentExecutor
    if type_name == "AgentExecutor":
        return "langchain"

    # Claude Agent SDK (claude-code-sdk package)
    if type_name in ("ClaudeCodeOptions", "ClaudeAgentOptions"):
        return "claude_agent_sdk"

    # Existing module-prefix fallback for openai and google_adk
    module = type(agent_obj).__module__ or ""
    for prefix, framework_id in _FRAMEWORK_DETECTION.items():
        if module == prefix or module.startswith(prefix + "."):
            return framework_id
    return None


# ── Worker info ──────────────────────────────────────────────────────


@dataclass
class WorkerInfo:
    """Extracted callable info for Conductor worker registration."""

    name: str
    description: str
    input_schema: Dict[str, Any]
    func: Callable[..., Any]
    _pre_wrapped: bool = False  # True if func is already a Task→TaskResult worker
    _extra: Optional[Dict[str, Any]] = None  # Extra metadata (e.g. llm_var_name for LLM intercept)


# ── Generic serializer ───────────────────────────────────────────────


def serialize_agent(agent_obj: Any) -> Tuple[Dict[str, Any], List[WorkerInfo]]:
    """Generic deep serialization of any agent object.

    Walks the object tree using standard Python introspection.
    Callables are replaced with ``{"_worker_ref": "name", ...}`` markers.
    Non-callable objects are serialized with ``{"_type": "ClassName", ...}``.

    Returns:
        A tuple of (json_dict, extracted_workers).
    """
    # LangGraph/LangChain: short-circuit to framework-specific serializer
    # Note: func=None in returned WorkerInfo — filled by _build_passthrough_func()
    # in runtime._start_framework() before calling _register_passthrough_worker().
    framework = detect_framework(agent_obj)
    if framework == "langgraph":
        from agentspan.agents.frameworks.langgraph import serialize_langgraph

        return serialize_langgraph(agent_obj)
    if framework == "langchain":
        from agentspan.agents.frameworks.langchain import serialize_langchain

        return serialize_langchain(agent_obj)
    if framework == "claude_agent_sdk":
        from agentspan.agents.frameworks.claude_agent_sdk import serialize_claude_agent_sdk

        return serialize_claude_agent_sdk(agent_obj)
    if framework == "skill":
        return _serialize_skill(agent_obj)

    workers: List[WorkerInfo] = []
    seen: Set[int] = set()  # Prevent infinite recursion on circular refs

    def _serialize(obj: Any) -> Any:
        if obj is None or isinstance(obj, (str, int, float, bool)):
            return obj

        obj_id = id(obj)

        # Enum → value
        if isinstance(obj, enum.Enum):
            return obj.value

        # Pydantic model class (used as output_type) → JSON schema
        if isinstance(obj, type) and hasattr(obj, "model_json_schema"):
            try:
                return obj.model_json_schema()
            except Exception:
                return {"_type": obj.__name__}

        # Callable (function, method, decorated tool) — extract as worker
        if _is_tool_callable(obj):
            worker = _extract_callable(obj)
            workers.append(worker)
            return {
                "_worker_ref": worker.name,
                "description": worker.description,
                "parameters": worker.input_schema,
            }

        # Agent-as-tool: framework tool wrapping a nested agent.
        # Must be checked BEFORE generic tool extraction so the embedded
        # agent is serialized as a child workflow, not a worker_ref.
        agent_tool_result = _try_extract_agent_tool(obj)
        if agent_tool_result is not None:
            config_dict, child_workers = agent_tool_result
            workers.extend(child_workers)
            return config_dict

        # Tool-like object (has name + description + schema + embedded callable)
        # Frameworks like OpenAI wrap functions in tool objects that aren't
        # directly callable but contain the original function.
        tool_worker = _try_extract_tool_object(obj)
        if tool_worker is not None:
            workers.append(tool_worker)
            return {
                "_worker_ref": tool_worker.name,
                "description": tool_worker.description,
                "parameters": tool_worker.input_schema,
            }

        # Prevent circular references
        if obj_id in seen:
            return f"<circular ref: {type(obj).__name__}>"
        seen.add(obj_id)

        try:
            # Dict
            if isinstance(obj, dict):
                return {str(k): _serialize(v) for k, v in obj.items()}

            # List / tuple / set
            if isinstance(obj, (list, tuple, set, frozenset)):
                return [_serialize(v) for v in obj]

            # Bytes
            if isinstance(obj, bytes):
                return obj.decode("utf-8", errors="replace")

            # Pydantic v2 (instance, not class)
            if hasattr(obj, "model_dump") and not isinstance(obj, type):
                try:
                    return _serialize(obj.model_dump())
                except (ValueError, RecursionError):
                    # Circular reference in model_dump() — fall through to __dict__
                    pass

            # Pydantic v1 (instance, not class)
            if (
                hasattr(obj, "dict")
                and hasattr(type(obj), "__fields__")
                and not isinstance(obj, type)
            ):
                try:
                    return _serialize(obj.dict())
                except (ValueError, RecursionError):
                    pass

            # Dataclass
            if is_dataclass(obj) and not isinstance(obj, type):
                d: Dict[str, Any] = {"_type": type(obj).__name__}
                for f in dc_fields(obj):
                    val = getattr(obj, f.name, None)
                    d[f.name] = _serialize(val)
                return d

            # Regular object with __dict__
            if hasattr(obj, "__dict__"):
                d = {"_type": type(obj).__name__}
                for k, v in vars(obj).items():
                    if not k.startswith("_"):
                        d[k] = _serialize(v)
                return d

            # Fallback — str representation
            return str(obj)
        finally:
            seen.discard(obj_id)

    config = _serialize(agent_obj)
    return config, workers


def _is_tool_callable(obj: Any) -> bool:
    """Check if an object is a callable that should be extracted as a worker.

    We want to capture tool functions but NOT classes, modules, or built-in
    types that happen to be callable.
    """
    if isinstance(obj, type):
        return False
    if not callable(obj):
        return False
    # Skip built-in functions and lambdas without useful signatures
    if isinstance(obj, (type(len), type(print))):
        return False
    # Must have a meaningful name (not a lambda or anonymous)
    name = getattr(obj, "__name__", None) or getattr(obj, "name", None)
    if not name or name == "<lambda>":
        return False
    # Must have inspectable signature
    try:
        inspect.signature(obj)
        return True
    except (ValueError, TypeError):
        return False


def _try_extract_agent_tool(obj: Any) -> Optional[Tuple[Dict[str, Any], List[WorkerInfo]]]:
    """Detect a framework agent-as-tool wrapper and return a serialized marker.

    OpenAI agents SDK's ``Agent.as_tool()`` creates a ``FunctionTool`` with
    ``_is_agent_tool=True`` and ``_agent_instance`` pointing to the child
    agent.  We serialize this as ``{"_type": "AgentTool", ...}`` so the
    server normalizer can produce a ``toolType="agent_tool"`` config and
    run the child as a SUB_WORKFLOW.

    Returns:
        A tuple of (serialized_dict, child_workers) or ``None``.
    """
    if not getattr(obj, "_is_agent_tool", False):
        return None

    child_agent = getattr(obj, "_agent_instance", None)
    if child_agent is None:
        return None

    child_config, child_workers = serialize_agent(child_agent)
    return (
        {
            "_type": "AgentTool",
            "name": getattr(obj, "name", None) or getattr(child_agent, "name", "agent_tool"),
            "description": getattr(obj, "description", "") or "",
            "agent": child_config,
        },
        child_workers,
    )


def _try_extract_tool_object(obj: Any) -> Optional[WorkerInfo]:
    """Try to recognize a tool-like wrapper object and extract its callable.

    Many frameworks wrap tool functions in objects that have:
    - A ``name`` attribute
    - A ``description`` or docstring
    - A JSON schema (``params_json_schema``, ``input_schema``, ``parameters``, etc.)
    - An embedded callable (found by walking the object's attributes)

    This is fully generic — no framework-specific knowledge needed.
    """
    # Must have a name
    name = getattr(obj, "name", None)
    if not name or not isinstance(name, str):
        return None

    # Must have some kind of schema (indicates it's a tool definition)
    schema = (
        getattr(obj, "params_json_schema", None)
        or getattr(obj, "input_schema", None)
        or getattr(obj, "parameters", None)
    )
    if not isinstance(schema, dict):
        return None

    description = getattr(obj, "description", None) or ""

    # Find the original callable by searching the object's attribute tree
    # (up to 2 levels deep) for a plain function
    original_func = _find_embedded_function(obj, max_depth=2)
    if original_func is None:
        # No callable found — still emit as a tool but without a local worker
        logger.debug("Tool-like object '%s' has no extractable callable", name)
        return None

    return WorkerInfo(
        name=name,
        description=description.strip().split("\n")[0] if description else "",
        input_schema=schema,
        func=original_func,
    )


def _find_embedded_function(obj: Any, max_depth: int = 2) -> Optional[Any]:
    """Walk an object's attributes to find an embedded plain function.

    Searches closures and nested attribute objects for the original
    user-defined function. Returns ``None`` if not found.
    """
    if max_depth <= 0:
        return None

    # Check direct attributes for callables that look like user functions
    for attr_name in vars(obj) if hasattr(obj, "__dict__") else []:
        val = getattr(obj, attr_name, None)
        if val is None:
            continue

        # Plain function with a clean signature
        if inspect.isfunction(val):
            # Check if it has a closure containing the original function
            func = _extract_from_closure(val)
            if func is not None:
                return func
            # The function itself might be usable
            return val

        # Nested object — recurse one level
        if hasattr(val, "__dict__") and not isinstance(val, type):
            result = _find_embedded_function(val, max_depth - 1)
            if result is not None:
                return result

    return None


def _extract_from_closure(func: Any) -> Optional[Any]:
    """Extract the original user function from a closure's cell variables."""
    closure = getattr(func, "__closure__", None)
    if not closure:
        return None

    for cell in closure:
        try:
            val = cell.cell_contents
        except ValueError:
            continue
        if inspect.isfunction(val):
            # Skip internal wrappers that take (ctx, input) or (context, ...)
            try:
                sig = inspect.signature(val)
                param_names = list(sig.parameters.keys())
                # Internal wrappers typically start with ctx/context as first param
                if param_names and param_names[0] in ("ctx", "context"):
                    continue
                return val
            except (ValueError, TypeError):
                continue
    return None


def _extract_callable(func: Any) -> WorkerInfo:
    """Extract name, description, and JSON schema from a callable."""
    from agentspan.agents._internal.schema_utils import schema_from_function

    # Unwrap decorated functions to get the original
    actual_func = func
    while hasattr(actual_func, "__wrapped__"):
        actual_func = actual_func.__wrapped__

    name = (
        getattr(func, "name", None)
        or getattr(func, "__name__", None)
        or getattr(actual_func, "__name__", "unknown_tool")
    )
    description = (
        getattr(func, "description", None)
        or getattr(func, "__doc__", None)
        or getattr(actual_func, "__doc__", "")
        or ""
    )
    # Clean up docstring
    description = description.strip().split("\n")[0] if description else ""

    try:
        schemas = schema_from_function(actual_func)
        input_schema = schemas.get("input", {})
    except Exception:
        logger.debug("Could not extract schema from %s, using empty schema", name)
        input_schema = {"type": "object", "properties": {}}

    return WorkerInfo(
        name=name,
        description=description,
        input_schema=input_schema,
        func=func,
    )


def _serialize_skill(agent_obj: Any) -> Tuple[Dict[str, Any], List[WorkerInfo]]:
    """Serialize a skill-based agent for server-side normalization.

    Returns the raw skill config (which the server's SkillNormalizer expects)
    and WorkerInfo instances for each skill worker (scripts + read_skill_file).
    """
    from agentspan.agents.skill import create_skill_workers

    raw_config = agent_obj._framework_config

    # Convert SkillWorkers to WorkerInfo for the framework worker registration path
    skill_workers = create_skill_workers(agent_obj)
    workers: List[WorkerInfo] = []
    for sw in skill_workers:
        workers.append(
            WorkerInfo(
                name=sw.name,
                description=sw.description,
                input_schema={"type": "object", "properties": {
                    "command": {"type": "string", "description": "Arguments to pass"},
                }},
                func=sw.func,
            )
        )

    return raw_config, workers
