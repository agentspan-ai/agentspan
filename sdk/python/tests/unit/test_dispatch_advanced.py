# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""Unit tests for advanced dispatch features — circuit breaker,
make_tool_worker, and ToolContext injection.
"""

import inspect
from typing import List, Optional

import pytest

from agentspan.agents.runtime._dispatch import (
    _coerce_value,
    _current_context,
    _mcp_servers,
    _tool_approval_flags,
    _tool_error_counts,
    _tool_registry,
    _tool_task_names,
    _tool_type_registry,
    make_tool_worker,
)

# ── helpers ──────────────────────────────────────────────────────────────


def _register_tools(name: str, funcs: dict):
    _tool_registry[name] = funcs
    for fn_name in funcs:
        _tool_task_names[fn_name] = fn_name


def _make_task(input_data=None, workflow_instance_id="test-wf-001", task_id="test-task-001"):
    """Create a minimal mock Task for testing make_tool_worker."""
    from conductor.client.http.models.task import Task

    t = Task()
    t.input_data = input_data or {}
    t.workflow_instance_id = workflow_instance_id
    t.task_id = task_id
    return t


@pytest.fixture(autouse=True)
def _clean_state():
    """Clear all global state between tests."""
    _tool_registry.clear()
    _tool_type_registry.clear()
    _tool_task_names.clear()
    _mcp_servers.clear()
    _tool_error_counts.clear()
    _tool_approval_flags.clear()
    _current_context.clear()
    yield
    _tool_registry.clear()
    _tool_type_registry.clear()
    _tool_task_names.clear()
    _mcp_servers.clear()
    _tool_error_counts.clear()
    _tool_approval_flags.clear()
    _current_context.clear()


# ── Circuit breaker ──────────────────────────────────────────────────────


class TestCircuitBreaker:
    """Test that make_tool_worker tracks error counts for circuit breaking."""

    def test_make_tool_worker_increments_error_count(self):
        """make_tool_worker returns FAILED TaskResult and increments error count."""

        def bad_tool():
            raise RuntimeError("boom")

        wrapper = make_tool_worker(bad_tool, "bad_tool")
        result = wrapper(_make_task())
        assert result.status == "FAILED"
        assert _tool_error_counts["bad_tool"] == 1

    def test_make_tool_worker_resets_on_success(self):
        _tool_error_counts["good"] = 2
        wrapper = make_tool_worker(lambda: "ok", "good")
        result = wrapper(_make_task())
        assert result.status == "COMPLETED"
        assert _tool_error_counts["good"] == 0

    def test_consecutive_failures_increment(self):
        """Error count increments on each consecutive failure."""

        def flaky():
            raise ValueError("fail")

        wrapper = make_tool_worker(flaky, "flaky")
        for i in range(3):
            result = wrapper(_make_task())
            assert result.status == "FAILED"
        assert _tool_error_counts["flaky"] == 3


# ── ToolContext injection ───────────────────────────────────────────────


class TestToolContext:
    """Test ToolContext injection via make_tool_worker."""

    def test_context_injected_via_make_tool_worker(self):
        from agentspan.agents.tool import ToolContext

        received_ctx = {}

        def tool_with_context(context: ToolContext, query: str) -> str:
            received_ctx["agent"] = context.agent_name
            received_ctx["session"] = context.session_id
            received_ctx["execution_id"] = context.execution_id
            return f"result for {query}"

        _current_context.update(
            {
                "agent_name": "test_agent",
                "session_id": "session_123",
            }
        )

        wrapper = make_tool_worker(tool_with_context, "ctx_tool")
        task = _make_task(input_data={"query": "test"}, workflow_instance_id="wf-ctx-test")
        result = wrapper(task)

        assert result.status == "COMPLETED"
        assert result.output_data == {"result": "result for test"}
        assert received_ctx["agent"] == "test_agent"
        assert received_ctx["session"] == "session_123"
        assert received_ctx["execution_id"] == "wf-ctx-test"

    def test_no_context_param_via_make_tool_worker(self):
        def plain_tool(x: str) -> str:
            return x.upper()

        wrapper = make_tool_worker(plain_tool, "plain")
        task = _make_task(input_data={"x": "hello"})
        result = wrapper(task)
        assert result.status == "COMPLETED"
        assert result.output_data == {"result": "HELLO"}

    def test_context_state_from_task_input(self):
        """ToolContext.state should be populated from _agent_state in task input."""
        from agentspan.agents.tool import ToolContext

        def write_tool(key: str, value: str, context: ToolContext = None) -> dict:
            context.state[key] = value
            return {"written": key}

        wrapper = make_tool_worker(write_tool, "write_tool")
        # _agent_state is injected by the enrichment script on the server
        task = _make_task(
            input_data={"key": "color", "value": "blue", "_agent_state": {"existing": "data"}},
            workflow_instance_id="wf-state-test",
        )
        result = wrapper(task)
        assert result.status == "COMPLETED"
        # State updates should be in output for server-side persistence
        assert "_state_updates" in result.output_data
        assert result.output_data["_state_updates"]["color"] == "blue"
        assert result.output_data["_state_updates"]["existing"] == "data"

    def test_context_state_empty_when_no_agent_state(self):
        """ToolContext.state should be empty dict when _agent_state is not in task input."""
        from agentspan.agents.tool import ToolContext

        def read_tool(key: str, context: ToolContext = None) -> dict:
            return {"value": context.state.get(key, "NOT_FOUND")}

        wrapper = make_tool_worker(read_tool, "read_tool")
        task = _make_task(input_data={"key": "x"}, workflow_instance_id="wf-1")
        result = wrapper(task)
        assert result.status == "COMPLETED"
        assert result.output_data == {"value": "NOT_FOUND"}

    def test_state_updates_in_output(self):
        """Tools that modify state should include _state_updates in output."""
        from agentspan.agents.tool import ToolContext

        def multi_write(context: ToolContext = None) -> str:
            context.state["a"] = 1
            context.state["b"] = 2
            return "done"

        wrapper = make_tool_worker(multi_write, "multi_write")
        task = _make_task(input_data={"_agent_state": {}})
        result = wrapper(task)
        assert result.status == "COMPLETED"
        assert result.output_data["_state_updates"] == {"a": 1, "b": 2}
        assert result.output_data["result"] == "done"


# ── make_tool_worker factory ─────────────────────────────────────────


class TestMakeToolWorker:
    """Test make_tool_worker() — wraps execution, returns TaskResult."""

    def test_basic_execution(self):
        def my_tool(city: str) -> dict:
            return {"temp": 72, "city": city}

        wrapper = make_tool_worker(my_tool, "my_tool")
        result = wrapper(_make_task(input_data={"city": "NYC"}))
        assert result.status == "COMPLETED"
        assert result.output_data == {"temp": 72, "city": "NYC"}

    def test_string_result(self):
        def echo(msg: str) -> str:
            return f"Echo: {msg}"

        wrapper = make_tool_worker(echo, "echo")
        result = wrapper(_make_task(input_data={"msg": "hello"}))
        assert result.status == "COMPLETED"
        assert result.output_data == {"result": "Echo: hello"}

    def test_error_returns_failed_result(self):
        """Tool errors should return FAILED TaskResult."""

        def bad_tool():
            raise RuntimeError("boom")

        wrapper = make_tool_worker(bad_tool, "bad_tool")
        result = wrapper(_make_task())
        assert result.status == "FAILED"
        assert "boom" in result.reason_for_incompletion
        assert _tool_error_counts["bad_tool"] == 1

    def test_success_resets_error_count(self):
        _tool_error_counts["good"] = 2

        wrapper = make_tool_worker(lambda: "ok", "good")
        result = wrapper(_make_task())
        assert result.status == "COMPLETED"
        assert result.output_data == {"result": "ok"}
        assert _tool_error_counts["good"] == 0

    def test_preserves_function_name(self):
        def get_weather(city: str, units: str = "F") -> dict:
            return {"city": city}

        wrapper = make_tool_worker(get_weather, "get_weather")
        assert wrapper.__name__ == "get_weather"


class TestFrameworkCallableCompatibility:
    """Framework-extracted callables should match OpenAI SDK expectations."""

    def test_framework_callable_gets_object_like_ctx_and_agent(self):
        def dynamic_instructions(ctx, agent) -> str:
            return f"{agent.metadata.role}:{ctx.metadata.user.name}:{ctx.prompt}"

        dynamic_instructions._agentspan_framework_callable = True

        wrapper = make_tool_worker(dynamic_instructions, "dynamic_instructions")
        task = _make_task(
            input_data={
                "ctx": {
                    "prompt": "hello",
                    "metadata": {"user": {"name": "viren"}},
                },
                "agent": {
                    "name": "helper",
                    "metadata": {"role": "assistant"},
                },
            }
        )

        result = wrapper(task)

        assert result.status == "COMPLETED"
        assert result.output_data == {"result": "assistant:viren:hello"}

    def test_framework_callable_normalizes_model_like_results(self):
        class GuardrailOutput:
            def model_dump(self):
                return {
                    "tripwire_triggered": True,
                    "output_info": {"reason": "unsafe output"},
                }

        def check_output_safety(output):
            return GuardrailOutput()

        check_output_safety._agentspan_framework_callable = True

        wrapper = make_tool_worker(check_output_safety, "check_output_safety")
        result = wrapper(_make_task(input_data={"output": "bad"}))

        assert result.status == "COMPLETED"
        assert result.output_data == {
            "tripwire_triggered": True,
            "output_info": {"reason": "unsafe output"},
        }


# ── Guardrail integration with make_tool_worker ────────────────────────


class _MockGuardrail:
    """Minimal guardrail mock for testing make_tool_worker guardrail paths."""

    def __init__(self, position, on_fail, passed=True, message="", fixed_output=None):
        self.position = position
        self.on_fail = on_fail
        self.name = "mock_guard"
        self._passed = passed
        self._message = message
        self._fixed_output = fixed_output

    def check(self, content):
        from agentspan.agents.guardrail import GuardrailResult

        return GuardrailResult(
            passed=self._passed,
            message=self._message,
            fixed_output=self._fixed_output,
        )


class TestMakeToolWorkerGuardrails:
    """Test guardrail integration in make_tool_worker."""

    def test_pre_guardrail_blocks_with_raise(self):
        guard = _MockGuardrail(position="input", on_fail="raise", passed=False, message="bad input")

        def my_tool(x: str) -> str:
            return x

        wrapper = make_tool_worker(my_tool, "guarded", guardrails=[guard])
        result = wrapper(_make_task(input_data={"x": "hello"}))
        # Raise guardrails now return FAILED TaskResult
        assert result.status == "FAILED"
        assert "blocked execution" in result.reason_for_incompletion

    def test_pre_guardrail_blocks_with_error_dict(self):
        guard = _MockGuardrail(position="input", on_fail="retry", passed=False, message="bad input")

        def my_tool(x: str) -> str:
            return x

        wrapper = make_tool_worker(my_tool, "guarded", guardrails=[guard])
        result = wrapper(_make_task(input_data={"x": "hello"}))
        assert result.status == "COMPLETED"
        assert result.output_data["blocked"] is True
        assert "Blocked by guardrail" in result.output_data["error"]

    def test_pre_guardrail_passes(self):
        guard = _MockGuardrail(position="input", on_fail="raise", passed=True)

        def my_tool(x: str) -> str:
            return x.upper()

        wrapper = make_tool_worker(my_tool, "guarded", guardrails=[guard])
        result = wrapper(_make_task(input_data={"x": "hello"}))
        assert result.status == "COMPLETED"
        assert result.output_data == {"result": "HELLO"}

    def test_post_guardrail_fix_replaces_result(self):
        guard = _MockGuardrail(
            position="output",
            on_fail="fix",
            passed=False,
            message="needs fix",
            fixed_output="FIXED",
        )

        def my_tool() -> str:
            return "original"

        wrapper = make_tool_worker(my_tool, "guarded", guardrails=[guard])
        result = wrapper(_make_task())
        assert result.status == "COMPLETED"
        assert result.output_data == {"result": "FIXED"}

    def test_post_guardrail_raise(self):
        guard = _MockGuardrail(
            position="output", on_fail="raise", passed=False, message="bad output"
        )

        def my_tool() -> str:
            return "original"

        wrapper = make_tool_worker(my_tool, "guarded", guardrails=[guard])
        result = wrapper(_make_task())
        assert result.status == "FAILED"
        assert "failed" in result.reason_for_incompletion.lower()

    def test_post_guardrail_sanitize(self):
        guard = _MockGuardrail(
            position="output", on_fail="retry", passed=False, message="unsafe output"
        )

        def my_tool() -> str:
            return "original"

        wrapper = make_tool_worker(my_tool, "guarded", guardrails=[guard])
        result = wrapper(_make_task())
        assert result.status == "COMPLETED"
        assert result.output_data["blocked"] is True
        assert "blocked by guardrail" in result.output_data["error"].lower()

    def test_post_guardrail_passes(self):
        guard = _MockGuardrail(position="output", on_fail="raise", passed=True)

        def my_tool() -> dict:
            return {"key": "value"}

        wrapper = make_tool_worker(my_tool, "guarded", guardrails=[guard])
        result = wrapper(_make_task())
        assert result.status == "COMPLETED"
        assert result.output_data == {"key": "value"}


class TestNeedsContext:
    """Test _needs_context helper for edge cases."""

    def test_exception_returns_false(self):
        from agentspan.agents.runtime._dispatch import _needs_context

        # Pass something that's not a function
        assert _needs_context(42) is False


class TestToolSerializationValidation:
    """Test BUG-P2-08: non-serializable return values raise ToolSerializationError."""

    def test_set_return_raises(self):

        def bad_tool():
            return {1, 2, 3}  # set is not JSON-serializable

        worker = make_tool_worker(bad_tool, "bad_set_tool")
        task = _make_task(input_data={})
        result = worker(task)
        # Worker catches exceptions and marks task FAILED
        assert result.status.name == "FAILED"

    def test_dict_return_ok(self):
        def good_tool():
            return {"key": "value", "count": 42}

        worker = make_tool_worker(good_tool, "good_dict_tool")
        task = _make_task(input_data={})
        result = worker(task)
        assert result.status.name == "COMPLETED"
        assert result.output_data == {"key": "value", "count": 42}

    def test_string_return_ok(self):
        def str_tool():
            return "hello"

        worker = make_tool_worker(str_tool, "str_tool")
        task = _make_task(input_data={})
        result = worker(task)
        assert result.status.name == "COMPLETED"

    def test_bytes_return_raises(self):
        def bytes_tool():
            return b"binary data"

        worker = make_tool_worker(bytes_tool, "bytes_tool")
        task = _make_task(input_data={})
        result = worker(task)
        assert result.status.name == "FAILED"

    def test_validate_serializable_function(self):
        from agentspan.agents.runtime._dispatch import (
            ToolSerializationError,
            _validate_serializable,
        )

        # These should not raise
        _validate_serializable("t", None)
        _validate_serializable("t", "hello")
        _validate_serializable("t", 42)
        _validate_serializable("t", 3.14)
        _validate_serializable("t", True)
        _validate_serializable("t", {"key": "val"})
        _validate_serializable("t", [1, 2, 3])

        # These should raise
        with pytest.raises(ToolSerializationError, match="non-serializable"):
            _validate_serializable("t", {1, 2, 3})
        with pytest.raises(ToolSerializationError, match="non-serializable"):
            _validate_serializable("t", b"bytes")


# ── Type coercion ────────────────────────────────────────────────────────


class TestTypeCoercion:
    """Test _coerce_value and end-to-end type coercion in make_tool_worker."""

    # ── _coerce_value unit tests ─────────────────────────────────────

    def test_list_str_from_json_string(self):
        result = _coerce_value('["a", "b", "c"]', List[str])
        assert result == ["a", "b", "c"]

    def test_list_dict_from_json_string(self):
        result = _coerce_value('[{"k": "v"}, {"k2": "v2"}]', List[dict])
        assert result == [{"k": "v"}, {"k2": "v2"}]

    def test_dict_from_json_string(self):
        result = _coerce_value('{"key": "value"}', dict)
        assert result == {"key": "value"}

    def test_already_native_list_unchanged(self):
        original = ["a", "b"]
        result = _coerce_value(original, List[str])
        assert result is original

    def test_optional_list_str_unwrapped(self):
        result = _coerce_value('["x", "y"]', Optional[List[str]])
        assert result == ["x", "y"]

    def test_invalid_json_passes_through(self):
        result = _coerce_value("not json at all", List[str])
        assert result == "not json at all"

    def test_int_from_string(self):
        assert _coerce_value("42", int) == 42

    def test_float_from_string(self):
        assert _coerce_value("3.14", float) == 3.14

    def test_bool_from_string_true(self):
        assert _coerce_value("true", bool) is True
        assert _coerce_value("YES", bool) is True
        assert _coerce_value("1", bool) is True

    def test_bool_from_string_false(self):
        assert _coerce_value("false", bool) is False
        assert _coerce_value("NO", bool) is False
        assert _coerce_value("0", bool) is False

    def test_none_not_coerced(self):
        assert _coerce_value(None, List[str]) is None

    def test_wrong_json_type_passes_through(self):
        """JSON array when dict expected should pass through unchanged."""
        result = _coerce_value("[1, 2, 3]", dict)
        assert result == "[1, 2, 3]"

    def test_empty_annotation_no_coercion(self):
        result = _coerce_value("42", inspect.Parameter.empty)
        assert result == "42"

    # ── End-to-end via make_tool_worker ───────────────────────────────

    def test_e2e_list_str_coerced_in_worker(self):
        def process_tags(tags: List[str]) -> dict:
            return {"count": len(tags), "tags": tags}

        wrapper = make_tool_worker(process_tags, "process_tags")
        task = _make_task(input_data={"tags": '["python", "rust"]'})
        result = wrapper(task)
        assert result.status == "COMPLETED"
        assert result.output_data == {"count": 2, "tags": ["python", "rust"]}

    def test_e2e_dict_coerced_in_worker(self):
        def process_config(config: dict) -> dict:
            return {"keys": list(config.keys())}

        wrapper = make_tool_worker(process_config, "process_config")
        task = _make_task(input_data={"config": '{"a": 1, "b": 2}'})
        result = wrapper(task)
        assert result.status == "COMPLETED"
        assert result.output_data == {"keys": ["a", "b"]}

    def test_e2e_int_coerced_in_worker(self):
        def repeat(text: str, count: int) -> str:
            return text * count

        wrapper = make_tool_worker(repeat, "repeat")
        task = _make_task(input_data={"text": "ha", "count": "3"})
        result = wrapper(task)
        assert result.status == "COMPLETED"
        assert result.output_data == {"result": "hahaha"}
