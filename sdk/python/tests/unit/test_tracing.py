# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""Unit tests for OpenTelemetry tracing instrumentation."""

from unittest.mock import MagicMock

import pytest

import conductor.ai.agents.tracing as tracing_mod


class TestNoopWhenOtelNotInstalled:
    """When OTel is not installed, all tracing functions are no-ops."""

    def test_is_tracing_enabled_reflects_flag(self):
        original = tracing_mod._HAS_OTEL
        try:
            tracing_mod._HAS_OTEL = False
            assert tracing_mod.is_tracing_enabled() is False
            tracing_mod._HAS_OTEL = True
            assert tracing_mod.is_tracing_enabled() is True
        finally:
            tracing_mod._HAS_OTEL = original

    def test_trace_agent_run_noop(self):
        original = tracing_mod._HAS_OTEL
        original_tracer = tracing_mod._tracer
        try:
            tracing_mod._HAS_OTEL = False
            tracing_mod._tracer = None
            with tracing_mod.trace_agent_run("agent", "prompt") as span:
                assert span is None
        finally:
            tracing_mod._HAS_OTEL = original
            tracing_mod._tracer = original_tracer

    def test_trace_compile_noop(self):
        original = tracing_mod._HAS_OTEL
        original_tracer = tracing_mod._tracer
        try:
            tracing_mod._HAS_OTEL = False
            tracing_mod._tracer = None
            with tracing_mod.trace_compile("agent") as span:
                assert span is None
        finally:
            tracing_mod._HAS_OTEL = original
            tracing_mod._tracer = original_tracer

    def test_trace_llm_call_noop(self):
        original = tracing_mod._HAS_OTEL
        original_tracer = tracing_mod._tracer
        try:
            tracing_mod._HAS_OTEL = False
            tracing_mod._tracer = None
            with tracing_mod.trace_llm_call("agent", "gpt-4o") as span:
                assert span is None
        finally:
            tracing_mod._HAS_OTEL = original
            tracing_mod._tracer = original_tracer

    def test_trace_tool_call_noop(self):
        original = tracing_mod._HAS_OTEL
        original_tracer = tracing_mod._tracer
        try:
            tracing_mod._HAS_OTEL = False
            tracing_mod._tracer = None
            with tracing_mod.trace_tool_call("agent", "my_tool") as span:
                assert span is None
        finally:
            tracing_mod._HAS_OTEL = original
            tracing_mod._tracer = original_tracer

    def test_trace_handoff_noop(self):
        original = tracing_mod._HAS_OTEL
        original_tracer = tracing_mod._tracer
        try:
            tracing_mod._HAS_OTEL = False
            tracing_mod._tracer = None
            with tracing_mod.trace_handoff("agent_a", "agent_b") as span:
                assert span is None
        finally:
            tracing_mod._HAS_OTEL = original
            tracing_mod._tracer = original_tracer

    def test_record_token_usage_noop(self):
        tracing_mod.record_token_usage(None, prompt_tokens=100)
        # Should not raise


