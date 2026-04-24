#!/usr/bin/env python3
# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""Issue Fixer Agent — autonomous GitHub issue to PR pipeline.

A multi-agent coding agent that takes a GitHub issue number, analyzes the
codebase, implements a fix with tests, and creates a pull request.

Architecture: Deterministic pipeline with sequential review stages

    issue_analyst >> tech_lead >> [impl_loop: (coder >> dg) <-> tl_review]
                  >> (qa_lead >> test_coder >> qa_reviewer) >> docs_agent >> pr_creator

Code review is SEQUENTIAL (coder >> dg_reviewer) — DG is GUARANTEED to run
after every coder execution. No handoff text needed.
The impl_loop SWARM wraps this with TL review for approval/rework cycles.
Testing is SEQUENTIAL: QA plans >> coder writes >> QA reviews + runs e2e.

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
DOCS_PLAN_DIR = "docs/plan"
DOCS_DESIGN_DIR = "docs/design"
QA_EVIDENCE_DIR = "qa-tests"           # QA testing evidence per issue

# ── Server ───────────────────────────────────────────────────
SERVER_URL = "http://localhost:6767"

# ── Timeouts & Limits ────────────────────────────────────────
SWARM_MAX_TURNS = 500
SWARM_TIMEOUT = 14400          # 4 hours
E2E_TOOL_TIMEOUT = 5400        # 90 min
MAX_REVIEW_CYCLES = 3
MAX_E2E_RETRIES = 3

from _issue_fixer_instructions import (
    ISSUE_ANALYST_INSTRUCTIONS,
    TECH_LEAD_INSTRUCTIONS,
    CODER_INSTRUCTIONS,
    DG_REVIEWER_INSTRUCTIONS,
    QA_LEAD_INSTRUCTIONS,
    TL_REVIEW_INSTRUCTIONS,
    DOCS_AGENT_INSTRUCTIONS,
    PR_CREATOR_INSTRUCTIONS,
    PR_FEEDBACK_INSTRUCTIONS,
    PR_UPDATER_INSTRUCTIONS,
)

# Format instruction templates with project constants
_fmt = {
    "repo": REPO,
    "branch_prefix": BRANCH_PREFIX,
    "max_review_cycles": MAX_REVIEW_CYCLES,
    "max_e2e_retries": MAX_E2E_RETRIES,
    "docs_plan_dir": DOCS_PLAN_DIR,
    "docs_design_dir": DOCS_DESIGN_DIR,
    "qa_evidence_dir": QA_EVIDENCE_DIR,
}


def _issue_analyzed(context: dict, **kwargs) -> bool:
    """Stop Issue Analyst when structured output is produced."""
    result = context.get("result", "")
    return all(tag in result for tag in ("REPO:", "BRANCH:", "ISSUE:", "MODULE:"))


def _pr_created(context: dict, **kwargs) -> bool:
    """Stop PR Creator when a PR URL is output."""
    result = context.get("result", "")
    return "github.com" in result and "/pull/" in result


# ═══════════════════════════════════════════════════════════════
# Stage 1: Issue Analyst (pipeline)
# ═══════════════════════════════════════════════════════════════

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

# ═══════════════════════════════════════════════════════════════
# Stage 2: Tech Lead — plan (pipeline)
# ═══════════════════════════════════════════════════════════════

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

# ═══════════════════════════════════════════════════════════════
# Stage 3: Implementation Loop
#   Inner: code_review_loop (coder <-> DG, until DG approves)
#   Outer: impl_loop (code_review <-> TL review, until TL approves)
# ═══════════════════════════════════════════════════════════════

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

# Sequential: coder runs THEN DG reviews — deterministic, no handoff text needed.
# A SWARM relied on the coder LLM to output handoff text, which it never did.
# Sequential guarantees DG runs after every coder execution.
code_then_review = coder >> dg_reviewer

# Tech Lead final review
tl_reviewer = Agent(
    name="tl_reviewer",
    model=OPUS,
    stateful=True,
    max_turns=30,
    max_tokens=60000,
    tools=[
        read_file, grep_search, glob_find, list_directory,
        file_outline, search_symbols, find_references,
        git_diff, git_log, run_command,
        contextbook_write, contextbook_read, contextbook_summary,
    ],
    instructions=TL_REVIEW_INSTRUCTIONS.format(**_fmt),
)

# Outer loop: (coder >> DG) <-> TL review until TL says IMPL_APPROVED
# Each iteration: coder implements (sequential), DG reviews (sequential),
# then TL does final review. If TL says NEEDS_REWORK, back to coder >> DG.
impl_loop = Agent(
    name="impl_loop",
    model=SONNET,
    stateful=True,
    strategy=Strategy.SWARM,
    agents=[code_then_review, tl_reviewer],
    handoffs=[
        OnTextMention(text="NEEDS_REWORK", target="coder_dg_reviewer"),
        OnTextMention(text="IMPL_APPROVED", target="tl_reviewer"),
    ],
    termination=TextMentionTermination("IMPL_APPROVED"),
    max_turns=MAX_REVIEW_CYCLES * 2 + 2,  # bounded: code_review + tl_review per cycle
    max_tokens=60000,
    timeout_seconds=SWARM_TIMEOUT,
    instructions="Start with code_review_loop. After code review, TL reviews. Loop until TL says IMPL_APPROVED.",
)

# ═══════════════════════════════════════════════════════════════
# Stage 4: Test Loop (coder <-> QA, until QA says TESTS_PASS)
# ═══════════════════════════════════════════════════════════════

