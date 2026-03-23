# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""Unit tests for the @tool decorator and tool utilities."""

from unittest import mock

import pytest

from agentspan.agents.tool import ToolDef, get_tool_def, get_tool_defs, http_tool, mcp_tool, tool


def _make_task(input_data=None, workflow_instance_id="test-wf-001", task_id="test-task-001"):
    """Create a minimal mock Task for testing make_tool_worker."""
    from conductor.client.http.models.task import Task

    t = Task()
    t.input_data = input_data or {}
    t.workflow_instance_id = workflow_instance_id
    t.task_id = task_id
    return t


class TestToolDecorator:
    """Test @tool decorator behavior."""

    def test_bare_decorator(self):
        @tool
        def my_func(x: str) -> str:
            """Do something."""
            return x

        assert hasattr(my_func, "_tool_def")
        td = my_func._tool_def
        assert isinstance(td, ToolDef)
        assert td.name == "my_func"
        assert td.description == "Do something."
        assert td.func is not None
        assert td.tool_type == "worker"

    def test_decorator_with_args(self):
        @tool(name="custom_name", approval_required=True, timeout_seconds=30)
        def my_func(x: str) -> str:
            """Custom tool."""
            return x

        td = my_func._tool_def
        assert td.name == "custom_name"
        assert td.approval_required is True
        assert td.timeout_seconds == 30

    def test_function_still_callable(self):
        @tool
        def add(a: int, b: int) -> int:
            """Add two numbers."""
            return a + b

        assert add(2, 3) == 5

    def test_input_schema_generated(self):
        @tool
        def greet(name: str, age: int) -> str:
            """Greet someone."""
            return f"Hello {name}"

        td = greet._tool_def
        assert "properties" in td.input_schema
        assert "name" in td.input_schema["properties"]
        assert "age" in td.input_schema["properties"]
        assert td.input_schema["properties"]["name"]["type"] == "string"
        assert td.input_schema["properties"]["age"]["type"] == "integer"

    def test_docstring_as_description(self):
        @tool
        def my_tool(x: str) -> str:
            """This is the description."""
            return x

        assert my_tool._tool_def.description == "This is the description."

    def test_no_docstring(self):
        @tool
        def my_tool(x: str) -> str:
            return x

        assert my_tool._tool_def.description == ""


class TestHttpTool:
    """Test http_tool() constructor."""

    def test_basic_http_tool(self):
        td = http_tool(
            name="weather",
            description="Get weather",
            url="https://api.weather.com/v1",
            method="GET",
        )
        assert isinstance(td, ToolDef)
        assert td.name == "weather"
        assert td.tool_type == "http"
        assert td.config["url"] == "https://api.weather.com/v1"
        assert td.config["method"] == "GET"

    def test_http_tool_with_schema(self):
        td = http_tool(
            name="api",
            description="Call API",
            url="https://api.example.com",
            method="POST",
            headers={"Authorization": "Bearer token"},
            input_schema={"type": "object", "properties": {"q": {"type": "string"}}},
        )
        assert td.config["headers"]["Authorization"] == "Bearer token"
        assert "q" in td.input_schema["properties"]


class TestMcpTool:
    """Test mcp_tool() constructor."""

    def test_basic_mcp_tool(self):
        td = mcp_tool(server_url="http://localhost:8080/mcp")
        assert isinstance(td, ToolDef)
        assert td.tool_type == "mcp"
        assert td.config["server_url"] == "http://localhost:8080/mcp"

    def test_mcp_tool_with_overrides(self):
        td = mcp_tool(
            server_url="http://localhost:8080/mcp",
            name="github_tools",
            description="GitHub operations",
        )
        assert td.name == "github_tools"
        assert td.description == "GitHub operations"

    def test_mcp_tool_with_tool_names(self):
        td = mcp_tool(
            server_url="http://localhost:8080/mcp",
            tool_names=["get_weather", "get_forecast"],
        )
        assert td.config["tool_names"] == ["get_weather", "get_forecast"]

    def test_mcp_tool_default_max_tools(self):
        td = mcp_tool(server_url="http://localhost:8080/mcp")
        assert td.config["max_tools"] == 64

    def test_mcp_tool_custom_max_tools(self):
        td = mcp_tool(server_url="http://localhost:8080/mcp", max_tools=10)
        assert td.config["max_tools"] == 10

    def test_mcp_tool_no_tool_names_key_when_none(self):
        td = mcp_tool(server_url="http://localhost:8080/mcp")
        assert "tool_names" not in td.config


