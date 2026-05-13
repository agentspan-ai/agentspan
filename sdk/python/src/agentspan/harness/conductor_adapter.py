# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""Conductor adapter — wrap harness ``Tool`` instances so they can run as
Conductor SIMPLE tasks under an agentspan ``Agent`` workflow.

The harness used to run its own conversation loop and call LLMs in-process
via litellm. That meant two parallel codepaths inside agentspan for the same
job. This adapter eliminates the duplication: each harness ``Tool`` becomes
a regular ``ToolDef`` whose worker function applies the harness's
permission / sandbox / hook layers before invoking the tool's ``call()``,
then returns a result the LLM can see.

The session-level ``HarnessRuntime`` builds these ``ToolDef``s, hands them
to a normal ``Agent``, and submits via ``AgentRuntime`` — which means the
conversation loop, durability, retries, telemetry, and per-user
credentials are all owned by Conductor.

Public API:

* :func:`wrap_tool_as_tool_def` — convert one harness ``Tool`` to a
  Conductor-ready ``ToolDef``.
* :func:`build_agent` — convenience: take a :class:`HarnessConfig` plus
  the harness state container and return an :class:`Agent`.
"""

from __future__ import annotations

import asyncio
import logging
import threading
from typing import Any, Dict, List, Optional, TYPE_CHECKING

from agentspan.agents.tool import ToolDef

from .tools.contract import Tool, ToolResult, ToolUseContext

if TYPE_CHECKING:
    from .runtime import HarnessConfig, HarnessRuntime  # noqa: F401

logger = logging.getLogger("agentspan.harness.conductor_adapter")


# ── Active-harness registry ────────────────────────────────────────────
#
# The conductor SDK's threaded workers (used in our patched mode) can't be
# cleanly terminated when an AgentRuntime shuts down. Stale worker threads
# from a prior HarnessRuntime keep polling the same task names. To avoid
# cross-test contamination, the wrapper resolves the *current* harness for
# its tool name through this registry instead of capturing the harness in
# a closure.
#
# Last-writer-wins per tool name. ``_unregister_active`` lets a closed
# runtime remove itself so a later worker call sees a clean error rather
# than touching a half-closed runtime.

_active_lock = threading.Lock()
_active: Dict[str, "HarnessRuntime"] = {}


def _register_active(harness: "HarnessRuntime") -> None:
    with _active_lock:
        for t in harness.config.tools:
            _active[t.name] = harness


def _unregister_active(harness: "HarnessRuntime") -> None:
    with _active_lock:
        for t in harness.config.tools:
            if _active.get(t.name) is harness:
                _active.pop(t.name, None)


def _resolve_active(tool_name: str) -> Optional["HarnessRuntime"]:
    return _active.get(tool_name)


def wrap_tool_as_tool_def(tool: Tool, harness: "HarnessRuntime") -> ToolDef:
    """Wrap a harness ``Tool`` as a Conductor ``ToolDef``.

    The returned ``ToolDef`` has ``tool_type="worker"`` and a ``func`` that:
      1. Builds a fresh ``ToolUseContext`` from the harness state.
      2. Runs the harness :class:`PermissionEngine` decision.
      3. Runs the ``pre_tool_use`` hook (if a :class:`HookRunner` is wired).
      4. Calls ``tool.call(input, context)``.
      5. Runs the ``post_tool_use`` hook.
      6. Returns the tool's content as the worker output.

    Permission denies, sandbox violations, schema errors, and tool exceptions
    all become ``{is_error: True, content: ...}`` dicts that the LLM sees as
    tool-result errors — never raw exceptions.

    Note on the dynamic signature: the agentspan worker dispatcher inspects
    the function's signature and only forwards parameters that are declared
    by name. We therefore generate a wrapper whose signature matches the
    tool's ``input_schema.properties`` so all declared inputs reach the
    pipeline.
    """
    name = tool.name
    description = tool.description or ""
    input_schema = dict(tool.input_schema or {})

    # Build named parameters from the schema.
    properties = (input_schema.get("properties") or {})
    required = set(input_schema.get("required") or [])
    param_names = list(properties.keys())

    def _runner(**kwargs: Any) -> Dict[str, Any]:
        # Drop framework-injected fields and any None defaults inserted by the
        # dispatcher when an optional schema field is absent from the call.
        kwargs.pop("context", None)
        kwargs.pop("_state_updates", None)
        cleaned = {
            k: v for k, v in kwargs.items()
            if not (v is None and k in properties and k not in required)
        }
        # Resolve the current harness for this tool at call-time. Stale
        # worker threads from a prior test/runtime see the latest registered
        # harness — the closure is only used as the registration anchor.
        active = _resolve_active(name) or harness
        return _run_tool_sync(tool, cleaned, active)

    _runner.__name__ = f"harness_tool_{name}"
    _runner.__qualname__ = _runner.__name__
    _build_signature(_runner, param_names)

    td = ToolDef(
        name=name,
        description=description,
        input_schema=input_schema,
        output_schema={"type": "object"},
        func=_runner,
        tool_type="worker",
    )
    # Honor a per-execution call cap if the embedder set one via
    # tool._max_calls_override (mirrors the ``_limited`` pattern in
    # 100_issue_fixer_agent.py). Conductor's
    # AgentChatCompleteTaskMapper.filterToolsByMaxCalls path enforces it.
    cap = getattr(tool, "_max_calls_override", None)
    if isinstance(cap, int) and cap > 0:
        td.max_calls = cap
    return td


def _build_signature(fn: Any, param_names: List[str]) -> None:
    """Attach a synthetic ``inspect.Signature`` to *fn* so the agentspan
    worker dispatcher (which iterates ``sig.parameters``) forwards each
    declared parameter from the task input.
    """
    import inspect
    params = [
        inspect.Parameter(
            name, inspect.Parameter.KEYWORD_ONLY, default=None,
        )
        for name in param_names
    ]
    fn.__signature__ = inspect.Signature(parameters=params)


def _run_tool_sync(
    tool: Tool, input: Dict[str, Any], harness: "HarnessRuntime"
) -> Dict[str, Any]:
    """Synchronously execute the async pipeline.

    Conductor's worker thread is sync. The harness pipeline is async. We
    bridge with ``asyncio.run`` per call. Each call gets its own loop
    (workers are independent invocations); no shared loop state.
    """
    try:
        return asyncio.run(_run_tool_async(tool, input, harness))
    except RuntimeError as exc:
        # If we're somehow already inside a loop (shouldn't be, but
        # defensively), fall back to a thread.
        if "asyncio.run() cannot be called from a running event loop" in str(exc):
            container: Dict[str, Any] = {}

            def _target() -> None:
                container["v"] = asyncio.new_event_loop().run_until_complete(
                    _run_tool_async(tool, input, harness)
                )

            t = threading.Thread(target=_target)
            t.start()
            t.join()
            return container.get("v", _error_result("worker bridge failed"))
        raise


async def _run_tool_async(
    tool: Tool, input: Dict[str, Any], harness: "HarnessRuntime"
) -> Dict[str, Any]:
    """Run the full per-tool pipeline once. Never raises — every failure mode
    is converted to ``{is_error: True, content: ...}`` so the LLM sees an
    error tool-result rather than a Conductor task failure.
    """
    ctx = ToolUseContext(
        cwd=harness.cwd,
        session_id=harness.session_id,
        abort=harness.abort_event,
        permission_mode=harness.permission_mode_value,
        store=harness.session_store,
    )

    # 1a. JSON Schema validation against the tool's declared input_schema.
    schema_error = _validate_against_schema(input, tool.input_schema)
    if schema_error:
        return _error_result(f"Invalid input for {tool.name}: {schema_error}")

    # 1b. Tool-specific semantic validation (default no-op).
    try:
        validation_error = await tool.validate_input(input, ctx)
    except Exception as exc:  # noqa: BLE001
        return _error_result(f"validate_input raised: {type(exc).__name__}: {exc}")
    if validation_error:
        return _error_result(f"Invalid input for {tool.name}: {validation_error}")

    # 2. Permission.
    try:
        decision = await harness.permission.decide(tool=tool, input=input, context=ctx)
    except Exception as exc:  # noqa: BLE001
        return _error_result(f"permission engine raised: {exc}")
    if decision.behavior == "deny":
        return _error_result(
            f"Permission denied for {tool.name}: {decision.reason or 'no reason'}"
        )
    if decision.behavior == "ask":
        # No interactive ask in v1 — treat as deny so the model can adapt.
        return _error_result(
            f"Permission for {tool.name} requires user approval (not available in v1)"
        )

    # 3. pre_tool_use hook.
    if harness.hook_runner is not None:
        try:
            outcome = await harness.hook_runner.pre_tool_use(
                tool_name=tool.name, input=input, context=ctx
            )
        except Exception as exc:  # noqa: BLE001
            return _error_result(f"pre_tool_use hook raised: {exc}")
        if outcome.blocked:
            return _error_result(
                f"Hook '{outcome.hook_name}' blocked {tool.name}: {outcome.message}"
            )
        if outcome.updated_input is not None:
            input = outcome.updated_input

    # 4. Execute.
    try:
        result: ToolResult = await tool.call(input, ctx)
    except Exception as exc:  # noqa: BLE001
        logger.exception("tool %s raised", tool.name)
        return _error_result(f"{type(exc).__name__}: {exc}")

    # 5. post_tool_use hook (best-effort; never fails the tool result).
    if harness.hook_runner is not None:
        try:
            await harness.hook_runner.post_tool_use(
                tool_name=tool.name, input=input, result=result, context=ctx
            )
        except Exception:  # noqa: BLE001
            logger.exception("post_tool_use hook raised for %s", tool.name)

    # 6. Bound the model-visible content.
    content = result.content
    if isinstance(content, str) and len(content) > tool.max_result_chars:
        truncated = content[: tool.max_result_chars]
        content = (
            truncated
            + f"\n[truncated: {len(result.content) - tool.max_result_chars} more chars omitted]"
        )

    return {
        "result": content,  # the LLM-visible field; Conductor uses output.result
        "is_error": result.is_error,
        "content_ref": result.content_ref,
        "preview": result.preview,
    }


def _error_result(message: str) -> Dict[str, Any]:
    """Shape a tool-error result that the LLM will see, not a worker failure."""
    return {"result": message, "is_error": True, "content_ref": None, "preview": None}


def _validate_against_schema(
    input: Dict[str, Any], schema: Optional[Dict[str, Any]]
) -> Optional[str]:
    """Best-effort JSON Schema validation. Returns an error message or None.

    A missing or empty schema means "anything goes". Validation failure is
    reported as a short message so the model can correct its call.
    """
    if not schema or not isinstance(schema, dict):
        return None
    if schema.get("type") != "object":
        return None
    required = schema.get("required") or []
    if isinstance(required, list):
        for field_name in required:
            if field_name not in input:
                return f"missing required field {field_name!r}"
    # Light type-check on declared properties.
    properties = schema.get("properties") or {}
    if not isinstance(properties, dict):
        return None
    for k, v in input.items():
        spec = properties.get(k)
        if not isinstance(spec, dict):
            continue
        expected = spec.get("type")
        if not expected:
            continue
        if not _matches_type(v, expected):
            return f"field {k!r}: expected {expected}, got {type(v).__name__}"
    return None


def _matches_type(value: Any, expected: Any) -> bool:
    types = expected if isinstance(expected, list) else [expected]
    for t in types:
        if t == "string" and isinstance(value, str):
            return True
        if t == "integer" and isinstance(value, int) and not isinstance(value, bool):
            return True
        if t == "number" and isinstance(value, (int, float)) and not isinstance(value, bool):
            return True
        if t == "boolean" and isinstance(value, bool):
            return True
        if t == "object" and isinstance(value, dict):
            return True
        if t == "array" and isinstance(value, list):
            return True
        if t == "null" and value is None:
            return True
    return False


def build_agent(
    *,
    harness: "HarnessRuntime",
    name: str,
    extra_tools: Optional[List[Any]] = None,
) -> Any:
    """Build an agentspan ``Agent`` that wraps the harness's tools.

    ``extra_tools`` lets callers inject prefab tool defs (e.g. plain ``@tool``
    functions or HTTP/MCP tools) alongside the harness's wrapped tools.
    """
    from agentspan.agents import Agent

    cfg = harness.config
    wrapped: List[Any] = [wrap_tool_as_tool_def(t, harness) for t in cfg.tools]
    if extra_tools:
        wrapped.extend(extra_tools)

    kwargs: Dict[str, Any] = {
        "name": name,
        "model": cfg.model,
        "instructions": cfg.system,
        "tools": wrapped,
        "max_turns": cfg.max_turns,
        # Non-stateful: tool tasks go on the default queue and our
        # in-process workers (registered without a domain) can pick them
        # up. The harness owns its own session state in-process via the
        # SharedStore + session_store; we don't need Conductor's per-
        # execution domain isolation.
        "stateful": False,
    }
    if cfg.max_tokens:
        kwargs["max_tokens"] = cfg.max_tokens
    if cfg.temperature is not None:
        kwargs["temperature"] = cfg.temperature
    if getattr(cfg, "reasoning_effort", None):
        kwargs["reasoning_effort"] = cfg.reasoning_effort
    if getattr(cfg, "credentials", None):
        kwargs["credentials"] = list(cfg.credentials)
    if getattr(cfg, "stop_condition", None) is not None:
        kwargs["stop_when"] = cfg.stop_condition

    return Agent(**kwargs)


__all__ = ["wrap_tool_as_tool_def", "build_agent"]
