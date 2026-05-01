"""Random Strategy — diverse brainstorming with random agent selection.

Three thinkers with different styles are randomly selected each turn
to brainstorm ideas. The randomness creates variety — you never know
which perspective comes next.

Setup:
    pip install agentspan
    agentspan server start

    python 07_brainstorm_random.py
"""

from agentspan.agents import Agent, AgentRuntime, Strategy


# ── Thinkers ─────────────────────────────────────────────────────────

creative = Agent(
    name="creative",
    model="openai/gpt-4o",
    instructions=(
        "You are a creative thinker. Generate bold, unconventional ideas. "
        "Push boundaries. Think 'what if we did the opposite of what everyone "
        "expects?' Read what others said before you and build on their ideas "
        "or take them in a surprising direction. Keep your response to 2-3 paragraphs."
    ),
)

practical = Agent(
    name="practical",
    model="openai/gpt-4o",
    instructions=(
        "You are a practical thinker. Focus on what can actually be built "
        "and shipped. Consider timelines, resources, and feasibility. Read "
        "what others said before you and ground their ideas in reality — "
        "what would it take to actually do this? Keep your response to 2-3 paragraphs."
    ),
)

critical = Agent(
    name="critical",
    model="openai/gpt-4o",
    instructions=(
        "You are a critical thinker. Find the holes, the risks, the things "
        "nobody wants to talk about. Read what others said before you and "
        "stress-test their ideas — what could go wrong? What are they not "
        "considering? Keep your response to 2-3 paragraphs."
    ),
)

summarizer = Agent(
    name="summarizer",
    model="openai/gpt-4o",
    instructions=(
        "You observed a brainstorming session between a creative thinker, "
        "a practical thinker, and a critical thinker. Produce a summary:\n\n"
        "1. Top 3 ideas (ranked by potential)\n"
        "2. Biggest risk identified\n"
        "3. Recommended next step (one sentence)\n\n"
        "Be concise and actionable."
    ),
)

# ── Random: 6 turns, random agent each turn ─────────────────────────

brainstorm = Agent(
    name="brainstorm",
    model="openai/gpt-4o",
    agents=[creative, practical, critical],
    strategy=Strategy.RANDOM,
    max_turns=6,
)

pipeline = brainstorm >> summarizer


if __name__ == "__main__":
    with AgentRuntime() as runtime:
        result = runtime.run(
            pipeline,
            "How should a developer tools company get its first 1,000 users?",
        )
        result.print_result()
