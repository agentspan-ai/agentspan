#!/usr/bin/env python3
# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""Deep Research Agent — multi-agent competitive intelligence pipeline.

Takes a research brief (competitors, industry topics, data points to collect)
and produces a verified, source-cited research report or CSV.

Architecture:
    planner >> scatter_gather(researcher) >> reviewer >> synthesizer

    - Planner: discovers and validates sources, creates research plan
    - Researchers: parallel deep search with cross-referencing (N instances)
    - Reviewer: validates findings, dispatches follow-ups for gaps
    - Synthesizer: formats verified data into report or CSV

The planner iterates on source validation before dispatching researchers.
Each researcher iterates internally: search → extract → cross-reference → fill gaps.
The reviewer can dispatch additional researchers for missing data.

API Keys Required:
    PERPLEXITY_API_KEY  — Perplexity Sonar Pro (deep web search)
    TAVILY_API_KEY      — Tavily (URL/page discovery)

Google Docs Setup:
    For end users (one-time):
        python 102_deep_research_agent.py --google-auth
        → Opens browser → sign in with Google → done
        → Docs are created in the user's own Google Drive

    The deployer/admin sets GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET
    env vars (from Google Cloud Console OAuth client, type: Desktop).
    End users never need Google Cloud access.

    For developers:
        Use --google-client-secret client_secret.json, or
        gcloud auth application-default login --scopes=...

    For automation (service account):
        export GOOGLE_APPLICATION_CREDENTIALS=/path/to/service-account.json

    Python deps:
        pip install google-auth google-auth-oauthlib google-api-python-client

Usage:
    python 102_deep_research_agent.py --google-auth              # one-time OAuth setup
    python 102_deep_research_agent.py                            # run with sample brief
    python 102_deep_research_agent.py --brief "Research X, Y..."
    python 102_deep_research_agent.py --config research_brief.txt

Requirements:
    - Agentspan server running
    - AGENTSPAN_SERVER_URL=http://localhost:6767/api in .env or environment
"""

import os
import tempfile
import uuid

from _deep_research_instructions import (
    COORDINATOR_INSTRUCTIONS,
    PLANNER_INSTRUCTIONS,
    RESEARCHER_INSTRUCTIONS,
    REVIEWER_INSTRUCTIONS,
    SYNTHESIZER_INSTRUCTIONS,
)
from _deep_research_tools import (
    contextbook_read,
    contextbook_write,
    create_google_doc,
    google_oauth_setup,
    scrape_page,
    set_working_dir,
    sonar_search,
    web_search,
)

from agentspan.agents import Agent, AgentRuntime, agent_tool, scatter_gather
from settings import settings

# ── Configuration ────────────────────────────────────────────
SONNET = "anthropic/claude-sonnet-4-20250514"
OPUS = "anthropic/claude-opus-4-6"
SERVER_URL = os.environ.get("AGENTSPAN_SERVER_URL", "http://localhost:6767/api")


# ── Stop conditions ──────────────────────────────────────────


def _has_contextbook_marker(messages: list, marker: str) -> bool:
    """Check if a contextbook write marker appears in message history."""
    for msg in messages:
        if not isinstance(msg, dict):
            continue
        content = msg.get("content", "")
        if isinstance(content, str) and marker in content:
            return True
        if isinstance(content, list):
            for part in content:
                if isinstance(part, dict) and marker in str(part.get("text", "")):
                    return True
    return False


def _planner_done(context: dict, **kwargs) -> bool:
    """Stop planner when research_plan is written to contextbook."""
    result = context.get("result", "")
    marker = "wrote 'research_plan'"
    if marker in result:
        return True
    return _has_contextbook_marker(context.get("messages", []), marker)


def _reviewer_done(context: dict, **kwargs) -> bool:
    """Stop reviewer when verified_findings is written to contextbook."""
    result = context.get("result", "")
    marker = "wrote 'verified_findings'"
    if marker in result:
        return True
    return _has_contextbook_marker(context.get("messages", []), marker)


# ══════════════════════════════════════════════════════════════
# Agents
# ══════════════════════════════════════════════════════════════

# ── Planner: discovers sources, validates them, creates research plan ──

planner = Agent(
    name="research_planner",
    model=SONNET,
    tools=[sonar_search, contextbook_write],
    max_turns=10,
    max_tokens=16000,
    stop_when=_planner_done,
    instructions=PLANNER_INSTRUCTIONS,
)

# ── Researcher: deep iterative search on one focused task ──

researcher = Agent(
    name="deep_researcher",
    model=SONNET,
    tools=[sonar_search, web_search, scrape_page],
    max_turns=20,
    max_tokens=32000,
    instructions=RESEARCHER_INSTRUCTIONS,
)

# ── Research Coordinator: dispatches parallel researchers ──

coordinator = scatter_gather(
    name="research_coordinator",
    worker=researcher,
    model=SONNET,
    instructions=COORDINATOR_INSTRUCTIONS,
    retry_count=2,
    retry_delay_seconds=5,
    timeout_seconds=300,
)

# ── Reviewer: validates findings, dispatches follow-up research ──

reviewer = Agent(
    name="research_reviewer",
    model=OPUS,  # Use Opus for better reasoning on cross-referencing
    tools=[sonar_search, agent_tool(researcher), contextbook_write, contextbook_read],
    max_turns=15,
    max_tokens=60000,
    stop_when=_reviewer_done,
    instructions=REVIEWER_INSTRUCTIONS,
)

# ── Synthesizer: formats final output, creates Google Doc ──
# Credentials are resolved by _get_google_creds() inside the tool.
# List both so the credential system makes either available if set.

synthesizer = Agent(
    name="report_synthesizer",
    model=SONNET,
    tools=[contextbook_read, create_google_doc],
    max_turns=5,
    max_tokens=16000,
    instructions=SYNTHESIZER_INSTRUCTIONS,
)

# ══════════════════════════════════════════════════════════════
# Pipeline
# ══════════════════════════════════════════════════════════════

pipeline = planner >> coordinator >> reviewer >> synthesizer


# ── Sample research briefs ───────────────────────────────────

SAMPLE_BRIEF = """\
I run a residential landscaping business in Austin, TX. Research the following:

