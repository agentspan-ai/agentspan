# Issue #150 — Allow retry configuration on @tool decorator

## Root Cause

The `@tool` decorator in `sdk/python/src/agentspan/agents/tool.py` does not accept any retry-related parameters (`retry_count`, `retry_delay_seconds`, `retry_logic`, `timeout_policy`). When tools are registered as Conductor workers in `sdk/python/src/agentspan/agents/runtime/tool_registry.py` (line 71), the call to `_default_task_def(td.name)` in `runtime.py` always hardcodes `retry_count=2`, `retry_logic="LINEAR_BACKOFF"`, `retry_delay_seconds=2`, and `timeout_policy="RETRY"`. There is no mechanism for user-specified values on the `ToolDef` to flow through to the `TaskDef`.

The `agent_tool()` function already supports `retry_count` and `retry_delay_seconds` via its `config` dict, but the `@tool` decorator and the `ToolDef` dataclass have no such fields, and `_default_task_def` has no parameters for them.

## Files to Change

### 1. `sdk/python/src/agentspan/agents/tool.py`

**a) `ToolDef` dataclass (line 52–82)** — Add four new optional fields:

```python
retry_count: Optional[int] = None
retry_delay_seconds: Optional[int] = None
retry_logic: Optional[str] = None        # e.g. "LINEAR_BACKOFF", "FIXED", "EXPONENTIAL_BACKOFF"
timeout_policy: Optional[str] = None      # e.g. "RETRY", "TIME_OUT_WF", "ALERT_ONLY"
```

Place them after `timeout_seconds` (line 76) and before `tool_type` (line 77). All default to `None`, meaning "use the runtime default" (preserving backward compatibility).

**b) `tool()` function signature (lines 92–117)** — Add the same four optional parameters to both `@overload` signatures and the implementation:

```python
retry_count: Optional[int] = None,
retry_delay_seconds: Optional[int] = None,
retry_logic: Optional[str] = None,
timeout_policy: Optional[str] = None,
```

**c) `_wrap()` inner function (line 150–163)** — Pass the new parameters through to the `ToolDef` constructor:

```python
tool_def = ToolDef(
    ...
    retry_count=retry_count,
    retry_delay_seconds=retry_delay_seconds,
    retry_logic=retry_logic,
    timeout_policy=timeout_policy,
    ...
)
```

### 2. `sdk/python/src/agentspan/agents/runtime/runtime.py`

**`_default_task_def()` (line 44–64)** — Add optional keyword arguments that override the hardcoded defaults:

```python
def _default_task_def(
    name: str,
    *,
    response_timeout_seconds: int = 10,
    retry_count: int = 2,
    retry_delay_seconds: int = 2,
    retry_logic: str = "LINEAR_BACKOFF",
    timeout_policy: str = "RETRY",
) -> Any:
```

Then use these parameters instead of the hardcoded values:

```python
td.retry_count = retry_count
td.retry_logic = retry_logic
td.retry_delay_seconds = retry_delay_seconds
td.timeout_policy = timeout_policy
```

### 3. `sdk/python/src/agentspan/agents/runtime/tool_registry.py`

**`register_tool_workers()` (line 69–76)** — When calling `_default_task_def`, pass through any non-`None` retry fields from the `ToolDef`:

```python
# Build kwargs for _default_task_def from ToolDef retry overrides
task_def_kwargs: dict = {}
if td.retry_count is not None:
    task_def_kwargs["retry_count"] = td.retry_count
if td.retry_delay_seconds is not None:
    task_def_kwargs["retry_delay_seconds"] = td.retry_delay_seconds
if td.retry_logic is not None:
    task_def_kwargs["retry_logic"] = td.retry_logic
if td.timeout_policy is not None:
    task_def_kwargs["timeout_policy"] = td.timeout_policy

worker_task(
    task_definition_name=td.name,
    task_def=_default_task_def(td.name, **task_def_kwargs),
    register_task_def=True,
    overwrite_task_def=True,
    domain=domain if (agent_stateful or td.stateful) else None,
    lease_extend_enabled=True,
)(wrapper)
```