class TestGetToolDef:
    """Test get_tool_def() and get_tool_defs() utilities."""

    def test_from_decorated_function(self):
        @tool
        def my_tool(x: str) -> str:
            """Test."""
            return x

        td = get_tool_def(my_tool)
        assert isinstance(td, ToolDef)
        assert td.name == "my_tool"

    def test_from_tooldef(self):
        td = ToolDef(name="test", description="A test tool")
        result = get_tool_def(td)
        assert result is td

    def test_invalid_raises_type_error(self):
        with pytest.raises(TypeError, match="Expected a @tool-decorated"):
            get_tool_def("not a tool")

    def test_get_tool_defs_mixed(self):
        @tool
        def t1(x: str) -> str:
            """T1."""
            return x

        t2 = ToolDef(name="t2", description="T2")

        result = get_tool_defs([t1, t2])
        assert len(result) == 2
        assert result[0].name == "t1"
        assert result[1].name == "t2"


class TestWorkerTaskDetection:
    """Test that get_tool_def() detects @worker_task-decorated functions."""

    def _make_worker_task_func(self, registry: dict):
        """Simulate a @worker_task-decorated function by populating a registry."""
        import functools

        def original(customer_id: str, include_history: bool = False) -> dict:
            """Fetch customer data from the database."""
            return {"id": customer_id}

        @functools.wraps(original)
        def wrapper(*args, **kwargs):
            return original(*args, **kwargs)

        registry[("get_customer_data", None)] = {"func": original}
        return wrapper, original

    def test_worker_task_detected(self):
        registry = {}
        wrapper, _original = self._make_worker_task_func(registry)

        with (
            mock.patch(
                "agentspan.agents.tool._decorated_functions",
                registry,
                create=True,
            ),
            mock.patch(
                "conductor.client.automator.task_handler._decorated_functions",
                registry,
            ),
        ):
            td = get_tool_def(wrapper)

        assert isinstance(td, ToolDef)
        assert td.name == "get_customer_data"
        assert td.description == "Fetch customer data from the database."
        assert td.tool_type == "worker"
        assert td.func is not None
        assert "properties" in td.input_schema
        assert "customer_id" in td.input_schema["properties"]
        assert "include_history" in td.input_schema["properties"]

    def test_worker_task_not_registered_raises(self):
        """A plain callable not in _decorated_functions should still raise."""

        def plain_func(x: str) -> str:
            return x

        with pytest.raises(TypeError, match="@worker_task"):
            get_tool_def(plain_func)

    def test_worker_task_in_mixed_list(self):
        """get_tool_defs should handle @worker_task alongside @tool and ToolDef."""
        registry = {}
        wrapper, _original = self._make_worker_task_func(registry)

        @tool
        def my_tool(x: str) -> str:
            """A tool."""
            return x

        td_direct = ToolDef(name="direct", description="Direct ToolDef")

        with mock.patch(
            "conductor.client.automator.task_handler._decorated_functions",
            registry,
        ):
            result = get_tool_defs([my_tool, wrapper, td_direct])

        assert len(result) == 3
        assert result[0].name == "my_tool"
        assert result[1].name == "get_customer_data"
        assert result[2].name == "direct"

    def test_worker_task_with_domain(self):
        """A @worker_task registered with a domain should be detected."""
        import functools

        def original(order_id: str) -> dict:
            """Look up an order."""
            return {"order_id": order_id}

        @functools.wraps(original)
        def wrapper(*args, **kwargs):
            return original(*args, **kwargs)

        registry = {("lookup_order", "billing"): {"func": original}}

        with mock.patch(
            "conductor.client.automator.task_handler._decorated_functions",
            registry,
        ):
            td = get_tool_def(wrapper)

        assert td.name == "lookup_order"
        assert td.description == "Look up an order."

    def test_conductor_not_installed_raises(self):
        """If conductor-python is not installed, should fall through to TypeError."""

        def some_func(x: str) -> str:
            return x

        with mock.patch("agentspan.agents.tool._try_worker_task", return_value=None):
            with pytest.raises(TypeError):
                get_tool_def(some_func)


