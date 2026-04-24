## Test Plan — Issue #150

### Existing test coverage
- `sdk/python/tests/unit/test_tool.py` — covers `@tool` decorator, `ToolDef`, `get_tool_def`, external tools, credentials, guardrails
- `sdk/python/tests/unit/test_runtime.py` — covers runtime helpers, `_default_task_def` (indirectly), worker registration

### New tests in `sdk/python/tests/unit/test_tool.py`
Add a new class `TestToolDecoratorRetryConfig`:

1. `test_retry_count_stored_in_tool_def` — `@tool(retry_count=10)` → `td.retry_count == 10`
2. `test_retry_delay_seconds_stored_in_tool_def` — `@tool(retry_delay_seconds=5)` → `td.retry_delay_seconds == 5`
3. `test_both_retry_params_stored` — `@tool(retry_count=10, retry_delay_seconds=5)` → both set correctly
4. `test_zero_retry_count_stored` — `@tool(retry_count=0)` → `td.retry_count == 0` (not None, important edge case)
5. `test_default_retry_params_are_none` — bare `@tool` → `td.retry_count is None` and `td.retry_delay_seconds is None`
6. `test_retry_params_with_other_params` — `@tool(name="x", retry_count=3, retry_delay_seconds=1)` → all params set correctly

### New tests in `sdk/python/tests/unit/test_runtime.py`
Add a new class `TestDefaultTaskDefRetryOverride`:

1. `test_default_task_def_uses_hardcoded_defaults` — calling `_default_task_def("t")` → `td.retry_count == 2`, `td.retry_delay_seconds == 2`
2. `test_default_task_def_overrides_retry_count` — `_default_task_def("t", retry_count=10)` → `td.retry_count == 10`
3. `test_default_task_def_overrides_retry_delay` — `_default_task_def("t", retry_delay_seconds=5)` → `td.retry_delay_seconds == 5`
4. `test_default_task_def_zero_retry_count` — `_default_task_def("t", retry_count=0)` → `td.retry_count == 0`
5. `test_default_task_def_both_overrides` — `_default_task_def("t", retry_count=7, retry_delay_seconds=3)` → both set
6. `test_default_task_def_none_uses_defaults` — `_default_task_def("t", retry_count=None, retry_delay_seconds=None)` → defaults (2, 2)
