#!/usr/bin/env python3
# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""Issue Fixer Agent — autonomous GitHub issue to PR pipeline.

A multi-agent coding agent that takes a GitHub issue number, analyzes the
codebase, implements a fix with tests, and creates a pull request.

Architecture: Pipeline-wrapped swarm
    Issue Analyst >> [SWARM: Tech Lead <-> Coder <-> DG <-> QA Lead] >> PR Creator

Usage:
    python 100_issue_fixer_agent.py <issue_number>
    python 100_issue_fixer_agent.py 42

Requirements:
    - Agentspan server running
    - GITHUB_TOKEN: agentspan credentials set GITHUB_TOKEN <your-token>
    - gh CLI installed and authenticated
    - DG skill: git clone https://github.com/v1r3n/dinesh-gilfoyle ~/.claude/skills/dg
    - Full build toolchain (Go, Java 21, Python 3.10+, Node.js, pnpm, uv)
"""

import os
import sys
import tempfile
import uuid

from agentspan.agents import Agent, AgentRuntime, Strategy, skill, agent_tool
from agentspan.agents.cli_config import CliConfig
from agentspan.agents.handoff import OnTextMention
from agentspan.agents.termination import TextMentionTermination

from _issue_fixer_tools import (
    set_working_dir, get_working_dir,
    read_file, write_file, edit_file, apply_patch, list_directory, file_outline,
    glob_find, grep_search, search_symbols, find_references,
    git_diff, git_log, git_blame,
    lint_and_format, build_check, run_unit_tests, run_e2e_tests,
    contextbook_write, contextbook_read, contextbook_summary,
    run_command, web_fetch,
)

# ── Project-Specific Configuration ────────────────────────────
REPO = "agentspan-ai/agentspan"
REPO_URL = f"https://github.com/{REPO}"
BRANCH_PREFIX = "fix/issue-"

# ── Models ────────────────────────────────────────────────────
OPUS = "anthropic/claude-opus-4-6"
SONNET = "anthropic/claude-sonnet-4-6"

# ── Credentials ──────────────────────────────────────────────
GITHUB_CREDENTIAL = "GITHUB_TOKEN"

# ── Skill Paths ──────────────────────────────────────────────
DG_SKILL_PATH = "~/.claude/skills/dg"

# ── Documentation Paths ──────────────────────────────────────
DOCS_PLAN_DIR = "docs/plan"               # Where the Tech Lead writes the implementation plan
DOCS_DESIGN_DIR = "docs/design"           # Where design docs go

# ── Server ───────────────────────────────────────────────────
SERVER_URL = "http://localhost:6767"

# ── Timeouts & Limits ────────────────────────────────────────
SWARM_MAX_TURNS = 500
SWARM_TIMEOUT = 14400          # 4 hours
E2E_TOOL_TIMEOUT = 5400        # 90 min — full e2e suite with margin
MAX_REVIEW_CYCLES = 3
MAX_E2E_RETRIES = 3

from _issue_fixer_instructions import (
    ISSUE_ANALYST_INSTRUCTIONS,
    TECH_LEAD_INSTRUCTIONS,
    CODER_INSTRUCTIONS,
    DG_REVIEWER_INSTRUCTIONS,
    QA_LEAD_INSTRUCTIONS,
    DOCS_AGENT_INSTRUCTIONS,
    PR_CREATOR_INSTRUCTIONS,
)

# Format instruction templates with project constants
_fmt = {
    "repo": REPO,
    "branch_prefix": BRANCH_PREFIX,
    "max_review_cycles": MAX_REVIEW_CYCLES,
    "max_e2e_retries": MAX_E2E_RETRIES,
    "docs_plan_dir": DOCS_PLAN_DIR,
    "docs_design_dir": DOCS_DESIGN_DIR,
}


def _issue_analyzed(context: dict, **kwargs) -> bool:
    """Stop Issue Analyst when structured output is produced."""
    result = context.get("result", "")
    return all(tag in result for tag in ("REPO:", "BRANCH:", "ISSUE:", "MODULE:"))


def _pr_created(context: dict, **kwargs) -> bool:
    """Stop PR Creator when a PR URL is output."""
    result = context.get("result", "")
    return "github.com" in result and "/pull/" in result


# ── Stage 1: Issue Analyst ────────────────────────────────────

issue_analyst = Agent(
    name="issue_analyst",
    model=SONNET,
    stateful=True,
    max_turns=20,
    max_tokens=8192,
    credentials=[GITHUB_CREDENTIAL],
    cli_config=CliConfig(
        allowed_commands=["gh", "git", "mktemp", "ls", "find"],
        allow_shell=True,
        timeout=60,
    ),
    tools=[contextbook_write, contextbook_read],
    stop_when=_issue_analyzed,
    instructions=ISSUE_ANALYST_INSTRUCTIONS.format(**_fmt),
)

# ── Stage 2: Swarm agents ────────────────────────────────────

tech_lead = Agent(
    name="tech_lead",
    model=OPUS,
    stateful=True,
    max_turns=80,
    max_tokens=60000,
    tools=[
        read_file, grep_search, glob_find, list_directory,
        file_outline, search_symbols, find_references,
        git_log, git_blame, run_command, web_fetch,
        contextbook_write, contextbook_read, contextbook_summary,
    ],
    instructions=TECH_LEAD_INSTRUCTIONS.format(**_fmt),
)

coder = Agent(
    name="coder",
    model=SONNET,
    stateful=True,
    max_turns=200,
    max_tokens=60000,
    credentials=[GITHUB_CREDENTIAL],
    cli_config=CliConfig(
        allowed_commands=["git"],
        allow_shell=True,
        timeout=120,
    ),
    tools=[
        read_file, write_file, edit_file, apply_patch,
        grep_search, glob_find, list_directory,
        file_outline, search_symbols, find_references,
        git_diff, git_log, run_command, web_fetch,
        lint_and_format, build_check, run_unit_tests,
        contextbook_write, contextbook_read, contextbook_summary,
    ],
    instructions=CODER_INSTRUCTIONS.format(**_fmt),
)

# DG skill + coordinator wrapper
dg_skill = skill(
    DG_SKILL_PATH,
    model=SONNET,
    agent_models={"gilfoyle": OPUS, "dinesh": SONNET},
)

dg_reviewer = Agent(
    name="dg_reviewer",
    model=SONNET,
    stateful=True,
    max_turns=15,
    max_tokens=60000,
    tools=[
        agent_tool(dg_skill, description="Run adversarial Dinesh vs Gilfoyle code review"),
        read_file, grep_search, git_diff, file_outline,
        contextbook_write, contextbook_read, contextbook_summary,
    ],
    instructions=DG_REVIEWER_INSTRUCTIONS.format(**_fmt),
)

qa_lead = Agent(
    name="qa_lead",
    model=SONNET,
    stateful=True,
    max_turns=80,
    max_tokens=60000,
    tools=[
        read_file, grep_search, glob_find, list_directory,
        file_outline, git_diff, run_command,
        run_unit_tests, run_e2e_tests,
        contextbook_write, contextbook_read, contextbook_summary,
    ],
    instructions=QA_LEAD_INSTRUCTIONS.format(**_fmt),
)

# ── Swarm assembly ────────────────────────────────────────────

coding_swarm = Agent(
    name="coding_swarm",
    model=SONNET,
    stateful=True,
    strategy=Strategy.SWARM,
    agents=[tech_lead, coder, dg_reviewer, qa_lead],
    handoffs=[
        OnTextMention(text="HANDOFF_TO_CODER", target="coder"),
        OnTextMention(text="HANDOFF_TO_DG", target="dg_reviewer"),
        OnTextMention(text="HANDOFF_TO_QA", target="qa_lead"),
        OnTextMention(text="HANDOFF_TO_TECH_LEAD", target="tech_lead"),
    ],
    termination=TextMentionTermination("SWARM_COMPLETE"),
    max_turns=SWARM_MAX_TURNS,
    max_tokens=60000,
    timeout_seconds=SWARM_TIMEOUT,
    instructions="Start with tech_lead. Iterate until QA Lead confirms ALL_TESTS_PASS.",
)

# ── Stage 3: Documentation Agent ─────────────────────────────

docs_agent = Agent(
    name="docs_agent",
    model=SONNET,
    stateful=True,
    max_turns=40,
    max_tokens=60000,
    tools=[
        read_file, write_file, edit_file,
        grep_search, glob_find, list_directory,
        file_outline, git_diff, run_command, web_fetch,
        contextbook_read, contextbook_summary,
    ],
    instructions=DOCS_AGENT_INSTRUCTIONS.format(**_fmt),
)

# ── Stage 4: PR Creator ──────────────────────────────────────

pr_creator = Agent(
    name="pr_creator",
    model=SONNET,
    stateful=True,
    max_turns=10,
    max_tokens=8192,
    credentials=[GITHUB_CREDENTIAL],
    cli_config=CliConfig(
        allowed_commands=["gh", "git", "find"],
        allow_shell=True,
        timeout=60,
    ),
    tools=[git_diff, git_log, contextbook_read],
    stop_when=_pr_created,
    instructions=PR_CREATOR_INSTRUCTIONS.format(**_fmt),
)

# ── Full pipeline ─────────────────────────────────────────────

pipeline = issue_analyst >> coding_swarm >> docs_agent >> pr_creator


def main():
    if len(sys.argv) < 2:
        print("Usage: python 100_issue_fixer_agent.py <issue_number>")
        sys.exit(1)

    issue_number = int(sys.argv[1])
    idempotency_key = f"issue-{issue_number}"

    # Create a temp working directory with a random suffix.
    # The Issue Analyst will clone the repo INTO this directory.
    # All tools (read_file, edit_file, run_command, etc.) operate relative to it.
    work_dir = os.path.join(tempfile.gettempdir(), f"agentspan-fix-{uuid.uuid4().hex[:12]}")
    set_working_dir(work_dir)
    print(f"Working directory: {work_dir}")

    with AgentRuntime() as rt:
        handle = rt.start(
            pipeline,
            f"Fix issue #{issue_number} from {REPO}. "
            f"The repo will be cloned into the working directory: {work_dir}",
            idempotency_key=idempotency_key,
        )
        print(f"Execution started: {handle.execution_id}")
        print(f"Idempotency key: {idempotency_key}")
        print(f"Monitor at: {SERVER_URL}/execution/{handle.execution_id}")

        # join() blocks until the pipeline completes (or times out).
        # Workers were already registered by start() under the execution's
        # domain — calling serve() here would re-register them in the
        # default domain, causing stateful tool tasks to stay SCHEDULED.
        result = handle.join(timeout=SWARM_TIMEOUT)
        result.print_result()


if __name__ == "__main__":
    main()
