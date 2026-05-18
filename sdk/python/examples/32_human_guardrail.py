# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""Human-in-the-loop guardrail — ``on_fail="human"``.

Demonstrates a guardrail that pauses the workflow for human review when
the output fails validation.  Uses interactive streaming with schema-driven
console prompts so the human can approve, reject, or edit inline.

Requirements:
    - Conductor server with LLM support
    - AGENTSPAN_SERVER_URL=http://localhost:6767/api as environment variable
    - AGENTSPAN_LLM_MODEL=openai/gpt-4o-mini as environment variable
"""

from agentspan.agents import (
    Agent,
    AgentRuntime,
    EventType,
    Guardrail,
    GuardrailResult,
    OnFail,
    Position,
    guardrail,
    tool,
)
from settings import settings


# ── Guardrail ────────────────────────────────────────────────────────────

@guardrail
def compliance_check(content: str) -> GuardrailResult:
    """Flag any response that mentions specific financial terms for review."""
    flagged_terms = ["investment advice", "guaranteed returns", "risk-free"]
    for term in flagged_terms:
        if term.lower() in content.lower():
            return GuardrailResult(
                passed=False,
                message=f"Response contains flagged term: '{term}'. Needs human review.",
            )
    return GuardrailResult(passed=True)


# ── Tool ─────────────────────────────────────────────────────────────────

@tool
def get_market_data(ticker: str) -> dict:
    """Get current market data for a stock ticker."""
    return {
        "ticker": ticker,
        "price": 185.42,
        "change": "+2.3%",
        "volume": "45.2M",
    }


# ── Agent ────────────────────────────────────────────────────────────────

agent = Agent(
    name="finance_agent",
    model=settings.llm_model,
    tools=[get_market_data],
    instructions=(
        "You are a financial information assistant. Provide market data "
        "and general financial information. You may discuss investment "
        "strategies and returns."
    ),
    guardrails=[
        Guardrail(
            compliance_check,
            position=Position.OUTPUT,
            on_fail=OnFail.HUMAN,
            name="compliance",
        ),
    ],
)


if __name__ == "__main__":
    with AgentRuntime() as runtime:
        handle = runtime.start(
            agent,
            "Look up AAPL and explain whether it's a good investment. "
            "Include your opinion on potential returns.",
        )
        print(f"Started: {handle.execution_id}\n")

        for event in handle.stream():
            if event.type == EventType.THINKING:
                print(f"  [thinking] {event.content}")

            elif event.type == EventType.TOOL_CALL:
                print(f"  [tool_call] {event.tool_name}({event.args})")

            elif event.type == EventType.TOOL_RESULT:
                print(f"  [tool_result] {event.tool_name} -> {str(event.result)[:100]}")

            elif event.type == EventType.WAITING:
                status = handle.get_status()
                pt = status.pending_tool or {}
                schema = pt.get("response_schema", {})
                props = schema.get("properties", {})
                print("\n--- Human input required ---")
                response = {}
                for field, fs in props.items():
                    desc = fs.get("description") or fs.get("title", field)
                    if fs.get("type") == "boolean":
                        val = input(f"  {desc} (y/n): ").strip().lower()
                        response[field] = val in ("y", "yes")
                    else:
                        response[field] = input(f"  {desc}: ").strip()
                handle.respond(response)
                print()

            elif event.type == EventType.DONE:
                print(f"\nDone: {event.output}")

        # Non-interactive alternative (no HITL, will block on human tasks):
        # result = runtime.run(agent, "Look up AAPL and summarize the latest price movement.")
        # result.print_result()

        # Production pattern:
        # 1. Deploy once during CI/CD:
        # runtime.deploy(agent)
        #
        # 2. In a separate long-lived worker process:
        # runtime.serve(agent)