## Test Strategy

### File: `sdk/python/tests/unit/test_tool.py`

Add a new test class `TestToolRetryConfig` with the following tests:

1. **`test_default_retry_fields_are_none`** — A bare `@tool` decorated function should have `retry_count`, `retry_delay_seconds`, `retry_logic`, and `timeout_policy` all set to `None` on its `ToolDef`.

2. **`test_retry_count_set`** — `@tool(retry_count=5)` should produce a `ToolDef` with `retry_count=5` and other retry fields as `None`.

3. **`test_retry_delay_seconds_set`** — `@tool(retry_delay_seconds=10)` should produce a `ToolDef` with `retry_delay_seconds=10`.

4. **`test_retry_logic_set`** — `@tool(retry_logic="EXPONENTIAL_BACKOFF")` should produce a `ToolDef` with `retry_logic="EXPONENTIAL_BACKOFF"`.

5. **`test_timeout_policy_set`** — `@tool(timeout_policy="TIME_OUT_WF")` should produce a `ToolDef` with `timeout_policy="TIME_OUT_WF"`.

6. **`test_disable_retries`** — `@tool(retry_count=0)` should produce a `ToolDef` with `retry_count=0` (idempotency-sensitive use case from the issue).

7. **`test_all_retry_fields_combined`** — `@tool(retry_count=5, retry_delay_seconds=10, retry_logic="FIXED", timeout_policy="ALERT_ONLY")` should set all four fields correctly.

8. **`test_retry_fields_with_other_params`** — `@tool(name="custom", approval_required=True, retry_count=3)` should set both the existing and new fields correctly.

### File: `sdk/python/tests/unit/test_runtime_task_def.py` (new file)

1. **`test_default_task_def_defaults`** — Call `_default_task_def("test")` with no overrides and verify `retry_count=2`, `retry_delay_seconds=2`, `retry_logic="LINEAR_BACKOFF"`, `timeout_policy="RETRY"`.

2. **`test_default_task_def_custom_retry_count`** — Call `_default_task_def("test", retry_count=5)` and verify `retry_count=5`, other fields at defaults.

3. **`test_default_task_def_zero_retries`** — Call `_default_task_def("test", retry_count=0)` and verify `retry_count=0`.

4. **`test_default_task_def_all_overrides`** — Call with all four overrides and verify each is applied.

### File: `sdk/python/tests/unit/test_tool_registry.py` (new or extend existing)

1. **`test_register_tool_with_retry_overrides`** — Mock `worker_task` and `_default_task_def`, create a `ToolDef` with `retry_count=5`, register it, and verify `_default_task_def` was called with `retry_count=5`.

2. **`test_register_tool_without_retry_overrides`** — Create a `ToolDef` with all retry fields as `None`, register it, and verify `_default_task_def` was called with no extra kwargs (defaults apply).

## Risks and Edge Cases

1. **Backward compatibility** — All new fields default to `None`, and `_default_task_def` preserves its current defaults when no overrides are passed. Existing code is unaffected.

2. **Invalid retry_logic / timeout_policy values** — Conductor will reject invalid strings at registration time. We could add validation, but the issue doesn't request it and Conductor's error messages are clear. Consider adding validation in a follow-up.

3. **`_passthrough_task_def`** — This function (line 67–84 in `runtime.py`) also hardcodes retry values but is used for framework-internal passthrough workers, not user-facing tools. It should NOT be changed — users don't control passthrough workers.

4. **`agent_tool()` already has retry fields in `config`** — The `agent_tool()` function stores retry config in the `config` dict (not as `ToolDef` fields). This is a different code path (sub-workflow retry, not task-level retry). No change needed there, but the two mechanisms should be documented as distinct.

5. **Overload type hints** — Both `@overload` signatures for `tool()` must be updated to include the new parameters, or type checkers will flag them.

6. **`http_tool()`, `mcp_tool()`, `api_tool()`** — These are server-side tools and don't go through `_default_task_def`. Retry config for them would be a separate feature. No change needed.
