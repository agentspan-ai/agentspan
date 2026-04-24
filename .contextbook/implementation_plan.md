## Implementation Plan — Issue #150: Allow retry configuration on @tool decorator

### Root Cause
Currently, `_default_task_def()` in `runtime.py` (line 44-64) hardcodes `retry_count=2` and `retry_delay_seconds=2` for all `@tool` worker tasks. Users have no way to override these values from the SDK. The `@tool` decorator and `ToolDef` dataclass don't expose retry parameters.

### Files to Change

#### 1. `sdk/python/src/agentspan/agents/tool.py`

**A. `ToolDef` dataclass (line 51-82)** — Add two new optional fields after `stateful`:
```python
retry_count: Optional[int] = None
retry_delay_seconds: Optional[int] = None
```

**B. `@overload` signature (lines 92-103)** — Add the two new keyword params:
```python
retry_count: Optional[int] = None,
retry_delay_seconds: Optional[int] = None,
```

**C. Real `tool()` function signature (lines 106-117)** — Add the two new keyword params:
```python
retry_count: Optional[int] = None,
retry_delay_seconds: Optional[int] = None,
```

**D. `_wrap()` inner function (lines 150-163)** — Pass the new params through to `ToolDef(...)`:
```python
retry_count=retry_count,
retry_delay_seconds=retry_delay_seconds,
```

#### 2. `sdk/python/src/agentspan/agents/runtime/runtime.py`

**`_default_task_def()` (lines 44-64)** — Add optional override params:
```python
def _default_task_def(
    name: str,
    *,
    response_timeout_seconds: int = 10,
    retry_count: Optional[int] = None,
    retry_delay_seconds: Optional[int] = None,
) -> Any:
```
And change the hardcoded assignments to use the overrides when provided:
```python
td.retry_count = retry_count if retry_count is not None else 2
td.retry_delay_seconds = retry_delay_seconds if retry_delay_seconds is not None else 2
```

#### 3. `sdk/python/src/agentspan/agents/runtime/tool_registry.py`

**`register_tool_workers()` (line 69-76)** — When calling `_default_task_def()` for each `@tool` worker, pass the per-tool retry overrides from `td.retry_count` / `td.retry_delay_seconds`:
```python
worker_task(
    task_definition_name=td.name,
    task_def=_default_task_def(
        td.name,
        retry_count=td.retry_count,
        retry_delay_seconds=td.retry_delay_seconds,
    ),
    ...
)(wrapper)
```

### No Breaking Changes
- All new params are `Optional[int] = None`, so existing code continues to work unchanged.
- `_default_task_def` still defaults to `retry_count=2` / `retry_delay_seconds=2` when `None` is passed.
- The `@overload` for bare `@tool` (line 88-89) takes no params and needs no change.
