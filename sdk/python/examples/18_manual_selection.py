# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""Manual Selection — human picks which agent speaks next.

Demonstrates ``strategy="manual"`` where the workflow pauses each turn
to let a human select which agent should respond.  The human interacts
via the ``AgentHandle.respond()`` API.

Flow:
    1. Workflow pauses with a HumanTask showing available agents
    2. Human picks an agent (e.g. {"selected": "writer"})
    3. Selected agent responds
    4. Repeat until max_turns

Requirements:
    - Conductor server with LLM support
    - AGENTSPAN_SERVER_URL=http://localhost:6767/api as environment variable
    - AGENTSPAN_LLM_MODEL=openai/gpt-4o-mini as environment variable
"""

from agentspan.agents import Agent, AgentRuntime, EventType, Strategy
from settings import settings

writer = Agent(
    name="writer",
    model=settings.llm_model,
    instructions="You are a creative writer. Expand on ideas with vivid prose.",
)

editor = Agent(
    name="editor",
    model=settings.llm_model,
    instructions="You are a strict editor. Improve clarity, fix issues, tighten prose.",
)

fact_checker = Agent(
    name="fact_checker",
    model=settings.llm_model,
    instructions="You verify claims and flag anything inaccurate or unsupported.",
)

# Manual strategy: human picks who speaks each turn
team = Agent(
    name="editorial_team",
    model=settings.llm_model,
    agents=[writer, editor, fact_checker],
    strategy=Strategy.MANUAL,
    max_turns=3,
)


if __name__ == "__main__":
    with AgentRuntime() as runtime:
        handle = runtime.start(
            team, "Write a short paragraph about the history of artificial intelligence."
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
        # result = runtime.run(writer, "Write a short paragraph about the history of artificial intelligence.")
        # result.print_result()

        # Production pattern:
        # 1. Deploy once during CI/CD:
        # runtime.deploy(team)
        #
        # 2. In a separate long-lived worker process:
        # runtime.serve(team)