class TestExternalTool:
    """Test @tool(external=True) for referencing external workers."""

    def test_external_sets_func_none(self):
        """external=True creates a ToolDef with func=None."""

        @tool(external=True)
        def process_order(order_id: str, action: str) -> dict:
            """Process a customer order."""
            ...

        td = process_order._tool_def
        assert isinstance(td, ToolDef)
        assert td.func is None
        assert td.name == "process_order"
        assert td.description == "Process a customer order."
        assert td.tool_type == "worker"

    def test_external_schema_from_type_hints(self):
        """external=True still generates schema from function signature."""

        @tool(external=True)
        def query_db(query: str, limit: int = 10) -> dict:
            """Run a database query."""
            ...

        td = query_db._tool_def
        assert "properties" in td.input_schema
        assert "query" in td.input_schema["properties"]
        assert "limit" in td.input_schema["properties"]
        assert td.input_schema["properties"]["query"]["type"] == "string"
        assert td.input_schema["properties"]["limit"]["type"] == "integer"
        assert "query" in td.input_schema.get("required", [])
        assert "limit" not in td.input_schema.get("required", [])

    def test_external_with_custom_name(self):
        """external=True respects the name parameter."""

        @tool(name="order_processor_v2", external=True)
        def process_order(order_id: str) -> dict:
            """Process an order."""
            ...

        td = process_order._tool_def
        assert td.name == "order_processor_v2"
        assert td.func is None

    def test_external_with_approval(self):
        """external=True works with approval_required."""

        @tool(external=True, approval_required=True)
        def delete_account(user_id: str) -> dict:
            """Delete a user account."""
            ...

        td = delete_account._tool_def
        assert td.func is None
        assert td.approval_required is True

    def test_external_with_guardrails(self):
        """external=True works with guardrails."""
        from agentspan.agents.guardrail import Guardrail, GuardrailResult

        guard = Guardrail(
            func=lambda c: GuardrailResult(passed=True),
            position="input",
            on_fail="raise",
            name="test_guard",
        )

        @tool(external=True, guardrails=[guard])
        def query_db(query: str) -> dict:
            """Query the database."""
            ...

        td = query_db._tool_def
        assert td.func is None
        assert len(td.guardrails) == 1
        assert td.guardrails[0].name == "test_guard"

    def test_external_still_callable(self):
        """external=True decorated functions are still callable (stub)."""

        @tool(external=True)
        def stub(x: str) -> str:
            """A stub."""
            return "stub_result"

        # The wrapper function is still callable
        assert stub("test") == "stub_result"

    def test_non_external_has_func(self):
        """Regular @tool (external=False) still sets func."""

        @tool
        def normal(x: str) -> str:
            """Normal tool."""
            return x

        td = normal._tool_def
        assert td.func is not None

    def test_get_tool_def_works_with_external(self):
        """get_tool_def() correctly extracts ToolDef from external tools."""

        @tool(external=True)
        def ext(x: str) -> str:
            """External."""
            ...

        td = get_tool_def(ext)
        assert td.func is None
        assert td.name == "ext"


class TestPEP563Annotations:
    """Test that tools work with PEP 563 (from __future__ import annotations)."""

    def test_make_tool_worker_resolves_string_annotations(self):
        """make_tool_worker resolves PEP 563 string annotations to real types."""
        from agentspan.agents.runtime._dispatch import make_tool_worker

        def my_tool(query: str, count: int = 5) -> dict:
            """A test tool."""
            return {"query": query, "count": count}

        # Simulate PEP 563: replace annotations with strings
        my_tool.__annotations__ = {"query": "str", "count": "int", "return": "dict"}

        wrapper = make_tool_worker(my_tool, "my_tool")

        # After make_tool_worker, the original function's annotations should be resolved
        assert my_tool.__annotations__["query"] is str
        assert my_tool.__annotations__["count"] is int
        assert my_tool.__annotations__["return"] is dict

    def test_make_tool_worker_wrapper_still_works(self):
        """The wrapper function returned by make_tool_worker still executes correctly."""
        from conductor.client.http.models.task import Task

        from agentspan.agents.runtime._dispatch import make_tool_worker

        def adder(a: int, b: int) -> int:
            """Add two numbers."""
            return a + b

        # Simulate PEP 563
        adder.__annotations__ = {"a": "int", "b": "int", "return": "int"}

        wrapper = make_tool_worker(adder, "adder")
        task = Task()
        task.input_data = {"a": 3, "b": 4}
        task.workflow_instance_id = "test-wf"
        task.task_id = "test-task"
        result = wrapper(task)
        assert result.output_data == {"result": 7}


# ── P4-D: Tool edge cases ─────────────────────────────────────────────


