# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""Tool execution workers for native function calling.

This file deliberately does NOT use ``from __future__ import annotations``
because the Conductor worker framework needs real type objects (not strings)
for parameter type resolution.
"""

import inspect
import json
import logging
import os
import threading
from dataclasses import asdict, is_dataclass
from types import SimpleNamespace

logger = logging.getLogger("agentspan.agents.dispatch")


class ToolSerializationError(TypeError):
    """Raised when a tool returns a value that cannot be JSON-serialized."""

    pass


def _validate_serializable(tool_name, result):
    """Validate that a tool result is JSON-serializable. Raises ToolSerializationError if not."""
    if result is None or isinstance(result, (str, int, float, bool)):
        return
    try:
        json.dumps(result)
    except (TypeError, ValueError) as exc:
        result_type = type(result).__name__
        raise ToolSerializationError(
            f"Tool '{tool_name}' returned a non-serializable type '{result_type}'. "
            f"Return dict, str, int, float, list, or bool. Error: {exc}"
        ) from None


def _is_framework_callable(tool_func) -> bool:
    return bool(getattr(tool_func, "_agentspan_framework_callable", False))


def _to_namespace(value):
    if isinstance(value, dict):
        return SimpleNamespace(**{k: _to_namespace(v) for k, v in value.items()})
    if isinstance(value, list):
        return [_to_namespace(v) for v in value]
    return value


def _normalize_framework_kwargs(kwargs):
    normalized = dict(kwargs)
    for key in ("ctx", "context", "agent"):
        if key in normalized and isinstance(normalized[key], dict):
            normalized[key] = _to_namespace(normalized[key])
    return normalized


def _normalize_framework_result(value):
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, dict):
        return {str(k): _normalize_framework_result(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set, frozenset)):
        return [_normalize_framework_result(v) for v in value]
    if is_dataclass(value):
        return _normalize_framework_result(asdict(value))
    if hasattr(value, "model_dump"):
        try:
            return _normalize_framework_result(value.model_dump())
        except Exception:
            pass
    if hasattr(value, "dict"):
        try:
            return _normalize_framework_result(value.dict())
        except Exception:
            pass
    if hasattr(value, "__dict__"):
        try:
            return _normalize_framework_result(
                {k: v for k, v in vars(value).items() if not k.startswith("_")}
            )
        except Exception:
            pass
    return value


def _coerce_value(value, annotation):
    """Coerce a raw value to match the expected type annotation."""
    if value is None or annotation is inspect.Parameter.empty:
        return value

    import typing

    origin = getattr(annotation, "__origin__", None)
    args = getattr(annotation, "__args__", ())

    # Unwrap Optional[X] → X
    if origin is getattr(typing, "Union", None):
        non_none = [a for a in args if a is not type(None)]
        if len(non_none) == 1:
            return _coerce_value(value, non_none[0])
        return value

    # Already correct type — short-circuit
    target = origin if origin is not None else annotation
    try:
        if isinstance(value, target):
            return value
    except TypeError:
        return value

    # String → list/dict: json.loads
    if isinstance(value, str) and target in (list, dict):
        try:
            parsed = json.loads(value)
            if isinstance(parsed, target):
                return parsed
        except (json.JSONDecodeError, ValueError):
            pass
        return value

    # dict/list → str: json.dumps
    # Conductor delivers AI_MODEL tool arguments as already-parsed objects.
    # Tools that expect a JSON string and call json.loads() internally will
    # fail with "the JSON object must be str, bytes or bytearray, not dict"
    # unless we re-serialise here.
    if isinstance(value, (dict, list)) and target is str:
        try:
            return json.dumps(value)
        except (TypeError, ValueError):
            return str(value)

    # String → int/float/bool
    if isinstance(value, str):
        if annotation is int:
            try:
                return int(value)
            except (ValueError, TypeError):
                pass
        elif annotation is float:
            try:
                return float(value)
            except (ValueError, TypeError):
                pass
        elif annotation is bool:
            lower = value.lower().strip()
            if lower in ("true", "1", "yes"):
                return True
            if lower in ("false", "0", "no"):
                return False

    return value


# Lazily created credential fetcher — initialized from AgentConfig on first use
_credential_fetcher = None


def _get_credential_fetcher():
    """Return the module-level WorkerCredentialFetcher, creating it on first call.

    The fetcher is initialized from AgentConfig.from_env() so it picks up
    AGENTSPAN_SERVER_URL, AGENTSPAN_API_KEY, AGENTSPAN_CREDENTIAL_STRICT_MODE.
    """
    global _credential_fetcher
    if _credential_fetcher is None:
        from agentspan.agents.runtime.config import AgentConfig
        from agentspan.agents.runtime.credentials.fetcher import WorkerCredentialFetcher

        config = AgentConfig.from_env()
        _credential_fetcher = WorkerCredentialFetcher(
            server_url=config.server_url,
            strict_mode=config.credential_strict_mode,
            api_key=config.api_key or config.auth_key,
        )
    return _credential_fetcher


def _extract_execution_token(task) -> str | None:
    """Extract __agentspan_ctx__.execution_token from a Conductor task.

    Checks task.input_data first (most common), then task.workflow_input.
    Returns None if not present.
    """
    # input_data is the primary source (set by Conductor enrichment scripts)
    ctx = (task.input_data or {}).get("__agentspan_ctx__")
    if isinstance(ctx, dict):
        return ctx.get("execution_token") or None
    if isinstance(ctx, str) and ctx:
        return ctx
    # Fallback: check workflow_input (set at workflow start)
    ctx = (getattr(task, "workflow_input", None) or {}).get("__agentspan_ctx__")
    if isinstance(ctx, dict):
        return ctx.get("execution_token") or None
    if isinstance(ctx, str) and ctx:
        return ctx
    return None


def _get_credential_names_from_tool(tool_func) -> list:
    """Extract credential names from a @tool-decorated function's ToolDef.

    Returns empty list if the function has no _tool_def attribute.
    """
    tool_def = getattr(tool_func, "_tool_def", None)
    if tool_def is None:
        return []
    return list(getattr(tool_def, "credentials", []))


def _is_isolated(tool_func) -> bool:
    """Return the isolated flag from a @tool-decorated function's ToolDef.

    Defaults to True (safe default) if no ToolDef is present.
    """
    tool_def = getattr(tool_func, "_tool_def", None)
    if tool_def is None:
        return True
    return getattr(tool_def, "isolated", True)


# Module-level registry: task_name -> {tool_name: tool_func}
_tool_registry = {}

# Module-level ToolDef registry: tool_name -> ToolDef
# Used to pass credential/isolation metadata to tool_worker without closures
# (closures are not picklable across spawn-mode multiprocessing boundaries).
_tool_def_registry = {}

# Server-side tool registry: tool_name -> {"type": "http"|"mcp", "config": {...}}
_tool_type_registry = {}

# Workflow-level credential names: workflow_instance_id -> [credential_names]
# Fallback for framework-extracted tools that have no tool_def.
_workflow_credentials = {}
_workflow_credentials_lock = threading.Lock()

# MCP server configs: [{"server_url": ..., "headers": ...}]
_mcp_servers = []

# Per-tool consecutive error count for circuit breaker
_tool_error_counts = {}

# Approval-required flags: tool_name -> bool
_tool_approval_flags = {}

# Maps tool_name -> Conductor task definition name for DynamicTask resolution
_tool_task_names = {}

# Maximum consecutive failures before disabling a tool
_CIRCUIT_BREAKER_THRESHOLD = 10

# Current execution context for ToolContext injection
_current_context = {}


def reset_circuit_breaker(tool_name: str) -> None:
    """Reset the consecutive error count for a specific tool."""
    _tool_error_counts.pop(tool_name, None)


def reset_all_circuit_breakers() -> None:
    """Reset all tool error counts (e.g., between agent runs)."""
    _tool_error_counts.clear()


def _needs_context(func):
    """Check if a function declares a 'context' parameter with ToolContext type."""
    try:
        sig = inspect.signature(func)
        return "context" in sig.parameters
    except (ValueError, TypeError):
        return False


def make_tool_worker(tool_func, tool_name, guardrails=None, tool_def=None):
    """Create a Conductor worker wrapper for a @tool function.

    The wrapper accepts a ``Task`` object so it can extract metadata
    (execution ID) for ``ToolContext`` injection, then maps the task's
    ``inputParameters`` to the tool function's arguments.
    On failure the exception propagates so Conductor marks the task FAILED.

    If *guardrails* are provided, they wrap the tool execution:
    - Pre-execution guardrails check the input parameters.
    - Post-execution guardrails check the tool result.
    """
    # Store tool_def in module-level registry so it's accessible across
    # spawn-mode multiprocessing boundaries (closures are not picklable).
    if tool_def is not None:
        _tool_def_registry[tool_name] = tool_def
    # Resolve PEP 563 string annotations (from __future__ import annotations)
    # to real types so downstream code can use isinstance().
    import typing

    try:
        tool_func.__annotations__ = typing.get_type_hints(tool_func)
    except Exception:
        pass

    from conductor.client.http.models import Task, TaskResult
    from conductor.client.http.models.task_result_status import TaskResultStatus

    def _execute(kwargs, execution_id="", agent_state=None):
        """Core execution logic shared by both Task-based and kwargs-based paths."""
        # Circuit breaker: disable tool after N consecutive failures
        if _tool_error_counts.get(tool_name, 0) >= _CIRCUIT_BREAKER_THRESHOLD:
            raise RuntimeError(
                f"Tool '{tool_name}' disabled after {_CIRCUIT_BREAKER_THRESHOLD} "
                "consecutive failures (circuit breaker open)"
            )

        ctx = None
        if _needs_context(tool_func):
            from agentspan.agents.tool import ToolContext

            state = dict(agent_state) if agent_state else {}
            ctx = ToolContext(
                execution_id=execution_id,
                agent_name=_current_context.get("agent_name", ""),
                session_id=_current_context.get("session_id", ""),
                metadata=_current_context.get("metadata", {}),
                dependencies=_current_context.get("dependencies", {}),
                state=state,
            )
            kwargs["context"] = ctx

        # Pre-execution guardrails: check input parameters
        if guardrails:
            input_str = json.dumps(kwargs, default=str)
            for guard in guardrails:
                if guard.position == "input":
                    check_result = guard.check(input_str)
                    if not check_result.passed:
                        if guard.on_fail == "raise":
                            raise ValueError(
                                f"Tool guardrail '{guard.name}' blocked execution: "
                                f"{check_result.message}"
                            )
                        return {
                            "error": f"Blocked by guardrail '{guard.name}': {check_result.message}",
                            "blocked": True,
                        }

        call_kwargs = kwargs
        if _is_framework_callable(tool_func):
            call_kwargs = _normalize_framework_kwargs(kwargs)

        result = tool_func(**call_kwargs)
        if _is_framework_callable(tool_func):
            result = _normalize_framework_result(result)

        # Validate result is JSON-serializable before proceeding
        _validate_serializable(tool_name, result)

        # Post-execution guardrails: check tool result
        if guardrails:
            result_str = json.dumps(result) if not isinstance(result, str) else result
            for guard in guardrails:
                if guard.position == "output":
                    check_result = guard.check(result_str)
                    if not check_result.passed:
                        if guard.on_fail == "fix" and check_result.fixed_output is not None:
                            result = check_result.fixed_output
                            result_str = (
                                json.dumps(result) if not isinstance(result, str) else result
                            )
                        elif guard.on_fail == "raise":
                            raise ValueError(
                                f"Tool guardrail '{guard.name}' failed: {check_result.message}"
                            )
                        else:
                            result = {
                                "error": f"Output blocked by guardrail '{guard.name}': {check_result.message}",
                                "blocked": True,
                            }

        # Capture ToolContext.state mutations for server-side persistence
        if ctx is not None and ctx.state:
            state_updates = dict(ctx.state)
            if isinstance(result, dict):
                result["_state_updates"] = state_updates
            else:
                result = {"result": result, "_state_updates": state_updates}

        _tool_error_counts[tool_name] = 0
        return result

    def tool_worker(task: Task) -> TaskResult:
        """Worker wrapper that receives a Task object from Conductor."""
        task_result = TaskResult(
            task_id=task.task_id,
            workflow_instance_id=task.workflow_instance_id,
            worker_id="agent-sdk",
        )
        try:
            # Extract server-side agent state (injected by enrichment script)
            agent_state = task.input_data.pop("_agent_state", None) or {}

            # ── Credential fetching ───────────────────────────────────────
            # Look up tool_def from multiple sources:
            # 1. Module-level registry (works with fork, not spawn)
            # 2. Closure variable tool_def (works with fork)
            # 3. _tool_def attribute on tool_func (works everywhere)
            _td = _tool_def_registry.get(tool_name) or tool_def
            raw_credentials = list(getattr(_td, "credentials", [])) if _td else _get_credential_names_from_tool(tool_func)
            # Normalize: CredentialFile → env_var string, keep strings as-is
            from agentspan.agents.runtime.credentials.types import CredentialFile
            credential_names = [
                c.env_var if isinstance(c, CredentialFile) else c
                for c in raw_credentials
                if isinstance(c, (str, CredentialFile))
            ]
            # Fallback: workflow-level credentials (for framework-extracted tools)
            if not credential_names and task.workflow_instance_id:
                with _workflow_credentials_lock:
                    credential_names = list(_workflow_credentials.get(task.workflow_instance_id, []))
            resolved_credentials = {}
            if credential_names:
                token = _extract_execution_token(task)
                fetcher = _get_credential_fetcher()
                try:
                    resolved_credentials = fetcher.fetch(token, credential_names)
                except Exception as cred_err:
                    # Credential errors are configuration issues — non-retryable.
                    logger.error("Credential resolution failed for tool '%s': %s", tool_name, cred_err)
                    task_result.status = TaskResultStatus.FAILED_WITH_TERMINAL_ERROR
                    task_result.reason_for_incompletion = str(cred_err)
                    return task_result

            # Map task input to function kwargs
            sig = inspect.signature(tool_func)
            fn_kwargs = {}
            for param_name in sig.parameters:
                if param_name == "context":
                    continue
                if param_name in task.input_data:
                    raw_value = task.input_data[param_name]
                    ann = tool_func.__annotations__.get(param_name, inspect.Parameter.empty)
                    fn_kwargs[param_name] = _coerce_value(raw_value, ann)
                elif sig.parameters[param_name].default is not inspect.Parameter.empty:
                    fn_kwargs[param_name] = sig.parameters[param_name].default
                else:
                    fn_kwargs[param_name] = None

            # ── Credential injection ──────────────────────────────────────
            # Inject credentials into os.environ for the tool to read.
            # Conductor workers default to thread_count=1, so concurrent
            # credential injection is not a risk. Clean up in finally block.
            _injected_env_keys = []
            if resolved_credentials:
                for k, v in resolved_credentials.items():
                    if isinstance(v, str):
                        os.environ[k] = v
                        _injected_env_keys.append(k)

                # Also set credential context for non-isolated tools using get_credential()
                from agentspan.agents.runtime.credentials.accessor import (
                    clear_credential_context,
                    set_credential_context,
                )
                set_credential_context(resolved_credentials)

            try:
                result = _execute(
                    fn_kwargs,
                    execution_id=task.workflow_instance_id or "",
                    agent_state=agent_state,
                )
            finally:
                # Clean up injected env vars
                for k in _injected_env_keys:
                    os.environ.pop(k, None)
                if resolved_credentials:
                    from agentspan.agents.runtime.credentials.accessor import clear_credential_context
                    clear_credential_context()

            if isinstance(result, dict):
                task_result.output_data = result
            else:
                task_result.output_data = {"result": result}
            task_result.status = TaskResultStatus.COMPLETED
            return task_result
        except Exception as e:
            _tool_error_counts[tool_name] = _tool_error_counts.get(tool_name, 0) + 1
            logger.error(
                "Tool '%s' failed (count=%d): %s", tool_name, _tool_error_counts[tool_name], e
            )
            from agentspan.agents.cli_config import TerminalToolError

            if isinstance(e, TerminalToolError):
                task_result.status = TaskResultStatus.FAILED_WITH_TERMINAL_ERROR
            else:
                task_result.status = TaskResultStatus.FAILED
            task_result.reason_for_incompletion = str(e)
            return task_result

    tool_worker.__name__ = tool_func.__name__
    tool_worker.__qualname__ = tool_func.__qualname__
    tool_worker.__doc__ = tool_func.__doc__
    return tool_worker


# ── Native function calling workers ─────────────────────────────────────


def check_approval_worker(tool_calls: object = None, _unused: str = "") -> object:
    """Check whether any tool in the batch requires human approval.

    Looks up each tool name in the ``_tool_approval_flags`` registry.
    Returns ``{needs_approval: True/False}``.
    """
    tool_calls = tool_calls or []
    for tc in tool_calls:
        name = tc.get("name", "")
        if _tool_approval_flags.get(name, False):
            return {"needs_approval": True}
    return {"needs_approval": False}
