#!/usr/bin/env python3
# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""GitHub Coding Agent — Claude Code variant.

Same issue-to-PR pipeline as 61, but replaces the SWARM coder/qa loop
with a single Claude Code agent that handles implementation, testing,
and self-review natively.

Architecture:
  pipeline = git_fetch_issues >> claude_code_fixer >> git_push_pr

  Stage 1: Fetch issue + create branch   (CLI tools: gh, git)
  Stage 2: Implement fix                 (Claude Code: Bash, Read, Write, Edit, Glob, Grep)
  Stage 3: Create pull request           (CLI tools: gh)

Compared to 61 (SWARM coder <-> qa_tester):
  - Simpler: one agent instead of a 3-agent swarm
  - Claude Code brings its own file editing, terminal, and code navigation
  - No need for local_code_execution — Claude Code has native tool support

Run:
    python 61a_github_coding_agent_claude_code.py

Requirements:
    - Agentspan server running
    - GITHUB_TOKEN stored: agentspan credentials set GITHUB_TOKEN <your-github-token>
    - gh CLI installed
    - Claude Code SDK installed (pip install claude-code-sdk)
"""

from agentspan.agents import Agent, AgentRuntime, ClaudeCode
from agentspan.agents.cli_config import CliConfig
from agentspan.agents.gate import TextGate

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
        allowed_commands=["gh", "git", "mktemp"],
        allow_shell=True,
        timeout=60,
    ),
    credentials=["GITHUB_TOKEN", "GH_TOKEN"],
    max_turns=20,
    stop_when=_fetch_done,
    gate=TextGate("NO_OPEN_ISSUES"),
)

# ── Stage 2: Claude Code fixer ────────────────────────────────────

claude_code_fixer = Agent(
    name="claude_code_fixer",
    model=ClaudeCode("sonnet", permission_mode=ClaudeCode.PermissionMode.ACCEPT_EDITS),
    credentials=["GITHUB_TOKEN", "GH_TOKEN"],
    instructions=f"""\
You are a senior developer fixing a GitHub issue.

Your input contains structured output from the previous stage:
  REPO, BRANCH, ISSUE, AUTHOR, DETAILS, SUMMARY

Workflow:
1. Clone the repo and check out the branch:
   git clone https://github.com/<REPO>.git /tmp/work
   cd /tmp/work
   git checkout <BRANCH>

2. Read the DETAILS field carefully — it contains the full issue requirements.

3. Explore the codebase to understand the project structure, conventions,
   and test patterns before making changes.

4. Implement the fix:
   - Make the SMALLEST correct change that fully resolves the issue.
   - Match existing code style exactly.
   - Add or update tests if the project has test infrastructure.

5. Validate:
   - Run the project's test suite if one exists.
   - Run the linter if one exists.

6. Commit and push:
   git add <specific files>
   git commit -m "fix: <concise description>"
   git push origin <BRANCH>

7. Output EXACTLY these lines when done:
   REPO: <repo>
   BRANCH: <branch>
   ISSUE: <issue>
   CHANGES: <summary of what was changed and why>

RULES:
- Fix root cause, not symptoms.
- No "while I'm here" changes — every line must be justified by the issue.
- Do NOT create a pull request — the next stage handles that.
""",
    tools=["Bash", "Read", "Write", "Edit", "Glob", "Grep"],
    max_turns=50,
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

pipeline = git_fetch_issues >> claude_code_fixer >> git_push_pr

if __name__ == "__main__":
    with AgentRuntime() as rt:
        result = rt.run(pipeline, "Pick an open issue and create a PR.", timeout=600000)
        result.print_result()

        # Production pattern:
        # 1. Deploy once during CI/CD:
        # rt.deploy(pipeline)
        # CLI alternative:
        # agentspan deploy --package examples.61a_github_coding_agent_claude_code
        #
        # 2. In a separate long-lived worker process:
        # rt.serve(pipeline)
