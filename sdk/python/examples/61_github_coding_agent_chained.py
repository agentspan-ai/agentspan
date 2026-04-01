#!/usr/bin/env python3
# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""GitHub Coding Agent — issue to PR pipeline.

Deploys and serves a three-stage pipeline:
  1. Fetch open issue, create branch (CLI tools: gh, git)
  2. Code fix + QA review (SWARM: coder <-> qa_tester)
  3. Create pull request (CLI tool: gh)

Run:
    python github_coding_agent.py          # Deploy + serve
    agentspan run github_pipeline "..."    # Trigger (from another terminal)

Requirements:
    - Agentspan server running
    - GITHUB_TOKEN stored: agentspan credentials set --name GITHUB_TOKEN
    - gh CLI installed
"""

from agentspan.agents import Agent, AgentRuntime, Strategy
from agentspan.agents.cli_config import CliConfig
from agentspan.agents.gate import TextGate
from agentspan.agents.handoff import OnTextMention

REPO = "agentspan-ai/codingexamples"
MODEL = "anthropic/claude-sonnet-4-6"

# ── Stage 1: Fetch issues ─────────────────────────────────────────

git_fetch_issues = Agent(
    name="git_fetch_issues",
    model=MODEL,
    max_tokens=8192,
    instructions=f"""\
You fetch ONE open issue from {REPO} and push an empty branch.

Step 1 — run this command:
  gh issue list --repo {REPO} --state open --limit 5
If no issues, respond: NO_OPEN_ISSUES

Step 2 — pick an issue, then run this ONE compound command (shell=true):
  TMPDIR=$(mktemp -d) && gh repo clone {REPO} "$TMPDIR" && cd "$TMPDIR" && git checkout -b fix/issue-<N> && git push -u origin fix/issue-<N> && echo "DONE"

Step 3 — respond with ONLY these 4 lines (NO tool calls):
  REPO: {REPO}
  BRANCH: fix/issue-<N>
  ISSUE: #<N> <title>
  SUMMARY: <one-sentence description>

RULES:
- Do NOT create files, commits, or pull requests.
- After step 2, you MUST stop using tools entirely. Just output text.
- You have at most 5 turns total.
""",
    cli_config=CliConfig(
        allowed_commands=["gh", "git", "mktemp"],
        allow_shell=True,
        timeout=60,
    ),
    credentials=["GITHUB_TOKEN", "GH_TOKEN"],
    max_turns=8,
    gate=TextGate("NO_OPEN_ISSUES"),
)

# ── Stage 2: Coding + QA (SWARM) ──────────────────────────────────

coder = Agent(
    name="coder",
    model=MODEL,
    max_tokens=60000,
    credentials=["GITHUB_TOKEN", "GH_TOKEN"],
    instructions="""\
You are a senior developer. Clone the repo, check out the branch,
implement the fix, commit, push. Then say HANDOFF_TO_QA with REPO/BRANCH/CHANGES.
""",
    local_code_execution=True,
)

qa_tester = Agent(
    name="qa_tester",
    model=MODEL,
    credentials=["GITHUB_TOKEN", "GH_TOKEN"],
    instructions="""\
You are a QA engineer. Clone the repo, review changes, run tests.
If bugs found: say HANDOFF_TO_CODER with what to fix.
If good: say QA_APPROVED with REPO/BRANCH/SUMMARY.
""",
    local_code_execution=True,
    max_tokens=60000,
    max_turns=5,
)

coding_qa = Agent(
    name="coding_qa",
    model=MODEL,
    instructions=(
        "Delegate to coder, then qa_tester. Loop until QA approves. "
        "Output REPO/BRANCH/SUMMARY when done."
    ),
    agents=[coder, qa_tester],
    strategy=Strategy.SWARM,
    handoffs=[
        OnTextMention(text="HANDOFF_TO_QA", target="qa_tester"),
        OnTextMention(text="HANDOFF_TO_CODER", target="coder"),
    ],
    max_turns=200,
    max_tokens=60000,
    timeout_seconds=6000,
)

# ── Stage 3: Create PR ────────────────────────────────────────────

git_push_pr = Agent(
    name="git_push_pr",
    model=MODEL,
    max_tokens=8192,
    max_turns=5,
    credentials=["GITHUB_TOKEN", "GH_TOKEN"],
    instructions="""\
Create a pull request. Run this ONE command (extract REPO, BRANCH, ISSUE from context):
  gh pr create --repo <REPO> --base main --head <BRANCH> --title "Fix <ISSUE>" --body "Fixes <ISSUE>"

After the command succeeds, STOP calling tools and respond with ONLY the PR URL.
""",
    cli_commands=True,
    cli_allowed_commands=["gh"],
)

# ── Pipeline ──────────────────────────────────────────────────────

pipeline = git_fetch_issues >> coding_qa >> git_push_pr

if __name__ == "__main__":
    with AgentRuntime() as rt:
        # Deploy: push definition to server (idempotent — safe to call every startup).
        # Can also be done via CLI: agentspan deploy examples.production.github_coding_agent
        # rt.deploy(pipeline)

        # Option A: Serve workers (production — blocks forever, run from outside)
        # rt.serve(pipeline)

        # Direct run for local development:
        # rt.run() handles deploy + workers internally, no serve needed.
        result = rt.run(pipeline, "Pick an open issue and create a PR.", timeout=240000)
        result.print_result()

        # Or trigger a deployed agent by name from any process:
        # result = rt.run("github_pipeline", "Pick an open issue and create a PR.")
        # result.print_result()
