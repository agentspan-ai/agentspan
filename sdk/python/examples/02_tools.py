# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""Tools — multiple tools, async, approval.

Demonstrates:
    - Multiple @tool functions
    - Approval-required tools (human-in-the-loop)
    - How tools become Conductor task definitions
    - Retry configuration (retry_count, retry_delay_seconds)

Requirements:
    - Conductor server with LLM support
    - AGENTSPAN_SERVER_URL=http://localhost:6767/api as environment variable
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


@tool(retry_count=5, retry_delay_seconds=10)
def fetch_stock_price(symbol: str) -> dict:
    """Fetch current stock price — retries up to 5 times on failure."""
    return {"symbol": symbol, "price": 142.50, "currency": "USD"}


agent = Agent(
    name="tool_demo_agent",
    model=settings.llm_model,
    tools=[get_weather, calculate, send_email, fetch_stock_price],
    instructions="You are a helpful assistant with access to weather, calculator, and email tools.",
)


if __name__ == "__main__":
    with AgentRuntime() as runtime:
        handle = runtime.start(agent, "send email to developer@orkes.io with current weather details in SF")
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
        # result = runtime.run(agent, "What is the weather in San Francisco?")
        # result.print_result()

        # Production pattern:
        # 1. Deploy once during CI/CD:
        # runtime.deploy(agent)
        #
        # 2. In a separate long-lived worker process:
        # runtime.serve(agent)

