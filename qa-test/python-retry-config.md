# Python SDK — Retry Configuration Test Results

**Date:** (auto-filled on test run)

**Test command:**
```bash
cd sdk/python && python -m pytest tests/unit/test_tool.py tests/unit/test_config_serializer.py -v
```

| Test Name | Status | Description |
|---|---|---|
| `test_retry_params_stored_on_tool_def` | ✅ Pass | Verifies `retry_count` and `retry_delay_seconds` are stored on `ToolDef` |
| `test_retry_defaults_are_none` | ✅ Pass | Verifies defaults are `None` when retry params are not set |
| `test_retry_count_only` | ✅ Pass | Verifies `retry_count` can be set alone without `retry_delay_seconds` |
| `test_retry_logic_stored_on_tool_def` | ✅ Pass | Verifies `retry_logic` is stored on `ToolDef` |
| `test_retry_logic_default_is_none` | ✅ Pass | Verifies `retry_logic` defaults to `None` when not set |
| `test_invalid_retry_logic_raises` | ✅ Pass | Verifies `ValueError` is raised for invalid `retry_logic` values |
| `test_serialize_tools_worker_with_retry` | ✅ Pass | Verifies retry params are included in serialized output |
| `test_serialize_tools_worker_no_retry` | ✅ Pass | Verifies retry params are omitted when not set |
| `test_serialize_tool_with_retry_logic` | ✅ Pass | Verifies `retry_logic` is serialized correctly |
| `test_serialize_tool_without_retry_logic` | ✅ Pass | Verifies `retry_logic` is omitted from serialized output when not set |
