# Issue #167 — Allow retry configuration on @tool decorator

## Root Cause

The `@tool` decorator in the Python SDK does not accept `retry_count` or `retry_delay_seconds` parameters. When tools are registered as Conductor workers in `tool_registry.py` (line 71), the call to `_default_task_def(td.name)` always creates a `TaskDef` with hardcoded `retry_count=2` and `retry_delay_seconds=2` (set in `runtime.py:44-65`). There is no mechanism to pass user-specified retry values from the `@tool` decorator through the `ToolDef` dataclass to the `_default_task_def` function.

Notably, `agent_tool()` already supports `retry_count` and `retry_delay_seconds` (stored in `td.config`), but these are used differently — they go into the workflow config, not the Conductor `TaskDef`. The `@tool` decorator needs its own path to influence the `TaskDef` retry settings.

The TypeScript SDK's `tool()` function (in `sdk/typescript/src/tool.ts`) does **not** currently support retry parameters either — the issue mentions "sdks" (plural), but the TS `tool()` doesn't have this feature. We should add it to both SDKs for parity.

## Files to Change

### Python SDK

1. **`sdk/python/src/agentspan/agents/tool.py`** — `ToolDef` dataclass + `tool()` function
2. **`sdk/python/src/agentspan/agents/runtime/runtime.py`** — `_default_task_def()` function
3. **`sdk/python/src/agentspan/agents/runtime/tool_registry.py`** — `register_tools()` call site
4. **`sdk/python/tests/unit/test_tool.py`** — New unit tests

### TypeScript SDK

5. **`sdk/typescript/src/tool.ts`** — `tool()` function options
6. **`sdk/typescript/src/types.ts`** — `ToolDef` interface

## Detailed Changes

### 1. `sdk/python/src/agentspan/agents/tool.py`

#### a. Add fields to `ToolDef` dataclass (line ~82, after `stateful`)

```python
retry_count: Optional[int] = None
retry_delay_seconds: Optional[int] = None
```

These are `Optional[int]` so that `None` means "use the default" (currently 2/2).

#### b. Add parameters to `tool()` function signature

In all three places — the two `@overload` signatures (lines 92-103 and 106-117) and the actual implementation:

```python
retry_count: Optional[int] = None,
retry_delay_seconds: Optional[int] = None,
```

Add after `stateful: bool = False`.

#### c. Pass values through in `_wrap()` (line 150-163)

Add to the `ToolDef(...)` constructor call:

```python
retry_count=retry_count,
retry_delay_seconds=retry_delay_seconds,
```

#### d. Add import for `Optional` if not already present

Check the imports at the top — `Optional` is already imported (used in the function signatures).

### 2. `sdk/python/src/agentspan/agents/runtime/runtime.py`

#### Modify `_default_task_def()` (line 44-65)

Add `retry_count` and `retry_delay_seconds` as optional keyword arguments with defaults matching the current hardcoded values:

```python
def _default_task_def(
    name: str,
    *,
    response_timeout_seconds: int = 10,
    retry_count: int = 2,
    retry_delay_seconds: int = 2,
) -> Any:
```

Then use these parameters instead of the hardcoded values in the `TaskDef` construction (lines ~57-62):

```python
td.retry_count = retry_count
td.retry_delay_seconds = retry_delay_seconds
```

### 3. `sdk/python/src/agentspan/agents/runtime/tool_registry.py`

#### Modify the `_default_task_def` call (line 71)

Change from:
```python
task_def=_default_task_def(td.name),
```

To:
```python
task_def=_default_task_def(
    td.name,
    **({"retry_count": td.retry_count} if td.retry_count is not None else {}),
    **({"retry_delay_seconds": td.retry_delay_seconds} if td.retry_delay_seconds is not None else {}),
),
```

This preserves the existing defaults (2/2) when the user doesn't specify values, and passes through user values when they do. An alternative cleaner approach:

```python
task_def_kwargs = {}
if td.retry_count is not None:
    task_def_kwargs["retry_count"] = td.retry_count
if td.retry_delay_seconds is not None:
    task_def_kwargs["retry_delay_seconds"] = td.retry_delay_seconds
task_def=_default_task_def(td.name, **task_def_kwargs),
```

### 4. `sdk/typescript/src/tool.ts`

#### Add `retryCount` and `retryDelaySeconds` to the `tool()` options

Find the `tool()` function's options interface/type and add:

```typescript
retryCount?: number;
retryDelaySeconds?: number;
```

Then pass these through to the returned `ToolDef` object's fields (see step 5 below).

### 5. `sdk/typescript/src/types.ts`

