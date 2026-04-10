# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""UserProxyAgent — human stand-in for interactive conversations.

Demonstrates ``UserProxyAgent`` which acts as a human proxy in
multi-agent conversations.  When it's the proxy's turn, the workflow
pauses for real human input.

Modes:
    - ALWAYS: always pause for human input
    - TERMINATE: pause only when conversation would end
    - NEVER: auto-respond (useful for testing)

Requirements:
    - Conductor server with LLM support
    - AGENTSPAN_SERVER_URL=http://localhost:6767/api as environment variable
    - AGENTSPAN_LLM_MODEL=openai/gpt-4o-mini as environment variable
"""

from agentspan.agents import Agent, AgentRuntime, EventType, Strategy
from settings import settings
from agentspan.agents.ext import UserProxyAgent

# ── Human proxy ──────────────────────────────────────────────────────

human = UserProxyAgent(
    name="human",
    human_input_mode="ALWAYS",
)

# ── AI assistant ─────────────────────────────────────────────────────

assistant = Agent(
    name="assistant",
    model=settings.llm_model,
    instructions=(
        "You are a helpful coding assistant. Help the user write Python code. "
        "Ask clarifying questions when needed."
    ),
)

# ── Round-robin conversation: human and assistant take turns ─────────

conversation = Agent(
    name="pair_programming",
    model=settings.llm_model,
    agents=[human, assistant],
    strategy=Strategy.ROUND_ROBIN,
    max_turns=4,  # 2 exchanges (human, assistant, human, assistant)
)


if __name__ == "__main__":
    with AgentRuntime() as runtime:
        handle = runtime.start(
            conversation,
            "Let's write a Python function to sort a list of dictionaries by a key.",
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
        # result = runtime.run(assistant, "Write a Python function to sort a list of dictionaries by a key.")
        # result.print_result()

        # Production pattern:
        # 1. Deploy once during CI/CD:
        # runtime.deploy(conversation)
        #
        # 2. In a separate long-lived worker process:
        # runtime.serve(conversation)