COMPETITORS:
- ABC Home & Commercial Services (abchomeandcommercial.com)
- TruGreen (trugreen.com)
- LawnStarter (lawnstarter.com)

For each competitor, find:
- Current pricing for basic residential lawn care (mowing, edging, trimming)
- Service tiers / packages offered
- Customer ratings (Google, Yelp, BBB)
- Any recent news, expansions, or changes (last 6 months)

INDUSTRY:
- Average residential lawn care pricing in Austin, TX metro area
- Industry trends for landscaping businesses in 2025-2026
- Any new regulations affecting landscaping in Texas

OUTPUT: A comparison table (CSV format) plus a brief analysis report.
"""


def main():
    import argparse

    parser = argparse.ArgumentParser(
        description="Deep Research Agent — multi-agent competitive intelligence",
        epilog="Examples:\n"
        "  python 102_deep_research_agent.py\n"
        '  python 102_deep_research_agent.py --brief "Research X, Y, Z..."\n'
        "  python 102_deep_research_agent.py --config research_brief.txt\n",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--brief",
        type=str,
        default=None,
        help="Research brief text (inline)",
    )
    parser.add_argument(
        "--config",
        type=str,
        default=None,
        help="Path to a text file containing the research brief",
    )
    parser.add_argument(
        "--google-auth",
        action="store_true",
        help="Run one-time Google OAuth setup (opens browser for login)",
    )
    parser.add_argument(
        "--google-client-secret",
        type=str,
        default="",
        help="Path to OAuth client_secret.json (for --google-auth)",
    )
    args = parser.parse_args()

    # Google OAuth setup (interactive, then exit)
    if args.google_auth:
        google_oauth_setup(client_secrets=args.google_client_secret)
        return

    # Determine research brief
    if args.config:
        with open(args.config) as f:
            brief = f.read().strip()
    elif args.brief:
        brief = args.brief
    else:
        brief = SAMPLE_BRIEF
        print("No --brief or --config provided, using sample landscaping brief.\n")

    # Working directory for contextbook
    work_dir = os.path.join(tempfile.gettempdir(), f"deep-research-{uuid.uuid4().hex[:8]}")
    set_working_dir(work_dir)

    print("=" * 70)
    print("  Deep Research Agent")
    print("  Pipeline: planner >> scatter(researcher) >> reviewer >> synthesizer")
    print("=" * 70)
    print(f"\nWorking directory: {work_dir}")
    print(f"Brief: {brief[:200]}{'...' if len(brief) > 200 else ''}\n")

    with AgentRuntime() as rt:
        handle = rt.start(pipeline, brief)
        print(f"Execution started: {handle.execution_id}")
        print(f"Monitor at: {SERVER_URL.rstrip('/api')}/execution/{handle.execution_id}")

        result = handle.join(timeout=1800)  # 30 min max
        print("\n" + "=" * 70)
        print("  RESEARCH COMPLETE")
        print("=" * 70)
        result.print_result()

        # Also print contextbook contents for reference
        print("\n--- Contextbook: research_plan ---")
        plan_path = os.path.join(work_dir, ".contextbook", "research_plan.md")
        if os.path.exists(plan_path):
            with open(plan_path) as f:
                print(f.read()[:2000])

        print("\n--- Contextbook: verified_findings ---")
        findings_path = os.path.join(work_dir, ".contextbook", "verified_findings.md")
        if os.path.exists(findings_path):
            with open(findings_path) as f:
                print(f.read()[:3000])


if __name__ == "__main__":
    main()
