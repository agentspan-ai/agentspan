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
    - GITHUB_TOKEN stored: agentspan credentials set GITHUB_TOKEN <your-github-token>
    - gh CLI installed
"""

from agentspan.agents import Agent, AgentRuntime, Strategy
from agentspan.agents.cli_config import CliConfig
from agentspan.agents.gate import TextGate
from agentspan.agents.handoff import OnTextMention

REPO = "agentspan-ai/codingexamples"
MODEL = "anthropic/claude-sonnet-4-6"


# ── Stage 1: Fetch issues ─────────────────────────────────────────

def _fetch_done(context: dict, **kwargs) -> bool:
    """Stop when the agent has produced the structured output with issue details."""
    result = context.get("result", "")
    return all(tag in result for tag in ("REPO:", "BRANCH:", "ISSUE:", "AUTHOR:", "DETAILS:"))


git_fetch_issues = Agent(
    name="git_fetch_issues",
    model=MODEL,
    max_tokens=8192,
    instructions=f"""\
You fetch ONE open issue from {REPO} and push an empty branch.

Step 1 — list open issues:
  gh issue list --repo {REPO} --state open --limit 5
If no issues, respond: NO_OPEN_ISSUES

Step 2 — pick an issue and fetch its FULL details (body, author, labels):
  gh issue view <N> --repo {REPO} --json number,title,body,author,labels

You MUST run this command — gh issue list only returns titles, not the issue body.
Read the JSON output carefully and extract the author login and the COMPLETE body text.

Step 3 — create a branch and push it (one compound command, shell=true):
  TMPDIR=$(mktemp -d) && gh repo clone {REPO} "$TMPDIR" && cd "$TMPDIR" && git checkout -b fix/issue-<N> && git push -u origin fix/issue-<N> && echo "DONE"

Step 4 — respond with ONLY these lines (NO tool calls):
  REPO: {REPO}
  BRANCH: fix/issue-<N>
  ISSUE: #<N> <title>
  AUTHOR: <who opened the issue>
  DETAILS: <full issue body — preserve all requirements, acceptance criteria, and context>
  SUMMARY: <one-sentence description>

RULES:
- Do NOT create files, commits, or pull requests.
- After step 3, you MUST stop using tools entirely. Just output text.
- Include the COMPLETE issue body in DETAILS — the next stage needs it to implement the fix.
""",
    cli_config=CliConfig(
        allowed_commands=["gh", "git", "mktemp", "ls"],
        allow_shell=True,
        timeout=60,
    ),
    credentials=["GITHUB_TOKEN", "GH_TOKEN"],
    max_turns=20,
    stop_when=_fetch_done,
    gate=TextGate("NO_OPEN_ISSUES"),
)

# ── Stage 2: Coding + QA (SWARM) ──────────────────────────────────

coder = Agent(
    name="coder",
    model=MODEL,
    max_tokens=60000,
    credentials=["GITHUB_TOKEN", "GH_TOKEN"],
    instructions="""\
You are a senior developer. Your input contains issue details from the previous stage
including REPO, BRANCH, ISSUE, AUTHOR, DETAILS, and SUMMARY.

1. Read the DETAILS field carefully — it contains the full issue body with requirements.
2. Clone the repo: gh repo clone <REPO> /tmp/work && cd /tmp/work
3. Check out the branch: git checkout <BRANCH>
4. Implement the fix according to ALL requirements in DETAILS.
5. Commit and push your changes.
6. Say HANDOFF_TO_QA with REPO, BRANCH, and a summary of CHANGES.
""",
    cli_config=CliConfig(
        allowed_commands=["gh", "git", "mktemp", "rm", "ls", "cat", "mkdir", "cp"],
        allow_shell=True,
        timeout=120,
    ),
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
    cli_config=CliConfig(
        allowed_commands=["gh", "git", "mktemp", "rm", "ls", "cat"],
        allow_shell=True,
        timeout=120,
    ),
    max_tokens=60000,
    max_turns=15,
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

def _pr_done(context: dict, **kwargs) -> bool:
    """Stop when the agent has output a PR URL."""
    result = context.get("result", "")
    return "github.com" in result and "/pull/" in result


git_push_pr = Agent(
    name="git_push_pr",
    model=MODEL,
    max_tokens=8192,
    max_turns=15,
    credentials=["GITHUB_TOKEN", "GH_TOKEN"],
    instructions="""\
Create a pull request. Extract REPO, BRANCH, and ISSUE from the previous stage output.

Run this command (shell=true so quotes are handled correctly):
  gh pr create --repo <REPO> --base main --head <BRANCH> --title "Fix <ISSUE>" --body "Fixes <ISSUE>"

After the command succeeds, STOP calling tools and respond with ONLY the PR URL.
""",
    cli_config=CliConfig(
        allowed_commands=["gh", "git"],
        allow_shell=True,
        timeout=60,
    ),
    stop_when=_pr_done,
)

# ── Pipeline ──────────────────────────────────────────────────────

pipeline = git_fetch_issues >> coding_qa >> git_push_pr

if __name__ == "__main__":
    with AgentRuntime() as rt:
        result = rt.run(pipeline, "Pick an open issue and create a PR.", timeout=240000)
        result.print_result()

        # Production pattern:
        # 1. Deploy once during CI/CD:
        # rt.deploy(pipeline)
        # CLI alternative:
        # agentspan deploy --package examples.61_github_coding_agent_chained
        #
        # 2. In a separate long-lived worker process:
        # rt.serve(pipeline)
