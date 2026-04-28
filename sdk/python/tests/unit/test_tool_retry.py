# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""Unit tests for retry_count and retry_delay_seconds on the @tool decorator (issue #167 / PR #168)."""

import pytest

from agentspan.agents.tool import ToolDef, get_tool_def, tool


class TestToolRetryDefaults:
    """ToolDef defaults for retry fields are None (inherits runtime default)."""

    def test_tooldef_retry_count_default_is_none(self):
        td = ToolDef(name="my_tool")
        assert td.retry_count is None

    def test_tooldef_retry_delay_seconds_default_is_none(self):
        td = ToolDef(name="my_tool")
        assert td.retry_delay_seconds is None

    def test_bare_tool_decorator_retry_count_is_none(self):
        @tool
        def my_tool(x: str) -> str:
            """A simple tool."""
            return x

        assert my_tool._tool_def.retry_count is None

    def test_bare_tool_decorator_retry_delay_seconds_is_none(self):
        @tool
        def my_tool(x: str) -> str:
            """A simple tool."""
            return x

        assert my_tool._tool_def.retry_delay_seconds is None


class TestToolRetryCountParam:
    """@tool(retry_count=N) stores the value on the ToolDef."""

    def test_retry_count_zero(self):
        @tool(retry_count=0)
        def no_retry_tool(query: str) -> str:
            """No retries."""
            return query

        assert no_retry_tool._tool_def.retry_count == 0

    def test_retry_count_positive(self):
        @tool(retry_count=5)
        def five_retry_tool(query: str) -> str:
            """Five retries."""
            return query

        assert five_retry_tool._tool_def.retry_count == 5

    def test_retry_count_one(self):
        @tool(retry_count=1)
        def one_retry_tool(query: str) -> str:
            """One retry."""
            return query

        assert one_retry_tool._tool_def.retry_count == 1

    def test_retry_count_stored_on_raw_fn(self):
        """retry_count is also accessible on the raw function (for pickling)."""
        @tool(retry_count=3)
        def my_tool(x: str) -> str:
            """Tool."""
            return x

        # The raw fn also gets _tool_def attached
        assert my_tool._tool_def.retry_count == 3


class TestToolRetryDelaySecondsParam:
    """@tool(retry_delay_seconds=N) stores the value on the ToolDef."""

    def test_retry_delay_seconds_zero(self):
        @tool(retry_delay_seconds=0)
        def instant_retry_tool(query: str) -> str:
            """Instant retry."""
            return query

        assert instant_retry_tool._tool_def.retry_delay_seconds == 0

    def test_retry_delay_seconds_positive(self):
        @tool(retry_delay_seconds=10)
        def slow_retry_tool(query: str) -> str:
            """Slow retry."""
            return query

        assert slow_retry_tool._tool_def.retry_delay_seconds == 10

    def test_retry_delay_seconds_one(self):
        @tool(retry_delay_seconds=1)
        def one_second_retry_tool(query: str) -> str:
            """One second retry."""
            return query

        assert one_second_retry_tool._tool_def.retry_delay_seconds == 1


class TestToolRetryBothParams:
    """@tool(retry_count=N, retry_delay_seconds=M) stores both values."""

    def test_both_params_set(self):
        @tool(retry_count=3, retry_delay_seconds=5)
        def resilient_tool(query: str) -> str:
            """A resilient tool."""
            return query

        td = resilient_tool._tool_def
        assert td.retry_count == 3
        assert td.retry_delay_seconds == 5

    def test_both_params_zero(self):
        @tool(retry_count=0, retry_delay_seconds=0)
        def no_retry_tool(query: str) -> str:
            """No retry tool."""
            return query

        td = no_retry_tool._tool_def
        assert td.retry_count == 0
        assert td.retry_delay_seconds == 0

    def test_retry_count_set_delay_not_set(self):
        @tool(retry_count=4)
        def partial_retry_tool(query: str) -> str:
            """Partial retry config."""
            return query

        td = partial_retry_tool._tool_def
        assert td.retry_count == 4
        assert td.retry_delay_seconds is None

    def test_retry_delay_set_count_not_set(self):
        @tool(retry_delay_seconds=7)
        def partial_delay_tool(query: str) -> str:
            """Partial delay config."""
            return query

        td = partial_delay_tool._tool_def
        assert td.retry_count is None
        assert td.retry_delay_seconds == 7


