# Implementation Plan — Issue #150: Allow retry configuration on @tool decorator

## Root Cause

Currently, all `@tool` functions get a hardcoded Conductor task definition with `retry_count=2` and `retry_delay_seconds=2` (set in `_default_task_def` in `runtime.py`). Users cannot override these values from the SDK. The `@tool` decorator and `ToolDef` dataclass have no fields for retry configuration, and the `_default_task_def()` function accepts no retry override parameters.

## Files to Change

### 1. `sdk/python/src/agentspan/agents/tool.py`

**ToolDef dataclass (line ~51)** — Add three new optional fields after `stateful`:
```python
retry_count: Optional[int] = None          # None = use server default (2)
retry_delay_seconds: Optional[int] = None  # None = use server default (2)
retry_logic: Optional[str] = None          # None = use server default ("LINEAR_BACKOFF")
                                            # Valid: "FIXED", "LINEAR_BACKOFF", "EXPONENTIAL_BACKOFF"
```

**@tool decorator overload signatures (lines ~92-103)** — Add the three new keyword params to both `@overload` signatures:
```python
retry_count: Optional[int] = None,
retry_delay_seconds: Optional[int] = None,
retry_logic: Optional[str] = None,
```

**@tool decorator implementation (lines ~106-117)** — Add the three new keyword params to the real `def tool(...)` function signature.

**_wrap inner function (lines ~142-163)** — Pass the three new params through to `ToolDef(...)`:
```python
tool_def = ToolDef(
    ...existing params...,
    retry_count=retry_count,
    retry_delay_seconds=retry_delay_seconds,
    retry_logic=retry_logic,
)
```

### 2. `sdk/python/src/agentspan/agents/runtime/runtime.py`

**`_default_task_def()` function (lines 44-64)** — Add optional override parameters:
```python
def _default_task_def(
    name: str,
    *,
    response_timeout_seconds: int = 10,
    retry_count: Optional[int] = None,
    retry_delay_seconds: Optional[int] = None,
    retry_logic: Optional[str] = None,
) -> Any:
    from conductor.client.http.models.task_def import TaskDef

    td = TaskDef(name=name)
    td.retry_count = retry_count if retry_count is not None else 2
    td.retry_logic = retry_logic if retry_logic is not None else "LINEAR_BACKOFF"
    td.retry_delay_seconds = retry_delay_seconds if retry_delay_seconds is not None else 2
    td.timeout_seconds = 0
    td.response_timeout_seconds = response_timeout_seconds
    td.timeout_policy = "RETRY"
    return td
```

Need to add `from typing import Optional` import (already present in the file).

### 3. `sdk/python/src/agentspan/agents/runtime/tool_registry.py`

**`register_tool_workers()` method (lines 65-78)** — Pass per-tool retry config when calling `_default_task_def`:
```python
worker_task(
    task_definition_name=td.name,
    task_def=_default_task_def(
        td.name,
        retry_count=td.retry_count,
        retry_delay_seconds=td.retry_delay_seconds,
        retry_logic=td.retry_logic,
    ),
    ...
)
```

### 4. `sdk/python/src/agentspan/agents/config_serializer.py`

**`_serialize_tool()` method (lines 225-270)** — Add retry fields to the serialized tool config so the server-side compiler can use them:
```python
if td.retry_count is not None:
    if "config" not in result:
        result["config"] = {}
    result["config"]["retryCount"] = td.retry_count
if td.retry_delay_seconds is not None:
    if "config" not in result:
        result["config"] = {}
    result["config"]["retryDelaySeconds"] = td.retry_delay_seconds
if td.retry_logic is not None:
    if "config" not in result:
        result["config"] = {}
    result["config"]["retryLogic"] = td.retry_logic
```

This is needed because the Java server's `ToolCompiler` already reads `retryCount` and `retryDelaySeconds` from the tool config (confirmed in `server/src/main/java/dev/agentspan/runtime/compiler/ToolCompiler.java` lines 318-320 and 1459-1461).

## Sensible Defaults
- `retry_count=None` → 2 (existing default, unchanged)
- `retry_delay_seconds=None` → 2 (existing default, unchanged)
- `retry_logic=None` → "LINEAR_BACKOFF" (existing default, unchanged)
- `retry_count=0` → no retries (fail immediately)

## Conductor TaskDef retry_logic values (from issue link)
- `"FIXED"` — fixed delay between retries
- `"LINEAR_BACKOFF"` — linear backoff (current default)
- `"EXPONENTIAL_BACKOFF"` — exponential backoff

## Test Strategy

### Unit tests (new file: `sdk/python/tests/unit/test_tool_retry.py`)
- `test_tool_decorator_default_retry_fields_are_none` — bare `@tool` has None retry fields
- `test_tool_decorator_retry_count` — `@tool(retry_count=10)` stores 10
- `test_tool_decorator_retry_delay_seconds` — `@tool(retry_delay_seconds=5)` stores 5
- `test_tool_decorator_retry_logic` — `@tool(retry_logic="EXPONENTIAL_BACKOFF")` stores it
- `test_tool_decorator_zero_retries` — `@tool(retry_count=0)` stores 0
- `test_tool_decorator_all_retry_params` — all three together
- `test_default_task_def_uses_tool_retry_config` — `_default_task_def` respects overrides
- `test_default_task_def_uses_defaults_when_none` — None → existing defaults
- `test_serializer_includes_retry_in_config` — config_serializer emits retryCount/retryDelaySeconds/retryLogic

## Risks and Edge Cases
- **Backward compatibility**: All new params default to `None`, so existing code is unaffected.
- **Server-side compilation**: The Java `ToolCompiler` already reads `retryCount` and `retryDelaySeconds` from tool config, so the serializer change ensures server-compiled workflows also respect per-tool retry settings.
- **`_passthrough_task_def`**: This function (line 67-84) also hardcodes retry values but is only used for framework passthrough workers (LangGraph, etc.), not user `@tool` functions. No change needed there.
- **Other callers of `_default_task_def`**: Many system workers (guardrails, stop_when, callbacks, etc.) call `_default_task_def` without retry overrides — they will continue to get the defaults. Only the `tool_registry.py` path passes per-tool overrides.
