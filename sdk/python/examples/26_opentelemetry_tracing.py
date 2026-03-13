# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""OpenTelemetry Tracing — industry-standard observability.

Demonstrates OTel instrumentation for agent execution. When
opentelemetry-sdk is installed and configured, all agent runs
automatically emit spans for:

- agent.run (top-level execution)
- agent.compile (workflow compilation)
- agent.llm_call (each LLM invocation)
- agent.tool_call (each tool execution)
- agent.handoff (agent transitions)

Requirements:
    - pip install opentelemetry-api opentelemetry-sdk
    - Conductor server with LLM support
    - AGENTSPAN_SERVER_URL=http://localhost:8080/api in .env or environment
    - AGENT_LLM_MODEL=openai/gpt-4o-mini in .env or environment
"""

from agentspan.agents import Agent, AgentRuntime, is_tracing_enabled, tool
from settings import settings
from agentspan.agents.tracing import trace_agent_run, trace_tool_call

# ── Check if OTel is available ───────────────────────────────────────

print(f"OpenTelemetry available: {is_tracing_enabled()}")

if is_tracing_enabled():
    # Configure OTel exporter (console for demo)
    from opentelemetry import trace
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import (
        ConsoleSpanExporter,
        SimpleSpanProcessor,
    )

    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(ConsoleSpanExporter()))
    trace.set_tracer_provider(provider)
    print("OTel configured with ConsoleSpanExporter")

# ── Agent with tools ─────────────────────────────────────────────────

@tool
def lookup(query: str) -> str:
    """Look up information."""
    return f"Result for '{query}': Python was created by Guido van Rossum in 1991."

agent = Agent(
    name="traced_agent",
    model=settings.llm_model,
    tools=[lookup],
    instructions="You are a helpful assistant. Use the lookup tool when needed.",
)

# ── Manual tracing (works even alongside automatic runtime tracing) ──

with AgentRuntime() as runtime:
    # The runtime automatically creates spans if OTel is configured.
    # You can also create manual spans for custom instrumentation:
    with trace_agent_run("traced_agent", "Who created Python?", model=settings.llm_model) as span:
        result = runtime.run(agent, "Who created Python?")
        if span:
            span.set_attribute("agent.output_length", len(str(result.output)))

    result.print_result()

    if result.token_usage:
        print(f"Tokens: {result.token_usage.total_tokens}")
