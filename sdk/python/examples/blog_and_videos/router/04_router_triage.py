"""Issue Triage Bot — split-brain routing with a dedicated classifier.

A cheap classifier agent (gpt-4o-mini) reads each issue and picks the
right specialist. The specialist (gpt-4o) does the actual work. Two
brains, each doing what it is good at.

Setup:
    pip install agentspan
    agentspan server start

    python split-the-brain.py
"""

from conductor.ai.agents import Agent, AgentRuntime, Strategy


# ── Specialists ──────────────────────────────────────────────────────

bug_handler = Agent(
    name="bug_handler",
    model="openai/gpt-4o",
    instructions=(
        "You handle bug reports. Read the issue CAREFULLY.\n\n"
        "You MUST output EXACTLY this format and NOTHING else:\n\n"
        "Severity: P0/P1/P2/P3\n"
        "Component: <which part>\n"
        "Repro steps: <what the user described, or 'Not provided'>\n"
        "Labels: bug, <severity>\n"
        "Engineering summary: <2-3 sentences>\n\n"
        "ONLY use information the user actually wrote. No guesses."
    ),
)

feature_handler = Agent(
    name="feature_handler",
    model="openai/gpt-4o",
    instructions=(
        "You handle feature requests. Read the issue CAREFULLY.\n\n"
        "You MUST output EXACTLY this format and NOTHING else:\n\n"
        "Request: <one sentence>\n"
        "Use case: <in the user's words, or 'No use case provided'>\n"
        "Complexity: small/medium/large\n"
        "Labels: enhancement, <area>\n"
        "Community summary: <2-3 sentences>\n\n"
        "ONLY use information the user actually wrote. No guesses."
    ),
)

docs_handler = Agent(
    name="docs_handler",
    model="openai/gpt-4o",
    instructions=(
        "You handle docs issues and questions. Read the issue CAREFULLY.\n\n"
        "You MUST output EXACTLY this format and NOTHING else:\n\n"
        "Confusion: <what the user is stuck on>\n"
        "Doc gap: <which doc page is missing or unclear>\n"
        "Draft reply: <under 50 words — acknowledge the gap>\n"
        "Labels: documentation\n\n"
        "ONLY describe the gap. Do NOT answer the technical question."
    ),
)


# ── Classifier ───────────────────────────────────────────────────────

classifier = Agent(
    name="classifier",
    model="anthropic/claude-sonnet-4-6",
    instructions=(
        "You are an issue classifier. Read the issue and reply with "
        "EXACTLY ONE of these agent names — nothing else:\n\n"
        "- bug_handler: error, crash, traceback, regression, broken behavior\n"
        "- feature_handler: feature request, suggestion, enhancement\n"
        "- docs_handler: docs question, missing or unclear documentation\n\n"
        "Reply with the agent name only. No explanation. No punctuation."
    ),
)


# ── Router ───────────────────────────────────────────────────────────

triage = Agent(
    name="triage",
    model="anthropic/claude-sonnet-4-6",
    agents=[bug_handler, feature_handler, docs_handler],
    strategy=Strategy.ROUTER,
    router=classifier,
)


# ── Run ──────────────────────────────────────────────────────────────

ISSUES = [
    (
        "bug",
        "File upload fails with a 500 error when the filename has spaces. "
        "Uploading 'report.pdf' works, but 'Q1 report.pdf' returns a server "
        "error. Looks like the filename isn't being URL-encoded.",
    ),
    (
        "feature",
        "Would love a dark mode toggle. The current white background is "
        "really harsh at night. A system preference option would be ideal.",
    ),
    (
        "docs",
        "I can't figure out how to configure custom retry logic. The docs "
        "mention it's possible but don't show an example.",
    ),
]

if __name__ == "__main__":
    for label, issue in ISSUES:
        print(f"\n{'─' * 60}")
        print(f"[{label.upper()}] {issue[:80]}...")
        print("─" * 60)
        with AgentRuntime() as runtime:
            result = runtime.run(triage, issue)
            result.print_result()
