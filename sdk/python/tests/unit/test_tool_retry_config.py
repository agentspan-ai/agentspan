# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""Unit tests for retry configuration on @tool decorator (issue #150)."""

from unittest import mock

import pytest

from agentspan.agents.tool import ToolDef, tool


class TestToolRetryConfig:
    """Test retry configuration fields on @tool decorator and ToolDef."""

    def test_default_retry_fields_are_none(self):
        """A bare @tool decorated function should have all retry fields as None."""

        @tool
        def my_func(x: str) -> str:
            """Do something."""
            return x

        td = my_func._tool_def
        assert td.retry_count is None
        assert td.retry_delay_seconds is None
        assert td.retry_logic is None
        assert td.timeout_policy is None

    def test_retry_count_set(self):
        """@tool(retry_count=5) should produce a ToolDef with retry_count=5."""

        @tool(retry_count=5)
        def my_func(x: str) -> str:
            """Do something."""
            return x

        td = my_func._tool_def
        assert td.retry_count == 5
        assert td.retry_delay_seconds is None
        assert td.retry_logic is None
        assert td.timeout_policy is None

    def test_retry_delay_seconds_set(self):
        """@tool(retry_delay_seconds=10) should produce a ToolDef with retry_delay_seconds=10."""

        @tool(retry_delay_seconds=10)
        def my_func(x: str) -> str:
            """Do something."""
            return x

        td = my_func._tool_def
        assert td.retry_delay_seconds == 10
        assert td.retry_count is None

    def test_retry_logic_set(self):
        """@tool(retry_logic='EXPONENTIAL_BACKOFF') should set retry_logic correctly."""

        @tool(retry_logic="EXPONENTIAL_BACKOFF")
        def my_func(x: str) -> str:
            """Do something."""
            return x

        td = my_func._tool_def
        assert td.retry_logic == "EXPONENTIAL_BACKOFF"

    def test_timeout_policy_set(self):
        """@tool(timeout_policy='TIME_OUT_WF') should set timeout_policy correctly."""

        @tool(timeout_policy="TIME_OUT_WF")
        def my_func(x: str) -> str:
            """Do something."""
            return x

        td = my_func._tool_def
        assert td.timeout_policy == "TIME_OUT_WF"

    def test_disable_retries(self):
        """@tool(retry_count=0) should produce a ToolDef with retry_count=0."""

        @tool(retry_count=0)
        def my_func(x: str) -> str:
            """Idempotency-sensitive tool."""
            return x

        td = my_func._tool_def
        assert td.retry_count == 0

    def test_all_retry_fields_combined(self):
        """All four retry fields can be set together."""

        @tool(retry_count=5, retry_delay_seconds=10, retry_logic="FIXED", timeout_policy="ALERT_ONLY")
        def my_func(x: str) -> str:
            """Do something."""
            return x

        td = my_func._tool_def
        assert td.retry_count == 5
        assert td.retry_delay_seconds == 10
        assert td.retry_logic == "FIXED"
        assert td.timeout_policy == "ALERT_ONLY"

    def test_retry_fields_with_other_params(self):
        """Retry fields work alongside existing @tool parameters."""

        @tool(name="custom", approval_required=True, retry_count=3)
        def my_func(x: str) -> str:
            """Do something."""
            return x

        td = my_func._tool_def
        assert td.name == "custom"
        assert td.approval_required is True
        assert td.retry_count == 3
        assert td.retry_delay_seconds is None

    def test_retry_fields_on_tooldef_dataclass(self):
        """ToolDef dataclass accepts retry fields directly."""
        td = ToolDef(
            name="my_tool",
            retry_count=3,
            retry_delay_seconds=5,
            retry_logic="LINEAR_BACKOFF",
            timeout_policy="RETRY",
        )
        assert td.retry_count == 3
        assert td.retry_delay_seconds == 5
        assert td.retry_logic == "LINEAR_BACKOFF"
        assert td.timeout_policy == "RETRY"

    def test_tooldef_retry_fields_default_to_none(self):
        """ToolDef retry fields default to None when not specified."""
        td = ToolDef(name="my_tool")
        assert td.retry_count is None
        assert td.retry_delay_seconds is None
        assert td.retry_logic is None
        assert td.timeout_policy is None


class TestDefaultTaskDef:
    """Test _default_task_def() with and without retry overrides."""

    def _make_task_def(self, name="test", **kwargs):
        from agentspan.agents.runtime.runtime import _default_task_def

        return _default_task_def(name, **kwargs)

    def test_default_task_def_defaults(self):
        """_default_task_def with no overrides uses hardcoded defaults."""
        td = self._make_task_def()
        assert td.retry_count == 2
        assert td.retry_delay_seconds == 2
        assert td.retry_logic == "LINEAR_BACKOFF"
        assert td.timeout_policy == "RETRY"

    def test_default_task_def_custom_retry_count(self):
        """_default_task_def(retry_count=5) sets retry_count=5."""
        td = self._make_task_def(retry_count=5)
        assert td.retry_count == 5
        # Other fields remain at defaults
        assert td.retry_delay_seconds == 2
        assert td.retry_logic == "LINEAR_BACKOFF"
        assert td.timeout_policy == "RETRY"

    def test_default_task_def_zero_retries(self):
        """_default_task_def(retry_count=0) sets retry_count=0."""
        td = self._make_task_def(retry_count=0)
        assert td.retry_count == 0

    def test_default_task_def_all_overrides(self):
        """All four retry overrides are applied correctly."""
        td = self._make_task_def(
            retry_count=7,
            retry_delay_seconds=15,
            retry_logic="EXPONENTIAL_BACKOFF",
            timeout_policy="TIME_OUT_WF",
        )
        assert td.retry_count == 7
        assert td.retry_delay_seconds == 15
        assert td.retry_logic == "EXPONENTIAL_BACKOFF"
        assert td.timeout_policy == "TIME_OUT_WF"

    def test_default_task_def_timeout_seconds_always_zero(self):
        """timeout_seconds is always 0 regardless of overrides."""
        td = self._make_task_def(retry_count=5)
        assert td.timeout_seconds == 0

    def test_default_task_def_response_timeout_override(self):
        """response_timeout_seconds can be overridden independently."""
        td = self._make_task_def(response_timeout_seconds=30)
        assert td.response_timeout_seconds == 30
        # Retry defaults unchanged
        assert td.retry_count == 2


