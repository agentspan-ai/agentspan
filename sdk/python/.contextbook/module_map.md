PRIMARY MODULE: sdk/python

Rationale:
- Issue explicitly mentions the Python SDK's @tool decorator and runtime.py
- Keywords in issue body: "sdk", "python", "@tool decorator", "runtime.py", "_default_task_def"

Affected files (confirmed by reading source):

1. sdk/python/src/agentspan/agents/tool.py
   - ToolDef dataclass: add two new optional fields:
       retry_count: Optional[int] = None
       retry_delay_seconds: Optional[int] = None
   - Both @tool overload signatures: add the same two keyword-only params
   - tool() implementation + _wrap() inner function: accept and pass them to ToolDef(...)

2. sdk/python/src/agentspan/agents/runtime/tool_registry.py
   - register_tool_workers() calls:
       task_def=_default_task_def(td.name)
   - Must be changed to pass td.retry_count / td.retry_delay_seconds so per-tool
     overrides win over the hardcoded defaults in _default_task_def.

3. sdk/python/src/agentspan/agents/runtime/runtime.py
   - _default_task_def(name, *, response_timeout_seconds=10) currently hardcodes
       td.retry_count = 2
       td.retry_delay_seconds = 2
   - Add optional params retry_count / retry_delay_seconds (default None → fall back
     to the existing hardcoded values of 2) so callers can override per-tool.

4. sdk/python/tests/unit/test_tool.py  (existing test file)
   - Add a new test class TestToolDecoratorRetryConfig with tests for:
       * @tool(retry_count=10, retry_delay_seconds=5) stores values on ToolDef
       * @tool(retry_count=0) stores 0 (not None)
       * bare @tool stores None for both fields (defaults)
       * values flow through to _default_task_def via tool_registry

SECONDARY MODULE: none — purely a Python SDK change; no server/, cli/, ui/, or TypeScript SDK changes required.