class TestToolEdgeCases:
    """Edge case tests for tool utilities."""

    def test_needs_context_with_non_tool_context_param(self):
        """A function with a 'context' param that's not ToolContext still triggers."""
        from agentspan.agents.runtime._dispatch import _needs_context

        def my_func(context: str) -> str:
            return context

        # _needs_context only checks param name, not type
        assert _needs_context(my_func) is True

    def test_needs_context_no_context_param(self):
        from agentspan.agents.runtime._dispatch import _needs_context

        def my_func(x: str) -> str:
            return x

        assert _needs_context(my_func) is False

    def test_mcp_tool_default_name(self):
        """Two MCP tools with default name should have the same default."""
        t1 = mcp_tool(server_url="http://localhost:8080/mcp")
        t2 = mcp_tool(server_url="http://localhost:9090/mcp")
        assert t1.name == t2.name  # both use default name

    def test_make_tool_worker_get_type_hints_fails(self):
        """make_tool_worker handles type hint resolution failure gracefully."""
        from conductor.client.http.models.task import Task

        from agentspan.agents.runtime._dispatch import make_tool_worker

        def my_tool(x: str) -> str:
            return x

        # Set annotations to something that can't be resolved
        my_tool.__annotations__ = {"x": "NonExistentType", "return": "str"}

        # Should not raise — the except block catches the failure
        wrapper = make_tool_worker(my_tool, "my_tool")
        task = Task()
        task.input_data = {"x": "hello"}
        task.workflow_instance_id = "test-wf"
        task.task_id = "test-task"
        result = wrapper(task)
        assert result.output_data == {"result": "hello"}


class TestAgentToolRetryConfig:
    """Test agent_tool() retry and resilience parameters."""

    def test_default_config_has_no_retry_overrides(self):
        from agentspan.agents.agent import Agent
        from agentspan.agents.tool import agent_tool

        worker = Agent(name="w", model="openai/gpt-4o")
        td = agent_tool(worker)
        assert "retryCount" not in td.config
        assert "retryDelaySeconds" not in td.config
        assert "optional" not in td.config

    def test_retry_count_passed(self):
        from agentspan.agents.agent import Agent
        from agentspan.agents.tool import agent_tool

        worker = Agent(name="w", model="openai/gpt-4o")
        td = agent_tool(worker, retry_count=5, retry_delay_seconds=10)
        assert td.config["retryCount"] == 5
        assert td.config["retryDelaySeconds"] == 10

    def test_optional_false_for_fail_fast(self):
        from agentspan.agents.agent import Agent
        from agentspan.agents.tool import agent_tool

        worker = Agent(name="w", model="openai/gpt-4o")
        td = agent_tool(worker, optional=False)
        assert td.config["optional"] is False

    def test_zero_retries(self):
        from agentspan.agents.agent import Agent
        from agentspan.agents.tool import agent_tool

        worker = Agent(name="w", model="openai/gpt-4o")
        td = agent_tool(worker, retry_count=0)
        assert td.config["retryCount"] == 0


# ── P1-A / P3-A: Dispatch advanced tests ──────────────────────────────


class TestDispatchFixThenCheck:
    """Test that fix-then-check recomputes result_str for subsequent guardrails."""

    def test_fix_then_check_uses_fixed_content(self):
        """When first guardrail fixes output, second guardrail checks the fixed version."""
        from agentspan.agents.guardrail import Guardrail, GuardrailResult
        from agentspan.agents.runtime._dispatch import make_tool_worker

        def fix_guardrail(content: str) -> GuardrailResult:
            if "bad" in content:
                return GuardrailResult(
                    passed=False,
                    message="Contains bad word",
                    fixed_output=content.replace("bad", "good"),
                )
            return GuardrailResult(passed=True)

        def validate_guardrail(content: str) -> GuardrailResult:
            if "bad" in content:
                return GuardrailResult(passed=False, message="Still contains bad word")
            return GuardrailResult(passed=True)

        g1 = Guardrail(func=fix_guardrail, on_fail="fix", position="output", name="fixer")
        g2 = Guardrail(
            func=validate_guardrail, on_fail="raise", position="output", name="validator"
        )

        def my_tool() -> str:
            return "this is bad content"

        wrapper = make_tool_worker(my_tool, "my_tool", guardrails=[g1, g2])
        # Without the fix, g2 would see "bad" and raise.
        # With the fix, g1 replaces "bad" with "good", g2 sees "good" and passes.
        result = wrapper(_make_task())
        assert result.status == "COMPLETED"
        assert result.output_data == {"result": "this is good content"}

    def test_fix_returns_fixed_output(self):
        """A single fix guardrail returns the fixed output."""
        from agentspan.agents.guardrail import Guardrail, GuardrailResult
        from agentspan.agents.runtime._dispatch import make_tool_worker

        def fix_it(content: str) -> GuardrailResult:
            return GuardrailResult(passed=False, message="fixing", fixed_output="FIXED")

        g = Guardrail(func=fix_it, on_fail="fix", position="output", name="fixer")

        wrapper = make_tool_worker(lambda: "original", "test_tool", guardrails=[g])
        result = wrapper(_make_task())
        assert result.status == "COMPLETED"
        assert result.output_data == {"result": "FIXED"}


