# Issue #150 — Allow retry configuration on @tool decorator

## Root Cause

The `@tool` decorator in `sdk/python/src/agentspan/agents/tool.py` does not accept `retry_count` or `retry_delay_seconds` parameters. When tools are registered as Conductor workers in `sdk/python/src/agentspan/agents/runtime/tool_registry.py` (line 71), the call `_default_task_def(td.name)` always produces a `TaskDef` with hardcoded `retry_count=2` and `retry_delay_seconds=2` (defined in `runtime.py` lines 44–65). There is no mechanism to pass user-specified retry values from the `ToolDef` through to `_default_task_def`.

Note: `agent_tool()` already supports `retry_count` and `retry_delay_seconds` by storing them in `ToolDef.config` — but those are forwarded to the *server-side compiler*, not to the Conductor `TaskDef`. For `@tool` (worker-type tools), the retry config must be applied to the `TaskDef` at worker-registration time.

## Files to Change

### 1. `sdk/python/src/agentspan/agents/tool.py`

**What:** Add `retry_count` and `retry_delay_seconds` parameters to the `@tool` decorator and store them on the `ToolDef`.

- **`ToolDef` dataclass (line 52–82):** Add two new optional fields:
  ```python
  retry_count: Optional[int] = None
  retry_delay_seconds: Optional[int] = None
  ```
  Using `None` means "use the default" (currently 2 and 2). This preserves backward compatibility.

- **`@overload` signatures (lines 92–103):** Add `retry_count: Optional[int] = None` and `retry_delay_seconds: Optional[int] = None` to both overload signatures.

- **`tool()` function signature (lines 106–117):** Add `retry_count: Optional[int] = None` and `retry_delay_seconds: Optional[int] = None` as keyword-only parameters.

- **`tool()` docstring (lines 118–140):** Add documentation for the new parameters:
  ```
  retry_count: Number of retries on failure. Defaults to 2 if not specified.
      Set to 0 to disable retries entirely.
  retry_delay_seconds: Seconds between retries (linear backoff). Defaults to 2
      if not specified.
  ```

- **`_wrap()` inner function (lines 150–163):** Pass the new parameters to the `ToolDef` constructor:
  ```python
  tool_def = ToolDef(
      ...
      retry_count=retry_count,
      retry_delay_seconds=retry_delay_seconds,
  )
  ```

### 2. `sdk/python/src/agentspan/agents/runtime/runtime.py`

**What:** Update `_default_task_def` to accept optional `retry_count` and `retry_delay_seconds` parameters.

- **`_default_task_def()` function (lines 44–65):** Change signature to:
  ```python
  def _default_task_def(
      name: str,
      *,
      response_timeout_seconds: int = 10,
      retry_count: Optional[int] = None,
      retry_delay_seconds: Optional[int] = None,
  ) -> Any:
  ```
  Inside the function body, use the provided values or fall back to the existing defaults:
  ```python
  effective_retry_count = retry_count if retry_count is not None else 2
  effective_retry_delay = retry_delay_seconds if retry_delay_seconds is not None else 2
  ```
  Then use `effective_retry_count` and `effective_retry_delay` when constructing the `TaskDef` (replacing the current hardcoded `2` values).

### 3. `sdk/python/src/agentspan/agents/runtime/tool_registry.py`

**What:** Forward `ToolDef.retry_count` and `ToolDef.retry_delay_seconds` to `_default_task_def` when registering worker tools.

- **`register_tools()` function, line 71:** Change:
  ```python
  task_def=_default_task_def(td.name),
  ```
  to:
  ```python
  task_def=_default_task_def(
      td.name,
      retry_count=td.retry_count,
      retry_delay_seconds=td.retry_delay_seconds,
  ),
  ```

### 4. (No change needed) Other call sites of `_default_task_def`

The other call sites in `runtime.py` (lines 767, 2998, 3113) are for framework workers, graph workers, and skill workers — not user `@tool` functions. These should continue using the defaults (passing no retry overrides), which is exactly what happens since the new parameters default to `None`.

## Changes Summary

| File | Function/Class | Change |
|------|---------------|--------|
| `tool.py` | `ToolDef` | Add `retry_count: Optional[int] = None`, `retry_delay_seconds: Optional[int] = None` fields |
| `tool.py` | `tool()` + overloads | Add `retry_count`, `retry_delay_seconds` keyword params; pass to `ToolDef` |
| `runtime.py` | `_default_task_def()` | Accept optional `retry_count`, `retry_delay_seconds`; use them or fall back to 2 |
| `tool_registry.py` | `register_tools()` | Forward `td.retry_count`, `td.retry_delay_seconds` to `_default_task_def()` |

## Test Strategy

### File: `sdk/python/tests/unit/test_tool.py`

Add a new test class or extend existing tests with the following cases:

1. **`test_tool_retry_count_stored_on_tool_def`** — Decorate a function with `@tool(retry_count=5)` and assert `func._tool_def.retry_count == 5`.

2. **`test_tool_retry_delay_stored_on_tool_def`** — Decorate with `@tool(retry_delay_seconds=10)` and assert `func._tool_def.retry_delay_seconds == 10`.

3. **`test_tool_retry_both_params`** — Decorate with `@tool(retry_count=0, retry_delay_seconds=0)` and assert both are stored correctly.

4. **`test_tool_retry_defaults_to_none`** — Bare `@tool` should have `retry_count=None` and `retry_delay_seconds=None` on the `ToolDef`.

5. **`test_default_task_def_uses_defaults`** — Call `_default_task_def("test")` with no retry args and assert the TaskDef has `retry_count=2` and `retry_delay_seconds=2`.

6. **`test_default_task_def_custom_retry`** — Call `_default_task_def("test", retry_count=5, retry_delay_seconds=10)` and assert the TaskDef reflects those values.

7. **`test_default_task_def_zero_retry`** — Call `_default_task_def("test", retry_count=0)` and assert `retry_count=0` (retries disabled).

8. **`test_register_tools_forwards_retry_config`** — Mock `worker_task` and `_default_task_def`, create a `ToolDef` with `retry_count=3, retry_delay_seconds=5`, call `register_tools`, and verify `_default_task_def` was called with those values.

### Validation approach (per CLAUDE.md):
- Write each test first, then verify it fails before the implementation is applied, confirming the test is actually testing the right thing.

## Risks and Edge Cases

1. **Negative values:** Users could pass `retry_count=-1`. We should either validate (raise `ValueError` for negative values) or let Conductor handle it. **Recommendation:** Add a simple validation in `_default_task_def` — raise `ValueError` if `retry_count < 0` or `retry_delay_seconds < 0`.

2. **Type safety:** Users could pass floats or strings. The type hints (`Optional[int]`) provide IDE guidance but no runtime enforcement. The Conductor SDK will likely reject non-int values at registration time, which is acceptable.

3. **Backward compatibility:** Fully preserved — all new parameters default to `None`, and `None` maps to the existing defaults (2, 2). No existing code changes behavior.

4. **`retry_logic` field:** The issue mentions `retry_logic` as a potential future addition. This plan does NOT include it to keep scope minimal. It can be added in a follow-up using the same pattern (add to `ToolDef`, forward through `_default_task_def`).

5. **`agent_tool()` already has retry params:** The `agent_tool()` function (line 1059) already accepts `retry_count` and `retry_delay_seconds` but stores them in `config` dict for server-side use. The `@tool` decorator stores them as first-class `ToolDef` fields instead, because they need to be forwarded to the Conductor `TaskDef` at worker-registration time. These are two different mechanisms for two different tool types — no conflict.