class TestWithMockedOtel:
    """Test tracing functions with mocked OpenTelemetry.

    We need to mock both the tracer AND the StatusCode enum, since
    StatusCode may not exist if opentelemetry is not installed.
    """

    def _setup_mocks(self):
        """Set up mock tracer, span, and StatusCode."""
        mock_span = MagicMock()
        mock_tracer = MagicMock()
        # Make start_as_current_span return a context manager that yields mock_span
        mock_cm = MagicMock()
        mock_cm.__enter__ = MagicMock(return_value=mock_span)
        mock_cm.__exit__ = MagicMock(return_value=False)
        mock_tracer.start_as_current_span.return_value = mock_cm

        mock_status_code = MagicMock()
        mock_status_code.OK = "OK"
        mock_status_code.ERROR = "ERROR"

        return mock_tracer, mock_span, mock_status_code

    def test_trace_agent_run_creates_span(self):
        mock_tracer, mock_span, mock_status_code = self._setup_mocks()
        original_has = tracing_mod._HAS_OTEL
        original_tracer = tracing_mod._tracer
        try:
            tracing_mod._HAS_OTEL = True
            tracing_mod._tracer = mock_tracer
            # Patch StatusCode in the tracing module
            tracing_mod.StatusCode = mock_status_code

            with tracing_mod.trace_agent_run(
                "my_agent", "hello", model="gpt-4o", session_id="s1"
            ) as span:
                assert span is mock_span

            mock_tracer.start_as_current_span.assert_called_once_with("agent.run")
            mock_span.set_attribute.assert_any_call("agent.name", "my_agent")
            mock_span.set_attribute.assert_any_call("agent.model", "gpt-4o")
            mock_span.set_attribute.assert_any_call("agent.session_id", "s1")
            mock_span.set_status.assert_called_once_with("OK")
        finally:
            tracing_mod._HAS_OTEL = original_has
            tracing_mod._tracer = original_tracer
            if hasattr(tracing_mod, "StatusCode") and isinstance(tracing_mod.StatusCode, MagicMock):
                delattr(tracing_mod, "StatusCode")

    def test_trace_agent_run_records_error(self):
        mock_tracer, mock_span, mock_status_code = self._setup_mocks()
        original_has = tracing_mod._HAS_OTEL
        original_tracer = tracing_mod._tracer
        try:
            tracing_mod._HAS_OTEL = True
            tracing_mod._tracer = mock_tracer
            tracing_mod.StatusCode = mock_status_code

            with pytest.raises(ValueError, match="test error"):
                with tracing_mod.trace_agent_run("agent", "prompt") as span:
                    raise ValueError("test error")

            mock_span.record_exception.assert_called_once()
            # Check that error status was set
            mock_span.set_status.assert_called_once_with("ERROR", "test error")
        finally:
            tracing_mod._HAS_OTEL = original_has
            tracing_mod._tracer = original_tracer
            if hasattr(tracing_mod, "StatusCode") and isinstance(tracing_mod.StatusCode, MagicMock):
                delattr(tracing_mod, "StatusCode")

    def test_trace_compile_creates_span(self):
        mock_tracer, mock_span, mock_status_code = self._setup_mocks()
        original_has = tracing_mod._HAS_OTEL
        original_tracer = tracing_mod._tracer
        try:
            tracing_mod._HAS_OTEL = True
            tracing_mod._tracer = mock_tracer

            with tracing_mod.trace_compile("my_agent", strategy="round_robin") as span:
                assert span is mock_span

            mock_tracer.start_as_current_span.assert_called_once_with("agent.compile")
            mock_span.set_attribute.assert_any_call("agent.name", "my_agent")
            mock_span.set_attribute.assert_any_call("agent.strategy", "round_robin")
        finally:
            tracing_mod._HAS_OTEL = original_has
            tracing_mod._tracer = original_tracer

    def test_trace_llm_call_creates_span(self):
        mock_tracer, mock_span, mock_status_code = self._setup_mocks()
        original_has = tracing_mod._HAS_OTEL
        original_tracer = tracing_mod._tracer
        try:
            tracing_mod._HAS_OTEL = True
            tracing_mod._tracer = mock_tracer

            with tracing_mod.trace_llm_call(
                "agent", "gpt-4o", prompt_tokens=100, completion_tokens=50
            ) as span:
                assert span is mock_span

            mock_span.set_attribute.assert_any_call("llm.model", "gpt-4o")
        finally:
            tracing_mod._HAS_OTEL = original_has
            tracing_mod._tracer = original_tracer

    def test_trace_tool_call_creates_span(self):
        mock_tracer, mock_span, mock_status_code = self._setup_mocks()
        original_has = tracing_mod._HAS_OTEL
        original_tracer = tracing_mod._tracer
        try:
            tracing_mod._HAS_OTEL = True
            tracing_mod._tracer = mock_tracer
            tracing_mod.StatusCode = mock_status_code

            with tracing_mod.trace_tool_call("agent", "my_tool", args={"x": 1}) as span:
                assert span is mock_span

            mock_span.set_attribute.assert_any_call("tool.name", "my_tool")
            mock_span.set_status.assert_called_once_with("OK")
        finally:
            tracing_mod._HAS_OTEL = original_has
            tracing_mod._tracer = original_tracer
            if hasattr(tracing_mod, "StatusCode") and isinstance(tracing_mod.StatusCode, MagicMock):
                delattr(tracing_mod, "StatusCode")

    def test_trace_tool_call_records_error(self):
        mock_tracer, mock_span, mock_status_code = self._setup_mocks()
        original_has = tracing_mod._HAS_OTEL
        original_tracer = tracing_mod._tracer
        try:
            tracing_mod._HAS_OTEL = True
            tracing_mod._tracer = mock_tracer
            tracing_mod.StatusCode = mock_status_code

            with pytest.raises(RuntimeError):
                with tracing_mod.trace_tool_call("agent", "bad_tool") as span:
                    raise RuntimeError("tool failed")

            mock_span.record_exception.assert_called_once()
            mock_span.set_status.assert_called_once_with("ERROR", "tool failed")
        finally:
            tracing_mod._HAS_OTEL = original_has
            tracing_mod._tracer = original_tracer
            if hasattr(tracing_mod, "StatusCode") and isinstance(tracing_mod.StatusCode, MagicMock):
                delattr(tracing_mod, "StatusCode")

    def test_trace_handoff_creates_span(self):
        mock_tracer, mock_span, mock_status_code = self._setup_mocks()
        original_has = tracing_mod._HAS_OTEL
        original_tracer = tracing_mod._tracer
        try:
            tracing_mod._HAS_OTEL = True
            tracing_mod._tracer = mock_tracer

            with tracing_mod.trace_handoff("agent_a", "agent_b") as span:
                assert span is mock_span

            mock_span.set_attribute.assert_any_call("handoff.source", "agent_a")
            mock_span.set_attribute.assert_any_call("handoff.target", "agent_b")
        finally:
            tracing_mod._HAS_OTEL = original_has
            tracing_mod._tracer = original_tracer

    def test_record_token_usage(self):
        mock_span = MagicMock()
        original = tracing_mod._HAS_OTEL
        try:
            tracing_mod._HAS_OTEL = True
            tracing_mod.record_token_usage(
                mock_span, prompt_tokens=100, completion_tokens=50, total_tokens=150
            )
            mock_span.set_attribute.assert_any_call("llm.prompt_tokens", 100)
            mock_span.set_attribute.assert_any_call("llm.completion_tokens", 50)
            mock_span.set_attribute.assert_any_call("llm.total_tokens", 150)
        finally:
            tracing_mod._HAS_OTEL = original

    def test_record_token_usage_skips_zeros(self):
        mock_span = MagicMock()
        original = tracing_mod._HAS_OTEL
        try:
            tracing_mod._HAS_OTEL = True
            tracing_mod.record_token_usage(mock_span, prompt_tokens=0, completion_tokens=0)
            mock_span.set_attribute.assert_not_called()
        finally:
            tracing_mod._HAS_OTEL = original
