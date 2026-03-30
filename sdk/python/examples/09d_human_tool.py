# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""Human Tool — LLM-initiated human interaction.

Unlike approval_required tools (09_human_in_the_loop.py) where humans gate
tool execution, ``human_tool`` lets the LLM **ask the human questions** at
any point.  The LLM decides when to call the tool, and the human's response
is returned as the tool output.

The tool is entirely server-side (Conductor HUMAN task) — no worker process
needed.  The server generates the response form and validation pipeline
automatically, so this works with any SDK language.

Demonstrates:
    - ``human_tool()`` for LLM-initiated human interaction
    - Mixing human tools with regular tools
    - The LLM using human input to make decisions

Requirements:
    - AGENTSPAN_SERVER_URL=http://localhost:8080/api
    - AGENTSPAN_LLM_MODEL (default: openai/gpt-4o-mini)
"""

from settings import settings

from agentspan.agents import Agent, AgentRuntime, EventType, human_tool, tool


@tool
def lookup_employee(name: str) -> dict:
    """Look up an employee by name and return their info."""
    employees = {
        "alice": {"name": "Alice Chen", "department": "Engineering", "level": "Senior"},
        "bob": {"name": "Bob Martinez", "department": "Sales", "level": "Manager"},
        "carol": {"name": "Carol Wu", "department": "Engineering", "level": "Staff"},
    }
    key = name.lower().split()[0]
    return employees.get(key, {"error": f"Employee '{name}' not found"})


@tool
def submit_ticket(title: str, priority: str, assignee: str) -> dict:
    """Submit an IT support ticket."""
    return {"ticket_id": "TKT-4821", "title": title, "priority": priority, "assignee": assignee}


ask_user = human_tool(
    name="ask_user",
    description="Ask the user a question when you need clarification or additional information.",
)

agent = Agent(
    name="it_support",
    model=settings.llm_model,
    tools=[lookup_employee, submit_ticket, ask_user],
    instructions=(
        "You are an IT support assistant. Help users create support tickets. "
        "Use lookup_employee to find employee info. "
        "If you need clarification about the issue or any details, use ask_user "
        "to ask the user directly. Always confirm the ticket details with the user "
        "before submitting."
    ),
)


if __name__ == "__main__":
    with AgentRuntime() as runtime:
        # Deploy to server. CLI alternative (recommended for CI/CD):
        #   agentspan deploy examples.09d_human_tool
        runtime.deploy(agent)
        runtime.serve(agent)

        # Quick test: uncomment below (and comment out serve) to run directly.
        # handle = runtime.start(agent, "I need to file a ticket for Alice about a laptop issue")
        # print(f"Workflow started: {handle.execution_id}\n")

        # for event in handle.stream():
        #     if event.type == EventType.THINKING:
        #         print(f"  [thinking] {event.content}")

        #     elif event.type == EventType.TOOL_CALL:
        #         print(f"  [tool_call] {event.tool_name}({event.args})")

        #     elif event.type == EventType.TOOL_RESULT:
        #         print(f"  [tool_result] {event.tool_name} -> {event.result}")

        #     elif event.type == EventType.WAITING:
        #         print("\n--- Human input required ---")
        #         response = input("  Your response: ").strip()
        #         handle.respond({"response": response})
        #         print()

        #     elif event.type == EventType.ERROR:
        #         print(f"  [error] {event.content}")

        #     elif event.type == EventType.DONE:
        #         print(f"\nResult: {event.output}")