class TestCircuitBreaker:
    """Test circuit breaker enforcement."""

    def test_tool_disabled_after_threshold(self):
        """Tool raises after N consecutive failures."""
        from agentspan.agents.runtime._dispatch import (
            _CIRCUIT_BREAKER_THRESHOLD,
            _tool_error_counts,
            make_tool_worker,
        )

        # Manually set error count to threshold
        _tool_error_counts["breaker_test"] = _CIRCUIT_BREAKER_THRESHOLD

        def my_tool() -> str:
            return "ok"

        wrapper = make_tool_worker(my_tool, "breaker_test")
        result = wrapper(_make_task())
        assert result.status == "FAILED"
        assert "circuit breaker open" in result.reason_for_incompletion

        # Cleanup
        _tool_error_counts.pop("breaker_test", None)

    def test_tool_works_below_threshold(self):
        """Tool works normally when error count is below threshold."""
        from agentspan.agents.runtime._dispatch import (
            _CIRCUIT_BREAKER_THRESHOLD,
            _tool_error_counts,
            make_tool_worker,
        )

        _tool_error_counts["below_test"] = _CIRCUIT_BREAKER_THRESHOLD - 1

        def my_tool() -> str:
            return "ok"

        wrapper = make_tool_worker(my_tool, "below_test")
        result = wrapper(_make_task())
        assert result.status == "COMPLETED"
        assert result.output_data == {"result": "ok"}
        # Success should reset count
        assert _tool_error_counts["below_test"] == 0

    def test_error_increments_count(self):
        """Tool failure increments error count."""
        from agentspan.agents.runtime._dispatch import (
            _tool_error_counts,
            make_tool_worker,
        )

        _tool_error_counts.pop("err_test", None)

        def failing_tool() -> str:
            raise ValueError("boom")

        wrapper = make_tool_worker(failing_tool, "err_test")
        result = wrapper(_make_task())
        assert result.status == "FAILED"
        assert "boom" in result.reason_for_incompletion

        assert _tool_error_counts["err_test"] == 1

        # Cleanup
        _tool_error_counts.pop("err_test", None)


class TestInputGuardrailDispatch:
    """Test pre-execution guardrail dispatch behavior."""

    def test_input_guardrail_blocks_execution(self):
        """An input guardrail failure blocks tool execution."""
        from agentspan.agents.guardrail import Guardrail, GuardrailResult
        from agentspan.agents.runtime._dispatch import make_tool_worker

        call_count = 0

        def my_tool(x: str) -> str:
            nonlocal call_count
            call_count += 1
            return x

        def block_input(content: str) -> GuardrailResult:
            return GuardrailResult(passed=False, message="Blocked")

        g = Guardrail(func=block_input, position="input", on_fail="raise", name="blocker")
        wrapper = make_tool_worker(my_tool, "guarded_tool", guardrails=[g])

        result = wrapper(_make_task(input_data={"x": "hello"}))
        assert result.status == "FAILED"
        assert "blocked execution" in result.reason_for_incompletion

        assert call_count == 0  # Tool was never called

    def test_input_guardrail_allows_when_passing(self):
        """An input guardrail that passes allows tool execution."""
        from agentspan.agents.guardrail import Guardrail, GuardrailResult
        from agentspan.agents.runtime._dispatch import make_tool_worker

        def my_tool(x: str) -> str:
            return f"processed_{x}"

        def allow_input(content: str) -> GuardrailResult:
            return GuardrailResult(passed=True)

        g = Guardrail(func=allow_input, position="input", on_fail="raise", name="allower")
        wrapper = make_tool_worker(my_tool, "guarded_tool2", guardrails=[g])

        result = wrapper(_make_task(input_data={"x": "hello"}))
        assert result.status == "COMPLETED"
        assert result.output_data == {"result": "processed_hello"}

    def test_output_guardrail_raise_raises(self):
        """An output guardrail with on_fail='raise' raises ValueError."""
        from agentspan.agents.guardrail import Guardrail, GuardrailResult
        from agentspan.agents.runtime._dispatch import make_tool_worker

        def my_tool() -> str:
            return "bad output"

        def check_output(content: str) -> GuardrailResult:
            return GuardrailResult(passed=False, message="Invalid output")

        g = Guardrail(func=check_output, position="output", on_fail="raise", name="checker")
        wrapper = make_tool_worker(my_tool, "raise_tool", guardrails=[g])

        result = wrapper(_make_task())
        assert result.status == "FAILED"
        assert "guardrail" in result.reason_for_incompletion.lower()


