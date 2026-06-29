# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""OpenTelemetry tracing — industry-standard observability for agent execution.

Automatically instruments agent runs with spans for LLM calls, tool
executions, and handoffs.  Only activates if ``opentelemetry-api`` is
installed — otherwise all operations are no-ops.

Setup::

    pip install opentelemetry-api opentelemetry-sdk

    from opentelemetry import trace
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import ConsoleSpanExporter, SimpleSpanProcessor

    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(ConsoleSpanExporter()))
    trace.set_tracer_provider(provider)

    # Now all agent runs emit OTel spans automatically
    from conductor.ai.agents import Agent, run
    result = run(agent, "Hello!")

The tracer emits spans for:

- ``agent.run`` — top-level agent execution
- ``agent.compile`` — workflow compilation
- ``agent.llm_call`` — each LLM invocation
- ``agent.tool_call`` — each tool execution
- ``agent.handoff`` — agent-to-agent transitions
"""

from __future__ import annotations

import logging
from contextlib import contextmanager
from typing import Any, Dict, Iterator, Optional

logger = logging.getLogger("conductor.ai.agents.tracing")

# ── OTel availability detection ────────────────────────────────────────

_HAS_OTEL = False
_tracer = None

try:
    from opentelemetry import trace
    from opentelemetry.trace import StatusCode

    _HAS_OTEL = True
except ImportError:
    pass


def _get_tracer():
    """Get or create the OTel tracer for the agents SDK."""
    global _tracer
    if not _HAS_OTEL:
        return None
    if _tracer is None:
        _tracer = trace.get_tracer("conductor.ai.agents", "1.0.0")
    return _tracer


# ── Public API ─────────────────────────────────────────────────────────


def is_tracing_enabled() -> bool:
    """Check if OpenTelemetry tracing is available and configured."""
    return _HAS_OTEL


@contextmanager
def trace_agent_run(
    agent_name: str,
    prompt: str,
    model: str = "",
    session_id: str = "",
) -> Iterator[Optional[Any]]:
    """Create a span for an agent execution.

    Usage::

        with trace_agent_run("my_agent", "Hello!", model="openai/gpt-4o") as span:
            result = runtime.run(agent, "Hello!")
            if span:
                span.set_attribute("agent.output_length", len(str(result.output)))

    Args:
        agent_name: The agent name.
        prompt: The user prompt.
        model: The LLM model identifier.
        session_id: Optional session ID.

    Yields:
        The OTel span (or ``None`` if tracing is not available).
    """
    tracer = _get_tracer()
    if tracer is None:
        yield None
        return

    with tracer.start_as_current_span("agent.run") as span:
        span.set_attribute("agent.name", agent_name)
        span.set_attribute("agent.model", model)
        span.set_attribute("agent.prompt_length", len(prompt))
        if session_id:
            span.set_attribute("agent.session_id", session_id)
        try:
            yield span
            span.set_status(StatusCode.OK)
        except Exception as e:
            span.set_status(StatusCode.ERROR, str(e))
            span.record_exception(e)
            raise


@contextmanager
def trace_compile(agent_name: str, strategy: str = "") -> Iterator[Optional[Any]]:
    """Create a span for agent compilation.

    Args:
        agent_name: The agent being compiled.
        strategy: The multi-agent strategy (if applicable).
    """
    tracer = _get_tracer()
    if tracer is None:
        yield None
        return

    with tracer.start_as_current_span("agent.compile") as span:
        span.set_attribute("agent.name", agent_name)
        if strategy:
            val = strategy.value if hasattr(strategy, "value") else strategy
            span.set_attribute("agent.strategy", val)
        yield span


@contextmanager
def trace_llm_call(
    agent_name: str,
    model: str,
    prompt_tokens: int = 0,
    completion_tokens: int = 0,
) -> Iterator[Optional[Any]]:
    """Create a span for an LLM call.

    Args:
        agent_name: The agent making the call.
        model: The LLM model.
        prompt_tokens: Input token count (set after call completes).
        completion_tokens: Output token count (set after call completes).
    """
    tracer = _get_tracer()
    if tracer is None:
        yield None
        return

    with tracer.start_as_current_span("agent.llm_call") as span:
        span.set_attribute("agent.name", agent_name)
        span.set_attribute("llm.model", model)
        yield span
        if prompt_tokens:
            span.set_attribute("llm.prompt_tokens", prompt_tokens)
        if completion_tokens:
            span.set_attribute("llm.completion_tokens", completion_tokens)


@contextmanager
def trace_tool_call(
    agent_name: str,
    tool_name: str,
    args: Optional[Dict[str, Any]] = None,
) -> Iterator[Optional[Any]]:
    """Create a span for a tool execution.

    Args:
        agent_name: The agent calling the tool.
        tool_name: The tool being called.
        args: The tool arguments.
    """
    tracer = _get_tracer()
    if tracer is None:
        yield None
        return

    with tracer.start_as_current_span("agent.tool_call") as span:
        span.set_attribute("agent.name", agent_name)
        span.set_attribute("tool.name", tool_name)
        if args:
            span.set_attribute("tool.args", str(args)[:1000])
        try:
            yield span
            span.set_status(StatusCode.OK)
        except Exception as e:
            span.set_status(StatusCode.ERROR, str(e))
            span.record_exception(e)
            raise


@contextmanager
def trace_handoff(
    source_agent: str,
    target_agent: str,
) -> Iterator[Optional[Any]]:
    """Create a span for an agent handoff.

    Args:
        source_agent: The agent handing off.
        target_agent: The agent receiving control.
    """
    tracer = _get_tracer()
    if tracer is None:
        yield None
        return

    with tracer.start_as_current_span("agent.handoff") as span:
        span.set_attribute("handoff.source", source_agent)
        span.set_attribute("handoff.target", target_agent)
        yield span


def record_token_usage(
    span: Optional[Any],
    prompt_tokens: int = 0,
    completion_tokens: int = 0,
    total_tokens: int = 0,
) -> None:
    """Record token usage on an existing span.

    Args:
        span: The OTel span (or ``None``).
        prompt_tokens: Input tokens.
        completion_tokens: Output tokens.
        total_tokens: Total tokens.
    """
    if span is None or not _HAS_OTEL:
        return
    if prompt_tokens:
        span.set_attribute("llm.prompt_tokens", prompt_tokens)
    if completion_tokens:
        span.set_attribute("llm.completion_tokens", completion_tokens)
    if total_tokens:
        span.set_attribute("llm.total_tokens", total_tokens)
