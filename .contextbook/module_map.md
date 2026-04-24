PRIMARY FILES TO MODIFY:

1. sdk/python/src/agentspan/agents/tool.py
   - `ToolDef` dataclass: Add `retry_count: Optional[int] = None` and `retry_delay_seconds: Optional[int] = None` fields.
   - `@tool` decorator (both overloads + implementation): Add `retry_count: Optional[int] = None` and `retry_delay_seconds: Optional[int] = None` keyword parameters.
   - `_wrap()` inner function: Pass the new params through when constructing `ToolDef(...)`.

2. sdk/python/src/agentspan/agents/runtime/runtime.py
   - `_default_task_def(name, ...)`: Currently hardcodes `td.retry_count = 2` and `td.retry_delay_seconds = 2`.
   - `ToolRegistry.register_tool_workers(...)` (in tool_registry.py): When registering a `@tool` worker, read `tool_def.retry_count` / `tool_def.retry_delay_seconds` and pass them to `_default_task_def` (or build a custom TaskDef) instead of always using the hardcoded defaults.

SECONDARY FILES (may need updates):
- sdk/python/src/agentspan/agents/runtime/tool_registry.py — where `worker_task(task_def=_default_task_def(...))` is called for each `@tool` worker; needs to honour per-tool retry overrides.
- sdk/python/tests/unit/test_tool.py — existing tool tests; new tests for retry params needed.
- sdk/python/tests/unit/test_runtime.py — existing runtime tests; new tests for TaskDef retry override needed.