class TestCircuitBreakerReset:
    """Test circuit breaker reset functions."""

    def test_reset_circuit_breaker_clears_specific_tool(self):
        """reset_circuit_breaker clears error count for one tool."""
        from agentspan.agents.runtime._dispatch import (
            _tool_error_counts,
            reset_circuit_breaker,
        )

        _tool_error_counts["tool_a"] = 5
        _tool_error_counts["tool_b"] = 3
        reset_circuit_breaker("tool_a")
        assert _tool_error_counts.get("tool_a", 0) == 0
        assert _tool_error_counts["tool_b"] == 3
        # Cleanup
        _tool_error_counts.pop("tool_b", None)

    def test_reset_all_circuit_breakers(self):
        """reset_all_circuit_breakers clears all error counts."""
        from agentspan.agents.runtime._dispatch import (
            _tool_error_counts,
            reset_all_circuit_breakers,
        )

        _tool_error_counts["x"] = 10
        _tool_error_counts["y"] = 20
        reset_all_circuit_breakers()
        assert _tool_error_counts == {}

    def test_reset_nonexistent_tool_is_noop(self):
        """Resetting a tool that has no error count does nothing."""
        from agentspan.agents.runtime._dispatch import reset_circuit_breaker

        # Should not raise
        reset_circuit_breaker("nonexistent_tool_xyz")


class TestToolCredentialParams:
    """@tool decorator: isolated and credentials params."""

    def test_isolated_defaults_to_true(self):
        @tool
        def my_tool(x: str) -> str:
            """A tool."""
            return x

        assert my_tool._tool_def.isolated is True

    def test_isolated_false(self):
        @tool(isolated=False)
        def my_tool(x: str) -> str:
            """A tool."""
            return x

        assert my_tool._tool_def.isolated is False

    def test_credentials_defaults_to_empty_list(self):
        @tool
        def my_tool(x: str) -> str:
            """A tool."""
            return x

        assert my_tool._tool_def.credentials == []

    def test_credentials_string_list(self):
        @tool(credentials=["GITHUB_TOKEN", "GH_TOKEN"])
        def my_tool(x: str) -> str:
            """A tool."""
            return x

        assert "GITHUB_TOKEN" in my_tool._tool_def.credentials
        assert "GH_TOKEN" in my_tool._tool_def.credentials

    def test_credentials_with_credential_file(self):
        from agentspan.agents.runtime.credentials.types import CredentialFile

        cf = CredentialFile("KUBECONFIG", ".kube/config")

        @tool(credentials=["GITHUB_TOKEN", cf])
        def my_tool(x: str) -> str:
            """A tool."""
            return x

        creds = my_tool._tool_def.credentials
        assert "GITHUB_TOKEN" in creds
        assert cf in creds

    def test_isolated_false_with_credentials(self):
        @tool(isolated=False, credentials=["OPENAI_API_KEY"])
        def my_tool(x: str) -> str:
            """A tool."""
            return x

        assert my_tool._tool_def.isolated is False
        assert "OPENAI_API_KEY" in my_tool._tool_def.credentials

    def test_existing_params_still_work_alongside_new_params(self):
        @tool(name="custom_name", approval_required=True, isolated=False, credentials=["KEY"])
        def my_tool(x: str) -> str:
            """A tool."""
            return x

        td = my_tool._tool_def
        assert td.name == "custom_name"
        assert td.approval_required is True
        assert td.isolated is False
        assert "KEY" in td.credentials
