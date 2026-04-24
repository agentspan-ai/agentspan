## Test Plan — Issue #150: Allow retry configuration on @tool decorator

### Unit Tests — `tests/unit/test_tool.py`

Add new test class `TestToolDecoratorRetryConfig`:

**1. `test_retry_count_and_delay_stored_on_tooldef`**
- `@tool(retry_count=10, retry_delay_seconds=5)` on a function
- Assert `td.retry_count == 10` and `td.retry_delay_seconds == 5`

**2. `test_retry_count_zero_stored`**
- `@tool(retry_count=0)` on a function
- Assert `td.retry_count == 0` (not None — zero means "no retries")
- Assert `td.retry_delay_seconds is None` (not set)

**3. `test_bare_tool_has_none_retry_fields`**
- `@tool` (bare decorator) on a function
- Assert `td.retry_count is None` and `td.retry_delay_seconds is None`

**4. `test_retry_with_other_params`**
- `@tool(name="custom", retry_count=3, retry_delay_seconds=10, approval_required=True)`
- Assert all params stored correctly — retry fields AND existing fields

**5. `test_only_retry_delay_set`**
- `@tool(retry_delay_seconds=15)` — only delay, no count
- Assert `td.retry_count is None` and `td.retry_delay_seconds == 15`

### Unit Tests — `tests/unit/test_tool.py` (continued)

Add tests for `_default_task_def` retry override behavior:

**6. `test_default_task_def_uses_retry_overrides`**
- Call `_default_task_def("x", retry_count=5, retry_delay_seconds=10)`
- Assert `td.retry_count == 5` and `td.retry_delay_seconds == 10`

**7. `test_default_task_def_falls_back_to_defaults`**
- Call `_default_task_def("x")` with no retry args
- Assert `td.retry_count == 2` and `td.retry_delay_seconds == 2`

**8. `test_default_task_def_zero_retry_count`**
- Call `_default_task_def("x", retry_count=0)`
- Assert `td.retry_count == 0` (not 2 — zero must be respected)

### Existing Suites That Must Still Pass
- `tests/unit/test_tool.py` — all existing tests (TestToolDecorator, TestHttpTool, TestMcpTool, TestGetToolDef, TestWorkerTaskDetection, TestExternalTool, TestAgentToolRetryConfig, TestToolCredentialParams, etc.)
- All e2e suites — no behavioral change for tools without retry overrides

### Acceptance Criteria
- All tests are deterministic (no LLM calls, no mocks for the new tests)
- `retry_count=0` is distinguished from `retry_count=None` (default)
- Existing tools without retry params continue to get retry_count=2, retry_delay_seconds=2
