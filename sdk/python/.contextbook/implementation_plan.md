## Implementation Plan — Issue #150: Allow retry configuration on @tool decorator

### Step 1 — `sdk/python/src/agentspan/agents/tool.py`

**A. `ToolDef` dataclass** — add two new optional fields after `stateful`:
```python
retry_count: Optional[int] = None
retry_delay_seconds: Optional[int] = None
```

**B. First `@overload` signature** — add keyword-only params:
```python
@overload
def tool(
    *,
    name: Optional[str] = None,
    external: bool = False,
    approval_required: bool = False,
    timeout_seconds: Optional[int] = None,
    guardrails: Optional[List[Any]] = None,
    isolated: bool = True,
    credentials: Optional[List[Any]] = None,
    stateful: bool = False,
    retry_count: Optional[int] = None,
    retry_delay_seconds: Optional[int] = None,
) -> Callable[[F], F]: ...
```

**C. `tool()` implementation signature** — same two new params with `None` defaults.

**D. `_wrap(fn)` inner function** — pass them to `ToolDef(...)`:
```python
tool_def = ToolDef(
    ...
    stateful=stateful,
    retry_count=retry_count,
    retry_delay_seconds=retry_delay_seconds,
)
```

---

### Step 2 — `sdk/python/src/agentspan/agents/runtime/runtime.py`

**`_default_task_def`** — add two optional keyword params and use them:
```python
def _default_task_def(
    name: str,
    *,
    response_timeout_seconds: int = 10,
    retry_count: Optional[int] = None,
    retry_delay_seconds: Optional[int] = None,
) -> Any:
    ...
    td.retry_count = retry_count if retry_count is not None else 2
    td.retry_logic = "LINEAR_BACKOFF"
    td.retry_delay_seconds = retry_delay_seconds if retry_delay_seconds is not None else 2
    ...
```

---

### Step 3 — `sdk/python/src/agentspan/agents/runtime/tool_registry.py`

**`register_tool_workers`** — pass per-tool retry values when calling `_default_task_def`:
```python
worker_task(
    task_definition_name=td.name,
    task_def=_default_task_def(
        td.name,
        retry_count=td.retry_count,
        retry_delay_seconds=td.retry_delay_seconds,
    ),
    register_task_def=True,
    overwrite_task_def=True,
    domain=domain if (agent_stateful or td.stateful) else None,
    lease_extend_enabled=True,
)(wrapper)
```

---

### Step 4 — `sdk/python/tests/unit/test_tool.py`

Add new test class `TestToolDecoratorRetryConfig`:
- `test_retry_count_and_delay_stored_on_tooldef` — `@tool(retry_count=10, retry_delay_seconds=5)` → `td.retry_count == 10`, `td.retry_delay_seconds == 5`
- `test_retry_count_zero_stored` — `@tool(retry_count=0)` → `td.retry_count == 0`
- `test_bare_tool_has_none_retry_fields` — `@tool` → `td.retry_count is None`, `td.retry_delay_seconds is None`
- `test_default_task_def_uses_retry_overrides` — call `_default_task_def("x", retry_count=5, retry_delay_seconds=10)` and assert `td.retry_count == 5`, `td.retry_delay_seconds == 10`
- `test_default_task_def_falls_back_to_defaults` — call `_default_task_def("x")` and assert `td.retry_count == 2`, `td.retry_delay_seconds == 2`
