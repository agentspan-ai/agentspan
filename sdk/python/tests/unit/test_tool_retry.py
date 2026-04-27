# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""Unit tests for @tool retry_count and retry_delay_seconds parameters (Issue #167 / PR #168)."""

import pytest

from agentspan.agents.tool import ToolDef, tool


class TestToolRetryParams:
    """@tool decorator must accept and store retry_count and retry_delay_seconds."""

    def test_retry_count_accepted_by_decorator(self):
        """@tool(retry_count=3) must not raise and must store the value."""

        @tool(retry_count=3)
        def my_tool(x: str) -> str:
            """A retryable tool."""
            return x

        td = my_tool._tool_def
        assert isinstance(td, ToolDef)
        assert td.retry_count == 3

    def test_retry_delay_seconds_accepted_by_decorator(self):
        """@tool(retry_delay_seconds=1) must not raise and must store the value."""

        @tool(retry_delay_seconds=1)
        def my_tool(x: str) -> str:
            """A retryable tool."""
            return x

        td = my_tool._tool_def
        assert isinstance(td, ToolDef)
        assert td.retry_delay_seconds == 1

    def test_retry_count_and_delay_together(self):
        """@tool(retry_count=3, retry_delay_seconds=1) must store both values."""

        @tool(retry_count=3, retry_delay_seconds=1)
        def fetch_exchange_rate(base: str, target: str) -> dict:
            """Fetch the exchange rate between two currencies."""
            return {"base": base, "target": target, "rate": 0.92}

        td = fetch_exchange_rate._tool_def
        assert td.retry_count == 3
        assert td.retry_delay_seconds == 1

    def test_retry_count_zero_disables_retries(self):
        """@tool(retry_count=0) must store 0 (disables retries)."""

        @tool(retry_count=0)
        def no_retry_tool(x: str) -> str:
            """No retries."""
            return x

        td = no_retry_tool._tool_def
        assert td.retry_count == 0

    def test_retry_defaults_when_not_specified(self):
        """When retry_count/retry_delay_seconds are not specified, defaults apply."""

        @tool
        def plain_tool(x: str) -> str:
            """Plain tool."""
            return x

        td = plain_tool._tool_def
        # Defaults should be 2 as documented in README
        assert td.retry_count == 2
        assert td.retry_delay_seconds == 2

    def test_retry_params_with_other_params(self):
        """retry_count and retry_delay_seconds work alongside other @tool params."""

        @tool(name="custom_name", retry_count=5, retry_delay_seconds=3, timeout_seconds=30)
        def my_tool(x: str) -> str:
            """A tool with many params."""
            return x

        td = my_tool._tool_def
        assert td.name == "custom_name"
        assert td.retry_count == 5
        assert td.retry_delay_seconds == 3
        assert td.timeout_seconds == 30

    def test_retry_tool_still_callable(self):
        """A @tool with retry params is still directly callable."""

        @tool(retry_count=3, retry_delay_seconds=1)
        def add(a: int, b: int) -> int:
            """Add two numbers."""
            return a + b

        assert add(2, 3) == 5

    def test_retry_tool_def_has_correct_type(self):
        """ToolDef created with retry params has tool_type='worker'."""

        @tool(retry_count=2, retry_delay_seconds=2)
        def worker_tool(q: str) -> str:
            """A worker."""
            return q

        td = worker_tool._tool_def
        assert td.tool_type == "worker"

    def test_retry_example_agent_pattern(self):
        """Reproduce the exact pattern from examples/retry_example/python/agent.py."""
        _call_count = 0

        @tool(retry_count=3, retry_delay_seconds=1)
        def fetch_exchange_rate(base: str, target: str) -> dict:
            """Fetch the exchange rate between two currencies."""
            nonlocal _call_count
            _call_count += 1
            if _call_count <= 2:
                raise ConnectionError(
                    f"[attempt {_call_count}] Upstream service unavailable — retrying..."
                )
            rates = {("USD", "EUR"): 0.92, ("USD", "GBP"): 0.79, ("EUR", "USD"): 1.09}
            rate = rates.get((base.upper(), target.upper()), 1.0)
            return {
                "base": base.upper(),
                "target": target.upper(),
                "rate": rate,
                "attempt": _call_count,
            }

        td = fetch_exchange_rate._tool_def
        assert td.retry_count == 3
        assert td.retry_delay_seconds == 1
        assert td.name == "fetch_exchange_rate"
        assert td.description == "Fetch the exchange rate between two currencies."

        # The function itself works on the 3rd call
        with pytest.raises(ConnectionError):
            fetch_exchange_rate("USD", "EUR")  # attempt 1 — fails
        with pytest.raises(ConnectionError):
            fetch_exchange_rate("USD", "EUR")  # attempt 2 — fails
        result = fetch_exchange_rate("USD", "EUR")  # attempt 3 — succeeds
        assert result["rate"] == 0.92
        assert result["attempt"] == 3

    def test_tooldef_retry_fields_exist(self):
        """ToolDef dataclass must have retry_count and retry_delay_seconds fields."""
        td = ToolDef(name="test", description="test", retry_count=4, retry_delay_seconds=5)
        assert td.retry_count == 4
        assert td.retry_delay_seconds == 5

    def test_tooldef_retry_defaults(self):
        """ToolDef created without retry params uses documented defaults."""
        td = ToolDef(name="test", description="test")
        assert td.retry_count == 2
        assert td.retry_delay_seconds == 2


class TestToolRetryCompilerOutput:
    """Verify retry params are passed through to the compiler/tool_compiler output."""

    def test_retry_params_stored_in_tool_def_config_or_fields(self):
        """After decoration, retry info is accessible for the compiler to use."""

        @tool(retry_count=3, retry_delay_seconds=1)
        def flaky_tool(x: str) -> str:
            """Flaky tool."""
            return x

        td = flaky_tool._tool_def
        # Either stored as direct fields or in config — both are acceptable
        has_fields = hasattr(td, "retry_count") and td.retry_count == 3
        has_config = td.config.get("retryCount") == 3 or td.config.get("retry_count") == 3
        assert has_fields or has_config, (
            "retry_count=3 must be accessible on ToolDef (as field or config key)"
        )

    def test_retry_delay_stored_in_tool_def_config_or_fields(self):
        """After decoration, retry_delay_seconds is accessible for the compiler."""

        @tool(retry_count=3, retry_delay_seconds=1)
        def flaky_tool(x: str) -> str:
            """Flaky tool."""
            return x

        td = flaky_tool._tool_def
        has_fields = hasattr(td, "retry_delay_seconds") and td.retry_delay_seconds == 1
        has_config = (
            td.config.get("retryDelaySeconds") == 1 or td.config.get("retry_delay_seconds") == 1
        )
        assert has_fields or has_config, (
            "retry_delay_seconds=1 must be accessible on ToolDef (as field or config key)"
        )
