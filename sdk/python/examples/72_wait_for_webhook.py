# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""Wait for Webhook — continuously listen for inbound webhook events.

Demonstrates:
    - webhook_tool: waits for a matching webhook event (Conductor WAIT_FOR_WEBHOOK task)
    - Mixing a server-side webhook tool with a local Python notification tool
    - Looping agent that keeps listening indefinitely

The agent loops forever: each iteration waits for a webhook with $['agent'] == "notifier",
then prints the value of $['message'] from the payload as a console notification.

Requirements:
    - Conductor server with LLM support
    - AGENTSPAN_SERVER_URL=http://localhost:8080/api as environment variable
    - AGENTSPAN_LLM_MODEL=openai/gpt-4o-mini as environment variable
"""

from agentspan.agents import Agent, AgentRuntime, tool, webhook_tool
from settings import settings


# Python tool (needs a worker) — prints the notification to the console
@tool
def send_notification(message: str) -> str:
    """Send a notification by printing it to the console."""
    print(f"\n*** NOTIFICATION: {message} ***\n")
    return f"Notification sent: {message}"


# Server-side tool — waits for a matching webhook event (no worker needed)
incoming_event = webhook_tool(
    name="wait_for_event",
    description="Wait for an inbound webhook event targeted at this notifier agent.",
    matches={
        "$['agent']": "notifier",
    },
)

agent = Agent(
    name="webhook_notifier",
    model=settings.llm_model,
    tools=[incoming_event, send_notification],
    max_turns=10000,
    instructions=(
        "You are a notification agent that runs forever in a loop. "
        "Repeat this cycle indefinitely: "
        "1. Call wait_for_event to wait for the next webhook. "
        "2. Extract the 'message' field from the webhook payload. "
        "3. Call send_notification with that message. "
        "4. Go back to step 1 immediately — never stop."
    ),
)

with AgentRuntime() as runtime:
    result = runtime.run(agent, "Start the notification loop.")
    result.print_result()