class TestToolRetryWithOtherParams:
    """retry_count and retry_delay_seconds coexist with other @tool params."""

    def test_retry_with_approval_required(self):
        @tool(retry_count=2, retry_delay_seconds=3, approval_required=True)
        def approved_tool(x: str) -> str:
            """Needs approval."""
            return x

        td = approved_tool._tool_def
        assert td.retry_count == 2
        assert td.retry_delay_seconds == 3
        assert td.approval_required is True

    def test_retry_with_timeout(self):
        @tool(retry_count=1, retry_delay_seconds=2, timeout_seconds=30)
        def timed_tool(x: str) -> str:
            """Has timeout."""
            return x

        td = timed_tool._tool_def
        assert td.retry_count == 1
        assert td.retry_delay_seconds == 2
        assert td.timeout_seconds == 30

    def test_retry_with_custom_name(self):
        @tool(name="custom_name", retry_count=3, retry_delay_seconds=4)
        def my_func(x: str) -> str:
            """Custom named tool."""
            return x

        td = my_func._tool_def
        assert td.name == "custom_name"
        assert td.retry_count == 3
        assert td.retry_delay_seconds == 4

    def test_retry_with_stateful(self):
        @tool(retry_count=2, retry_delay_seconds=1, stateful=True)
        def stateful_tool(x: str) -> str:
            """Stateful tool."""
            return x

        td = stateful_tool._tool_def
        assert td.retry_count == 2
        assert td.retry_delay_seconds == 1
        assert td.stateful is True

    def test_retry_with_isolated_false(self):
        @tool(retry_count=5, retry_delay_seconds=2, isolated=False)
        def shared_tool(x: str) -> str:
            """Shared tool."""
            return x

        td = shared_tool._tool_def
        assert td.retry_count == 5
        assert td.retry_delay_seconds == 2
        assert td.isolated is False


class TestToolRetryGetToolDef:
    """get_tool_def() correctly extracts retry fields from @tool-decorated functions."""

    def test_get_tool_def_preserves_retry_count(self):
        @tool(retry_count=6)
        def my_tool(x: str) -> str:
            """Tool."""
            return x

        td = get_tool_def(my_tool)
        assert isinstance(td, ToolDef)
        assert td.retry_count == 6

    def test_get_tool_def_preserves_retry_delay_seconds(self):
        @tool(retry_delay_seconds=8)
        def my_tool(x: str) -> str:
            """Tool."""
            return x

        td = get_tool_def(my_tool)
        assert isinstance(td, ToolDef)
        assert td.retry_delay_seconds == 8

    def test_get_tool_def_preserves_both_retry_fields(self):
        @tool(retry_count=2, retry_delay_seconds=10)
        def my_tool(x: str) -> str:
            """Tool."""
            return x

        td = get_tool_def(my_tool)
        assert td.retry_count == 2
        assert td.retry_delay_seconds == 10

    def test_get_tool_def_from_tooldef_instance(self):
        td_direct = ToolDef(name="direct_tool", retry_count=7, retry_delay_seconds=3)
        td = get_tool_def(td_direct)
        assert td is td_direct
        assert td.retry_count == 7
        assert td.retry_delay_seconds == 3


class TestToolRetryFunctionStillCallable:
    """@tool with retry params does not break the decorated function's callability."""

    def test_tool_with_retry_is_callable(self):
        @tool(retry_count=3, retry_delay_seconds=2)
        def add(a: int, b: int) -> int:
            """Add two numbers."""
            return a + b

        assert add(2, 3) == 5

    def test_tool_with_retry_preserves_docstring(self):
        @tool(retry_count=1, retry_delay_seconds=1)
        def my_tool(x: str) -> str:
            """My tool docstring."""
            return x

        assert my_tool.__doc__ == "My tool docstring."
        assert my_tool._tool_def.description == "My tool docstring."

    def test_tool_with_retry_preserves_name(self):
        @tool(retry_count=2, retry_delay_seconds=2)
        def named_tool(x: str) -> str:
            """Named tool."""
            return x

        assert named_tool.__name__ == "named_tool"
        assert named_tool._tool_def.name == "named_tool"


class TestToolDefDirectConstruction:
    """ToolDef can be constructed directly with retry fields."""

    def test_tooldef_with_retry_count(self):
        td = ToolDef(name="t", retry_count=3)
        assert td.retry_count == 3
        assert td.retry_delay_seconds is None

    def test_tooldef_with_retry_delay_seconds(self):
        td = ToolDef(name="t", retry_delay_seconds=5)
        assert td.retry_count is None
        assert td.retry_delay_seconds == 5

    def test_tooldef_with_both_retry_fields(self):
        td = ToolDef(name="t", retry_count=4, retry_delay_seconds=6)
        assert td.retry_count == 4
        assert td.retry_delay_seconds == 6

    def test_tooldef_retry_fields_are_independent(self):
        td1 = ToolDef(name="t1", retry_count=1)
        td2 = ToolDef(name="t2", retry_count=2)
        assert td1.retry_count == 1
        assert td2.retry_count == 2
        # Ensure no shared state
        assert td1.retry_count != td2.retry_count
