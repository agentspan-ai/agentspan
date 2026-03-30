# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""Tools — multiple tools, async, approval.

Demonstrates:
    - Multiple @tool functions
    - Approval-required tools (human-in-the-loop)
    - How tools become Conductor task definitions

Requirements:
    - Conductor server with LLM support
    - AGENTSPAN_SERVER_URL=http://localhost:8080/api as environment variable
    - AGENTSPAN_LLM_MODEL=openai/gpt-4o-mini as environment variable
"""

from agentspan.agents import Agent, AgentRuntime, EventType, tool
from settings import settings


@tool
def get_weather(city: str) -> dict:
    """Get current weather for a city."""
    weather_data = {
        "new york": {"temp": 72, "condition": "Partly Cloudy"},
        "san francisco": {"temp": 58, "condition": "Foggy"},
        "miami": {"temp": 85, "condition": "Sunny"},
    }
    data = weather_data.get(city.lower(), {"temp": 70, "condition": "Clear"})
    return {"city": city, "temperature_f": data["temp"], "condition": data["condition"]}


@tool
def calculate(expression: str) -> dict:
    """Evaluate a math expression."""
    import math
    safe_builtins = {
        "abs": abs, "round": round, "min": min, "max": max,
        "sqrt": math.sqrt, "pow": pow, "pi": math.pi, "e": math.e,
    }
    try:
        result = eval(expression, {"__builtins__": {}}, safe_builtins)
        return {"expression": expression, "result": result}
    except Exception as e:
        return {"expression": expression, "error": str(e)}


@tool(approval_required=True, timeout_seconds=60)
def send_email(to: str, subject: str, body: str) -> dict:
    """Send an email."""
    # In production, this would actually send an email
    return {"status": "sent", "to": to, "subject": subject}


agent = Agent(
    name="tool_demo_agent",
    model=settings.llm_model,
    tools=[get_weather, calculate, send_email],
    instructions="You are a helpful assistant with access to weather, calculator, and email tools.",
)


if __name__ == "__main__":
    with AgentRuntime() as runtime:
        # Deploy to server. CLI alternative (recommended for CI/CD):
        #   agentspan deploy examples.02_tools
        runtime.deploy(agent)
        runtime.serve(agent)

        # Quick test: uncomment below (and comment out serve) to run directly.
        # result = runtime.stream(
        #     agent, "send email to developer@orkes.io with current weather details in SF"
        # )
        # print(f"Workflow started: {result.execution_id}\n")

        # for event in result:
        #     if event.type == EventType.THINKING:
        #         print(f"  [thinking] {event.content}")

        #     elif event.type == EventType.TOOL_CALL:
        #         print(f"  [tool_call] {event.tool_name}({event.args})")

        #     elif event.type == EventType.TOOL_RESULT:
        #         print(f"  [tool_result] {event.tool_name} -> {event.result}")

        #     elif event.type == EventType.WAITING:
        #         print(f"\n--- Human approval required for send_email ---")
        #         choice = input("  Approve? (y/n): ").strip().lower()
        #         if choice == "y":
        #             result.approve()
        #             print("  Approved!\n")
        #         else:
        #             reason = input("  Rejection reason: ").strip()
        #             result.reject(reason or "Rejected by user")
        #             print("  Rejected.\n")

        #     elif event.type == EventType.ERROR:
        #         print(f"  [error] {event.content}")

        #     elif event.type == EventType.DONE:
        #         print(f"\nResult: {event.output}")

        # final = result.get_result()
        # print(f"\nTool calls: {len(final.tool_calls)}")
        # print(f"Status: {final.status}")