#### Add fields to `ToolDef` interface (line ~267, after `stateful`)

```typescript
/** Number of retries on failure. Default 2. Set to 0 to disable retries. */
retryCount?: number;
/** Delay between retries in seconds. Default 2. */
retryDelaySeconds?: number;
```

### 6. `sdk/python/tests/unit/test_tool.py`

Add a new test class after the existing `TestAgentToolRetryConfig` (line ~512):

```python
class TestToolDecoratorRetryConfig:
    """Test @tool decorator retry configuration."""

    def test_default_has_no_retry_overrides(self):
        """By default, retry fields are None (use system defaults)."""
        @tool
        def my_tool() -> str:
            """A tool."""
            return "ok"
        td = my_tool._tool_def
        assert td.retry_count is None
        assert td.retry_delay_seconds is None

    def test_retry_count_passed(self):
        """Custom retry_count is stored on ToolDef."""
        @tool(retry_count=5, retry_delay_seconds=10)
        def my_tool() -> str:
            """A tool."""
            return "ok"
        td = my_tool._tool_def
        assert td.retry_count == 5
        assert td.retry_delay_seconds == 10

    def test_zero_retries(self):
        """retry_count=0 disables retries (e.g. payment processing)."""
        @tool(retry_count=0)
        def payment_tool() -> str:
            """Process payment."""
            return "done"
        td = payment_tool._tool_def
        assert td.retry_count == 0
        assert td.retry_delay_seconds is None

    def test_retry_only_delay(self):
        """Can set retry_delay_seconds without retry_count."""
        @tool(retry_delay_seconds=30)
        def slow_tool() -> str:
            """Slow tool."""
            return "ok"
        td = slow_tool._tool_def
        assert td.retry_count is None
        assert td.retry_delay_seconds == 30
```

Also add a unit test for `_default_task_def`:

```python
class TestDefaultTaskDefRetryParams:
    """Test _default_task_def accepts retry overrides."""

    def test_default_values(self):
        from agentspan.agents.runtime.runtime import _default_task_def
        td = _default_task_def("test_task")
        assert td.retry_count == 2
        assert td.retry_delay_seconds == 2

    def test_custom_retry_count(self):
        from agentspan.agents.runtime.runtime import _default_task_def
        td = _default_task_def("test_task", retry_count=5)
        assert td.retry_count == 5
        assert td.retry_delay_seconds == 2  # default preserved

    def test_zero_retries(self):
        from agentspan.agents.runtime.runtime import _default_task_def
        td = _default_task_def("test_task", retry_count=0)
        assert td.retry_count == 0

    def test_custom_delay(self):
        from agentspan.agents.runtime.runtime import _default_task_def
        td = _default_task_def("test_task", retry_delay_seconds=10)
        assert td.retry_delay_seconds == 10
```

## Test Strategy

1. **Unit tests for `@tool` decorator** — Verify `retry_count` and `retry_delay_seconds` are stored on `ToolDef` when specified, and are `None` when not specified.
2. **Unit tests for `_default_task_def`** — Verify the function accepts and uses custom retry values, and preserves defaults when not specified.
3. **Existing tests must pass** — The `TestAgentToolRetryConfig` tests (lines 512-548) should continue to pass unchanged since `agent_tool()` uses a different mechanism (`config` dict).
4. **Run full test suite** — `pytest sdk/python/tests/unit/` to ensure no regressions.

## Risks and Edge Cases

1. **Backward compatibility**: All new parameters are optional with `None` defaults. Existing `@tool` and `@tool(...)` usage is unaffected. The `_default_task_def` function retains its existing defaults (2/2) via keyword argument defaults.

2. **`retry_count=0`**: Must work correctly to disable retries entirely. The Conductor `TaskDef` supports `retry_count=0`. Ensure we don't accidentally filter out falsy values (e.g., `if td.retry_count` would skip 0).

3. **Negative values**: We should NOT add validation for negative values — the Conductor server will reject invalid values. Keep the SDK thin.

4. **TypeScript SDK parity**: The TS `ToolDef` interface gets the fields, but the TS runtime registration (server-side compilation) may need corresponding changes in the compiler. Since the TS SDK compiles to a workflow definition sent to the server, the `retryCount`/`retryDelaySeconds` fields on `ToolDef` need to be picked up by the compiler. This is a lower-risk change since the TS compiler already handles `agent_tool` retry config.

5. **`_passthrough_task_def`** (line 67 in runtime.py): This is used for passthrough tasks and has its own hardcoded values. It's not affected by this change since it's not used for `@tool` workers.
