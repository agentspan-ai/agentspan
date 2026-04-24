# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""Unit tests for retry configuration on the @tool decorator (issue #150).

These are pure unit tests — no server, no mocks, just verifying the
dataclass and decorator wiring.
"""

import pytest

from agentspan.agents.tool import ToolDef, tool
from agentspan.agents.runtime.runtime import _default_task_def
from agentspan.agents.config_serializer import AgentConfigSerializer


# ── @tool decorator tests ────────────────────────────────────────────────────


def test_tool_decorator_default_retry_fields_are_none():
    """Bare @tool should leave all retry fields as None."""

    @tool
    def my_tool(x: str) -> str:
        """A simple tool."""
        return x

    td = my_tool._tool_def
    assert td.retry_count is None
    assert td.retry_delay_seconds is None
    assert td.retry_logic is None


def test_tool_decorator_retry_count():
    """@tool(retry_count=10) should set retry_count on the ToolDef."""

    @tool(retry_count=10)
    def my_tool(x: str) -> str:
        """A simple tool."""
        return x

    assert my_tool._tool_def.retry_count == 10
    assert my_tool._tool_def.retry_delay_seconds is None
    assert my_tool._tool_def.retry_logic is None


def test_tool_decorator_retry_delay_seconds():
    """@tool(retry_delay_seconds=5) should set retry_delay_seconds on the ToolDef."""

    @tool(retry_delay_seconds=5)
    def my_tool(x: str) -> str:
        """A simple tool."""
        return x

    assert my_tool._tool_def.retry_count is None
    assert my_tool._tool_def.retry_delay_seconds == 5
    assert my_tool._tool_def.retry_logic is None


def test_tool_decorator_retry_logic():
    """@tool(retry_logic='EXPONENTIAL_BACKOFF') should set retry_logic on the ToolDef."""

    @tool(retry_logic="EXPONENTIAL_BACKOFF")
    def my_tool(x: str) -> str:
        """A simple tool."""
        return x

    assert my_tool._tool_def.retry_count is None
    assert my_tool._tool_def.retry_delay_seconds is None
    assert my_tool._tool_def.retry_logic == "EXPONENTIAL_BACKOFF"


def test_tool_decorator_zero_retries():
    """@tool(retry_count=0) should set retry_count=0 (not None, not falsy-skipped)."""

    @tool(retry_count=0)
    def my_tool(x: str) -> str:
        """A simple tool."""
        return x

    # Must be exactly 0, not None
    assert my_tool._tool_def.retry_count == 0
    assert my_tool._tool_def.retry_count is not None


def test_tool_decorator_all_retry_params():
    """@tool with all three retry params should set all three fields."""

    @tool(retry_count=5, retry_delay_seconds=10, retry_logic="FIXED")
    def my_tool(x: str) -> str:
        """A simple tool."""
        return x

    td = my_tool._tool_def
    assert td.retry_count == 5
    assert td.retry_delay_seconds == 10
    assert td.retry_logic == "FIXED"


def test_tool_decorator_retry_preserved_on_raw_fn():
    """Retry fields should be set on both the wrapper and the raw function."""

    @tool(retry_count=3, retry_delay_seconds=7, retry_logic="LINEAR_BACKOFF")
    def my_tool(x: str) -> str:
        """A simple tool."""
        return x

    # Both the wrapper and the raw fn should have _tool_def
    assert my_tool._tool_def.retry_count == 3
    assert my_tool._tool_def.retry_delay_seconds == 7
    assert my_tool._tool_def.retry_logic == "LINEAR_BACKOFF"


# ── _default_task_def tests ──────────────────────────────────────────────────


def test_default_task_def_uses_defaults_when_none():
    """_default_task_def with no overrides should use the hardcoded defaults."""
    td = _default_task_def("test_task")
    assert td.retry_count == 2
    assert td.retry_delay_seconds == 2
    assert td.retry_logic == "LINEAR_BACKOFF"


def test_default_task_def_uses_tool_retry_config():
    """_default_task_def with explicit overrides should use those values."""
    td = _default_task_def(
        "test_task",
        retry_count=5,
        retry_delay_seconds=10,
        retry_logic="EXPONENTIAL_BACKOFF",
    )
    assert td.retry_count == 5
    assert td.retry_delay_seconds == 10
    assert td.retry_logic == "EXPONENTIAL_BACKOFF"


def test_default_task_def_zero_retry_count():
    """_default_task_def(retry_count=0) should set 0, not the default 2."""
    td = _default_task_def("test_task", retry_count=0)
    assert td.retry_count == 0


def test_default_task_def_partial_overrides():
    """Partial overrides should only change the specified fields."""
    td = _default_task_def("test_task", retry_count=7)
    assert td.retry_count == 7
    assert td.retry_delay_seconds == 2          # default
    assert td.retry_logic == "LINEAR_BACKOFF"   # default


def test_default_task_def_fixed_logic():
    """_default_task_def with retry_logic='FIXED' should set FIXED."""
    td = _default_task_def("test_task", retry_logic="FIXED")
    assert td.retry_logic == "FIXED"
    assert td.retry_count == 2          # default
    assert td.retry_delay_seconds == 2  # default


# ── AgentConfigSerializer._serialize_tool tests ──────────────────────────────


def _make_worker_tool_def(**kwargs) -> ToolDef:
    """Helper: create a minimal worker ToolDef with optional retry fields."""
    return ToolDef(
        name="my_tool",
        description="A test tool",
        input_schema={"type": "object", "properties": {"x": {"type": "string"}}},
        tool_type="worker",
        **kwargs,
    )


def test_serializer_includes_retry_in_config():
    """Serializer should include retryCount/retryDelaySeconds/retryLogic in config."""
    td = _make_worker_tool_def(retry_count=5, retry_delay_seconds=10, retry_logic="FIXED")
    serializer = AgentConfigSerializer()
    result = serializer._serialize_tool(td)

    assert "config" in result
    assert result["config"]["retryCount"] == 5
    assert result["config"]["retryDelaySeconds"] == 10
    assert result["config"]["retryLogic"] == "FIXED"


def test_serializer_omits_retry_when_none():
    """Serializer should NOT include retry keys when all retry fields are None."""
    td = _make_worker_tool_def()  # no retry fields set
    serializer = AgentConfigSerializer()
    result = serializer._serialize_tool(td)

    config = result.get("config", {})
    assert "retryCount" not in config
    assert "retryDelaySeconds" not in config
    assert "retryLogic" not in config


def test_serializer_partial_retry_fields():
    """Serializer should only include the retry keys that are set."""
    td = _make_worker_tool_def(retry_count=3)
    serializer = AgentConfigSerializer()
    result = serializer._serialize_tool(td)

    assert "config" in result
    assert result["config"]["retryCount"] == 3
    assert "retryDelaySeconds" not in result["config"]
    assert "retryLogic" not in result["config"]


def test_serializer_zero_retry_count_included():
    """Serializer should include retryCount=0 (not skip it as falsy)."""
    td = _make_worker_tool_def(retry_count=0)
    serializer = AgentConfigSerializer()
    result = serializer._serialize_tool(td)

    assert "config" in result
    assert result["config"]["retryCount"] == 0


def test_serializer_retry_alongside_credentials():
    """Retry config should coexist with credentials in the config dict."""
    td = _make_worker_tool_def(
        retry_count=2,
        retry_logic="LINEAR_BACKOFF",
        credentials=["MY_API_KEY"],
    )
    serializer = AgentConfigSerializer()
    result = serializer._serialize_tool(td)

    assert "config" in result
    assert result["config"]["retryCount"] == 2
    assert result["config"]["retryLogic"] == "LINEAR_BACKOFF"
    assert result["config"]["credentials"] == ["MY_API_KEY"]
