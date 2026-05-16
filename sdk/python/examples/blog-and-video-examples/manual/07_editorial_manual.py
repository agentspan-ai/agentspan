"""Manual Strategy — human picks which agent speaks next.

An editorial workflow where a human editor directs three specialists:
writer, fact checker, and copy editor. The human decides the order
based on what the draft needs at each stage.

Setup:
    pip install agentspan
    agentspan server start

    python 08_editorial_manual.py
"""

from agentspan.agents import Agent, AgentRuntime, Strategy, EventType


# ── Specialists ──────────────────────────────────────────────────────

writer = Agent(
    name="writer",
    model="openai/gpt-4o",
    instructions=(
        "You are a writer. Expand on ideas with clear, engaging prose. "
        "If you receive feedback from other agents, revise your work "
        "based on their suggestions. Keep your response focused and concise."
    ),
)

fact_checker = Agent(
    name="fact_checker",
    model="openai/gpt-4o",
    instructions=(
        "You are a fact checker. Review the content for accuracy. "
        "Flag any claims that are unsupported, exaggerated, or wrong. "
        "Be specific -- quote the exact text and explain the issue. "
        "If everything checks out, say so."
    ),
)

copy_editor = Agent(
    name="copy_editor",
    model="openai/gpt-4o",
    instructions=(
        "You are a copy editor. Review the content for grammar, clarity, "
        "tone, and flow. Suggest specific edits. Tighten prose. Remove "
        "filler. Make it read well. Return the improved version."
    ),
)

# ── Manual: human picks who speaks ──────────────────────────────────

team = Agent(
    name="editorial_team",
    model="openai/gpt-4o",
    agents=[writer, fact_checker, copy_editor],
    strategy=Strategy.MANUAL,
    max_turns=4,
)


if __name__ == "__main__":
    with AgentRuntime() as runtime:
        handle = runtime.start(
            team, "Write a short paragraph about the history of artificial intelligence."
        )
        print(f"Started: {handle.execution_id}\n")
        print("Available agents: writer, fact_checker, copy_editor")
        print("Type an agent name at each prompt to select who goes next.\n")

        for event in handle.stream():
            if event.type == EventType.WAITING:
                print("\n--- Pick the next agent ---")
                choice = input("> ").strip()
                handle.respond({"selected": choice})

            elif event.type == EventType.MESSAGE:
                if event.content:
                    print(f"\n{event.content}")

            elif event.type == EventType.DONE:
                if event.output:
                    out = event.output
                    if isinstance(out, dict):
                        out = out.get("result", str(out))
                    print(f"\n{'=' * 50}")
                    print("  FINAL OUTPUT")
                    print(f"{'=' * 50}\n")
                    print(out)