class TestToolRegistryRetryPassthrough:
    """Test that ToolRegistry passes retry fields from ToolDef to _default_task_def."""

    def _make_tool_def_with_func(self, name="my_tool", **retry_kwargs):
        """Create a ToolDef with a real callable func and optional retry fields."""

        def fn(x: str) -> str:
            """A test tool."""
            return x

        return ToolDef(name=name, func=fn, tool_type="worker", **retry_kwargs)

    def test_register_tool_with_retry_overrides(self):
        """ToolRegistry passes retry_count from ToolDef to _default_task_def."""
        td = self._make_tool_def_with_func(retry_count=5)

        with (
            mock.patch("agentspan.agents.runtime.tool_registry.make_tool_worker") as mock_make,
            mock.patch("agentspan.agents.runtime.tool_registry.worker_task") as mock_wt,
            mock.patch("agentspan.agents.runtime.runtime._default_task_def") as mock_dtd,
            mock.patch("agentspan.agents.tool.get_tool_defs", return_value=[td]),
        ):
            mock_make.return_value = mock.MagicMock()
            mock_wt.return_value = lambda fn: fn
            mock_dtd.return_value = mock.MagicMock()

            from agentspan.agents.runtime.tool_registry import ToolRegistry

            registry = ToolRegistry()
            registry.register_tool_workers([td], "test_agent")

            mock_dtd.assert_called_once_with("my_tool", retry_count=5)

    def test_register_tool_without_retry_overrides(self):
        """ToolRegistry calls _default_task_def with no extra kwargs when retry fields are None."""
        td = self._make_tool_def_with_func()

        with (
            mock.patch("agentspan.agents.runtime.tool_registry.make_tool_worker") as mock_make,
            mock.patch("agentspan.agents.runtime.tool_registry.worker_task") as mock_wt,
            mock.patch("agentspan.agents.runtime.runtime._default_task_def") as mock_dtd,
            mock.patch("agentspan.agents.tool.get_tool_defs", return_value=[td]),
        ):
            mock_make.return_value = mock.MagicMock()
            mock_wt.return_value = lambda fn: fn
            mock_dtd.return_value = mock.MagicMock()

            from agentspan.agents.runtime.tool_registry import ToolRegistry

            registry = ToolRegistry()
            registry.register_tool_workers([td], "test_agent")

            # Called with only the name — no retry kwargs
            mock_dtd.assert_called_once_with("my_tool")

    def test_register_tool_with_all_retry_fields(self):
        """ToolRegistry passes all four retry fields when all are set."""
        td = self._make_tool_def_with_func(
            retry_count=3,
            retry_delay_seconds=5,
            retry_logic="FIXED",
            timeout_policy="ALERT_ONLY",
        )

        with (
            mock.patch("agentspan.agents.runtime.tool_registry.make_tool_worker") as mock_make,
            mock.patch("agentspan.agents.runtime.tool_registry.worker_task") as mock_wt,
            mock.patch("agentspan.agents.runtime.runtime._default_task_def") as mock_dtd,
            mock.patch("agentspan.agents.tool.get_tool_defs", return_value=[td]),
        ):
            mock_make.return_value = mock.MagicMock()
            mock_wt.return_value = lambda fn: fn
            mock_dtd.return_value = mock.MagicMock()

            from agentspan.agents.runtime.tool_registry import ToolRegistry

            registry = ToolRegistry()
            registry.register_tool_workers([td], "test_agent")

            mock_dtd.assert_called_once_with(
                "my_tool",
                retry_count=3,
                retry_delay_seconds=5,
                retry_logic="FIXED",
                timeout_policy="ALERT_ONLY",
            )

    def test_register_tool_with_zero_retry_count(self):
        """retry_count=0 is passed through (not treated as falsy/None)."""
        td = self._make_tool_def_with_func(retry_count=0)

        with (
            mock.patch("agentspan.agents.runtime.tool_registry.make_tool_worker") as mock_make,
            mock.patch("agentspan.agents.runtime.tool_registry.worker_task") as mock_wt,
            mock.patch("agentspan.agents.runtime.runtime._default_task_def") as mock_dtd,
            mock.patch("agentspan.agents.tool.get_tool_defs", return_value=[td]),
        ):
            mock_make.return_value = mock.MagicMock()
            mock_wt.return_value = lambda fn: fn
            mock_dtd.return_value = mock.MagicMock()

            from agentspan.agents.runtime.tool_registry import ToolRegistry

            registry = ToolRegistry()
            registry.register_tool_workers([td], "test_agent")

            mock_dtd.assert_called_once_with("my_tool", retry_count=0)