# Separate coder instance for test writing (same config, different name)
test_coder = Agent(
    name="test_coder",
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

qa_lead = Agent(
    name="qa_lead",
    model=SONNET,
    stateful=True,
    max_turns=80,
    max_tokens=60000,
    tools=[
        read_file, write_file, grep_search, glob_find, list_directory,
        file_outline, git_diff, run_command, web_fetch,
        run_unit_tests, run_e2e_tests,
        contextbook_write, contextbook_read, contextbook_summary,
    ],
    instructions=QA_LEAD_INSTRUCTIONS.format(**_fmt),
)

# QA reviewer: runs e2e tests and captures evidence (separate instance for sequential pipeline)
qa_reviewer = Agent(
    name="qa_reviewer",
    model=SONNET,
    stateful=True,
    max_turns=80,
    max_tokens=60000,
    tools=[
        read_file, grep_search, glob_find, list_directory,
        file_outline, git_diff, run_command, web_fetch,
        write_file,
        run_unit_tests, run_e2e_tests,
        contextbook_write, contextbook_read, contextbook_summary,
    ],
    instructions=QA_LEAD_INSTRUCTIONS.format(**_fmt),
)

# Sequential: QA plans → coder writes tests → QA reviews + runs e2e
# All three steps are deterministic — no handoff text needed.
test_then_verify = qa_lead >> test_coder >> qa_reviewer

# ═══════════════════════════════════════════════════════════════
# Stage 5: Documentation Agent (pipeline)
# ═══════════════════════════════════════════════════════════════

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

# ═══════════════════════════════════════════════════════════════
# Stage 6: PR Creator (pipeline)
# ═══════════════════════════════════════════════════════════════

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

# ═══════════════════════════════════════════════════════════════
# Stage 7: PR Feedback Agent (feedback mode only)
#   Fetches PR comments/reviews, writes them to contextbook
# ═══════════════════════════════════════════════════════════════

pr_feedback = Agent(
    name="pr_feedback",
    model=SONNET,
    stateful=True,
    max_turns=20,
    max_tokens=16000,
    credentials=[GITHUB_CREDENTIAL],
    cli_config=CliConfig(
        allowed_commands=["gh", "git"],
        allow_shell=True,
        timeout=60,
    ),
    tools=[contextbook_write, contextbook_read, web_fetch],
    instructions=PR_FEEDBACK_INSTRUCTIONS.format(**_fmt),
)

# ═══════════════════════════════════════════════════════════════
# Stage 8: PR Updater (feedback mode only)
#   Pushes changes and updates the existing PR
# ═══════════════════════════════════════════════════════════════

pr_updater = Agent(
    name="pr_updater",
    model=SONNET,
    stateful=True,
    max_turns=10,
    max_tokens=8192,
    credentials=[GITHUB_CREDENTIAL],
    cli_config=CliConfig(
        allowed_commands=["gh", "git"],
        allow_shell=True,
        timeout=60,
    ),
    tools=[git_diff, git_log, contextbook_read, run_command],
    instructions=PR_UPDATER_INSTRUCTIONS.format(**_fmt),
)

# ═══════════════════════════════════════════════════════════════
# Pipelines
# ═══════════════════════════════════════════════════════════════

# New issue → full pipeline
pipeline = issue_analyst >> tech_lead >> impl_loop >> test_then_verify >> docs_agent >> pr_creator

# PR feedback → address comments, re-review, re-test, update PR
feedback_pipeline = pr_feedback >> impl_loop >> test_then_verify >> pr_updater


def main():
    import argparse

    parser = argparse.ArgumentParser(
        description="Issue Fixer Agent — autonomous GitHub issue to PR pipeline",
        epilog="Examples:\n"
               "  python 100_issue_fixer_agent.py 42           # Fix issue #42\n"
               "  python 100_issue_fixer_agent.py 42 --pr 157  # Address PR #157 feedback\n",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("issue_number", type=int, help="GitHub issue number to fix")
    parser.add_argument("--pr", type=int, default=None, help="Existing PR number to address feedback on")
    args = parser.parse_args()

    issue_number = args.issue_number
    pr_number = args.pr

    # Create a temp working directory with a random suffix.
    work_dir = os.path.join(tempfile.gettempdir(), f"agentspan-fix-{uuid.uuid4().hex[:12]}")
    set_working_dir(work_dir)
    print(f"Working directory: {work_dir}")

    if pr_number:
        # Feedback mode: address PR comments
        idempotency_key = f"issue-{issue_number}-pr-{pr_number}-feedback"
        active_pipeline = feedback_pipeline
        prompt = (
            f"Address feedback on PR #{pr_number} for issue #{issue_number} "
            f"in repo {REPO}. The repo will be cloned into: {work_dir}"
        )
        print(f"Mode: PR feedback (PR #{pr_number})")
    else:
        # New issue mode: full pipeline
        idempotency_key = f"issue-{issue_number}"
        active_pipeline = pipeline
        prompt = (
            f"Fix issue #{issue_number} from {REPO}. "
            f"The repo will be cloned into the working directory: {work_dir}"
        )
        print(f"Mode: New issue fix")

    with AgentRuntime() as rt:
        handle = rt.start(
            active_pipeline,
            prompt,
            idempotency_key=idempotency_key,
        )
        print(f"Execution started: {handle.execution_id}")
        print(f"Idempotency key: {idempotency_key}")
        print(f"Monitor at: {SERVER_URL}/execution/{handle.execution_id}")

        result = handle.join(timeout=SWARM_TIMEOUT)
        result.print_result()


if __name__ == "__main__":
    main()
