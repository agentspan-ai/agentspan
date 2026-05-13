import warnings
import logging

warnings.filterwarnings("ignore")
logging.disable(logging.CRITICAL)

"""Issue Triage with Handoff Strategy

A triage bot that reads a GitHub issue and hands off to the right
specialist agent based on what the issue is about. The LLM decides
the routing at runtime — not a fixed pipeline, not keyword matching.

Setup:
    pip install agentspan
    agentspan server start

    python 03_issue_triage_handoff.py
"""

from agentspan.agents import Agent, AgentRuntime, Strategy


# ── Specialist Agents ────────────────────────────────────────────

bug_handler = Agent(
    name="bug_handler",
    model="openai/gpt-4o",
    instructions=(
        "You handle bug reports. Read the issue CAREFULLY.\n\n"
        "You MUST output EXACTLY this format and NOTHING else — no greeting, "
        "no explanation, no sign-off, no extra text:\n\n"
        "Severity: P0/P1/P2/P3\n"
        "Component: <which part>\n"
        "Repro steps: <what the user described, or 'Not provided'>\n"
        "Labels: bug, <severity>\n"
        "Engineering summary: <2-3 sentences>\n\n"
        "Example output:\n"
        "Severity: P2\n"
        "Component: REST API — /users endpoint\n"
        "Repro steps: Send a GET request with limit=0. Returns 500 instead of empty list.\n"
        "Labels: bug, P2\n"
        "Engineering summary: Off-by-one in pagination. The /users endpoint does not "
        "handle limit=0. Affects v2.1+ only.\n\n"
        "RULES:\n"
        "- ONLY use information the user actually wrote. No guesses.\n"
        "- Do NOT suggest workarounds or fixes.\n"
        "- Do NOT add any text outside the format."
    ),
)

feature_handler = Agent(
    name="feature_handler",
    model="openai/gpt-4o",
    instructions=(
        "You handle feature requests. Read the issue CAREFULLY.\n\n"
        "You MUST output EXACTLY this format and NOTHING else — no greeting, "
        "no explanation, no sign-off, no extra text:\n\n"
        "Request: <one sentence>\n"
        "Use case: <in the user's words, or 'No use case provided'>\n"
        "Complexity: small/medium/large\n"
        "Labels: enhancement, <area>\n"
        "Community summary: <2-3 sentences>\n\n"
        "Example output:\n"
        "Request: Add CSV export for agent execution history.\n"
        "Use case: User wants to import execution data into their BI tool for "
        "weekly reporting.\n"
        "Complexity: small\n"
        "Labels: enhancement, observability\n"
        "Community summary: Request for CSV export of execution history. User "
        "needs it for BI/reporting integration. Low complexity — the data is "
        "already queryable.\n\n"
        "RULES:\n"
        "- ONLY use information the user actually wrote. No guesses.\n"
        "- Do NOT promise timelines or delivery.\n"
        "- Do NOT add any text outside the format."
    ),
)

docs_handler = Agent(
    name="docs_handler",
    model="openai/gpt-4o",
    instructions=(
        "You handle docs issues and questions. Read the issue CAREFULLY.\n\n"
        "You MUST output EXACTLY this format and NOTHING else — no greeting, "
        "no explanation, no sign-off, no extra text:\n\n"
        "Confusion: <what the user is stuck on>\n"
        "Doc gap: <which doc page is missing or unclear>\n"
        "Draft reply: <under 50 words — acknowledge the gap and say the "
        "team will update the docs>\n"
        "Labels: documentation\n\n"
        "Example output:\n"
        "Confusion: User doesn't know how to configure retry behavior.\n"
        "Doc gap: The tools page does not mention retry configuration.\n"
        "Draft reply: Good catch — the docs don't cover this yet. "
        "We'll add a section on retry configuration to the tools page.\n"
        "Labels: documentation\n\n"
        "RULES:\n"
        "- ONLY describe the gap. Do NOT answer the technical question.\n"
        "- NEVER write code examples — you don't have access to the "
        "source code and will get it wrong.\n"
        "- Keep Draft reply under 50 words. Just acknowledge and commit "
        "to updating the docs.\n"
        "- Do NOT add any text outside the format."
    ),
)

# ── Triage Agent (Handoff) ───────────────────────────────────────

triage = Agent(
    name="triage",
    model="openai/gpt-4o",
    agents=[bug_handler, feature_handler, docs_handler],
    strategy=Strategy.HANDOFF,
    instructions=(
        "You are an issue triage bot. Your ONLY job is to route.\n\n"
        "1. Read the issue.\n"
        "2. Hand off to exactly ONE agent:\n"
        "   - Error/crash/traceback/regression → bug_handler\n"
        "   - Feature request/suggestion → feature_handler\n"
        "   - Docs question/confusion → docs_handler\n"
        "3. After the specialist responds, output their response "
        "VERBATIM. Copy-paste it exactly. Add nothing.\n\n"
        "You are a router, not an analyst. Do NOT add your own words."
    ),
)


# ── Run ──────────────────────────────────────────────────────────

if __name__ == "__main__":
    with AgentRuntime() as runtime:
        result = runtime.run(
            triage,
            "File upload fails with a 500 error when the filename has spaces. "
            "Uploading 'report.pdf' works, but 'Q1 report.pdf' returns a server "
            "error. Looks like the filename isn't being URL-encoded.",
        )
        result.print_result()
