#!/usr/bin/env python3
# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""Issue Fixer Agent — autonomous GitHub issue to PR pipeline.

A multi-agent coding agent that takes a GitHub issue number, analyzes the
codebase, implements a fix with tests, and creates a pull request.

Architecture: Deterministic sequential pipeline — no SWARM loops

    issue_analyst >> tech_lead >> coder >> qa_agent
                  >> dg_reviewer >> fix_coder >> fix_qa >> pr_creator

Single QA agent writes tests + runs them (~6-8 turns).
DG runs ONCE after implementation + QA is complete.
If DG finds critical issues, fix_coder addresses them and fix_qa verifies.
If CODE_APPROVED, fix_coder and fix_qa pass through in 1 turn each.

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
import tempfile
import uuid

from agentspan.agents import Agent, AgentRuntime, skill, agent_tool
from agentspan.agents.cli_config import CliConfig

from _issue_fixer_tools import (
    set_working_dir, get_working_dir,
    read_file, write_file, edit_file, list_directory, file_outline,
    glob_find, grep_search, search_symbols, find_references,
    git_diff, git_log, git_blame,
    lint_and_format, build_check, run_unit_tests, run_e2e_tests,
    contextbook_write, contextbook_read,
    run_command, web_fetch, fetch_pr_context, gather_review_context,
    get_coder_context, read_files, edit_files,
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
E2E_TOOL_TIMEOUT = 5400        # 90 min
MAX_E2E_RETRIES = 3

from _issue_fixer_instructions import (
    ISSUE_ANALYST_INSTRUCTIONS,
    TECH_LEAD_INSTRUCTIONS,
    CODER_INSTRUCTIONS,
    DG_REVIEWER_INSTRUCTIONS,
    FIX_CODER_INSTRUCTIONS,
    FIX_QA_INSTRUCTIONS,
    QA_AGENT_INSTRUCTIONS,
    PR_CREATOR_INSTRUCTIONS,
    PR_FEEDBACK_INSTRUCTIONS,
    PR_UPDATER_INSTRUCTIONS,
)

# Format instruction templates with project constants
_fmt = {
    "repo": REPO,
    "branch_prefix": BRANCH_PREFIX,
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


def _feedback_collected(context: dict, **kwargs) -> bool:
    """Stop PR Feedback when TODO list is output."""
    result = context.get("result", "")
    return "## TODO" in result


def _review_decided(context: dict, **kwargs) -> bool:
    """Stop DG Reviewer when a verdict is output."""
    result = context.get("result", "")
    return "CODE_APPROVED" in result or "NEEDS_REWORK" in result


def _tech_lead_done(context: dict, **kwargs) -> bool:
    """Stop Tech Lead when handoff text is output or implementation_plan was written."""
    result = context.get("result", "")
    if "HANDOFF_TO_CODER" in result:
        return True
    for msg in context.get("messages", []):
        if not isinstance(msg, dict):
            continue
        content = msg.get("content", "")
        if isinstance(content, str) and "wrote 'implementation_plan'" in content:
            return True
        if isinstance(content, list):
            for part in content:
                if isinstance(part, dict) and "wrote 'implementation_plan'" in str(part.get("text", "")):
                    return True
    return False


def _coder_done(context: dict, **kwargs) -> bool:
    """Stop coder when handoff text is output or change_context was written.

    The coder's final meaningful action is writing change_context to contextbook.
    After that it should output HANDOFF, but LLMs sometimes loop on contextbook_read
    instead. Detecting change_context in tool results catches both cases.
    """
    result = context.get("result", "")
    if "HANDOFF_TO_DG" in result or "HANDOFF_TO_QA" in result:
        return True
    # Detect post-commit state: change_context was written → coder is done
    for msg in context.get("messages", []):
        if not isinstance(msg, dict):
            continue
        content = msg.get("content", "")
        # Tool result messages are strings; assistant tool_use are lists
        if isinstance(content, str) and "wrote 'change_context'" in content:
            return True
        if isinstance(content, list):
            for part in content:
                if isinstance(part, dict) and "wrote 'change_context'" in str(part.get("text", "")):
                    return True
    return False


def _qa_done(context: dict, **kwargs) -> bool:
    """Stop QA agent when verdict is output or test_results was written."""
    result = context.get("result", "")
    if "TESTS_PASS" in result or "TESTS_FAIL" in result:
        return True
    # Detect post-commit state: test_results was written → QA is done
    for msg in context.get("messages", []):
        if not isinstance(msg, dict):
            continue
        content = msg.get("content", "")
        if isinstance(content, str) and "wrote 'test_results'" in content:
            return True
        if isinstance(content, list):
            for part in content:
                if isinstance(part, dict) and "wrote 'test_results'" in str(part.get("text", "")):
                    return True
    return False


def _fix_done(context: dict, **kwargs) -> bool:
    """Stop fix_coder when it outputs a verdict or finishes rework."""
    result = context.get("result", "")
    if "NO_REWORK_NEEDED" in result or "REWORK_COMPLETE" in result:
        return True
    return _coder_done(context, **kwargs)


def _fix_qa_done(context: dict, **kwargs) -> bool:
    """Stop fix_qa when it outputs a verdict."""
    result = context.get("result", "")
    return "NO_REWORK_NEEDED" in result or "TESTS_PASS" in result or "TESTS_FAIL" in result


# ═══════════════════════════════════════════════════════════════
# Stage 1: Issue Analyst (pipeline)
# ═══════════════════════════════════════════════════════════════

issue_analyst = Agent(
    name="issue_analyst",
    model=SONNET,
    stateful=True,
    max_turns=8,
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
    max_turns=40,
    max_tokens=60000,
    tools=[
        read_file, grep_search, glob_find, list_directory,
        file_outline, search_symbols, find_references,
        git_log, git_blame, run_command, web_fetch,
        contextbook_write, contextbook_read,
    ],
    stop_when=_tech_lead_done,
    instructions=TECH_LEAD_INSTRUCTIONS.format(**_fmt),
)

# ═══════════════════════════════════════════════════════════════
# Stage 3: Coder (implements the fix)
# ═══════════════════════════════════════════════════════════════

coder = Agent(
    name="coder",
    model=SONNET,
    stateful=True,
    max_turns=20,
    max_tokens=60000,
    credentials=[GITHUB_CREDENTIAL],
    cli_config=CliConfig(
        allowed_commands=["git"],
        allow_shell=True,
        timeout=120,
    ),
    tools=[
        read_file, write_file, edit_file,
        read_files, edit_files,
        grep_search, glob_find, list_directory,
        file_outline, git_diff, git_log, run_command,
        lint_and_format, build_check, run_unit_tests,
        contextbook_write, contextbook_read, get_coder_context,
    ],
    stop_when=_coder_done,
    instructions=CODER_INSTRUCTIONS.format(**_fmt),
)

# ═══════════════════════════════════════════════════════════════
# Stage 3b: DG Skill (loaded here, used in Stage 5)
# ═══════════════════════════════════════════════════════════════

dg_skill = skill(
    DG_SKILL_PATH,
    model=SONNET,
    agent_models={"gilfoyle": OPUS, "dinesh": SONNET},
    params={"cap": 1},
)

dg_reviewer = Agent(
    name="dg_reviewer",
    model=SONNET,
    stateful=True,
    max_turns=2,
    max_tokens=60000,
    tools=[
        gather_review_context,
        agent_tool(dg_skill, description="Run Dinesh vs Gilfoyle code review. Pass '1' as the request to limit to 1 round."),
        contextbook_write,
    ],
    stop_when=_review_decided,
    instructions=DG_REVIEWER_INSTRUCTIONS.format(**_fmt),
)


# ═══════════════════════════════════════════════════════════════
# Stage 4: QA Agent (single agent: write tests + run + verify)
# ═══════════════════════════════════════════════════════════════

qa_agent = Agent(
    name="qa_agent",
    model=SONNET,
    stateful=True,
    max_turns=12,
    max_tokens=60000,
    credentials=[GITHUB_CREDENTIAL],
    cli_config=CliConfig(
        allowed_commands=["git"],
        allow_shell=True,
        timeout=120,
    ),
    tools=[
        read_file, write_file, edit_file,
        read_files, edit_files,
        grep_search, glob_find, list_directory,
        file_outline, git_diff, run_command,
        run_unit_tests, run_e2e_tests,
        contextbook_write, contextbook_read, get_coder_context,
    ],
    stop_when=_qa_done,
    instructions=QA_AGENT_INSTRUCTIONS.format(**_fmt),
)

# ═══════════════════════════════════════════════════════════════
# Stage 5: DG Code Review (runs ONCE after impl + QA)
# ═══════════════════════════════════════════════════════════════

# dg_reviewer defined above with dg_skill

# ═══════════════════════════════════════════════════════════════
# Stage 6: Fix Coder + Fix QA (conditional rework from DG feedback)
# ═══════════════════════════════════════════════════════════════

fix_coder = Agent(
    name="fix_coder",
    model=SONNET,
    stateful=True,
    max_turns=15,
    max_tokens=60000,
    credentials=[GITHUB_CREDENTIAL],
    cli_config=CliConfig(
        allowed_commands=["git"],
        allow_shell=True,
        timeout=120,
    ),
    tools=[
        read_file, write_file, edit_file,
        read_files, edit_files,
        grep_search, glob_find, list_directory,
        file_outline, git_diff, run_command,
        lint_and_format, build_check, run_unit_tests,
        contextbook_write, contextbook_read, get_coder_context,
    ],
    stop_when=_fix_done,
    instructions=FIX_CODER_INSTRUCTIONS.format(**_fmt),
)

fix_qa = Agent(
    name="fix_qa",
    model=SONNET,
    stateful=True,
    max_turns=5,
    max_tokens=16000,
    tools=[
        run_unit_tests, run_command,
        contextbook_write, contextbook_read,
    ],
    stop_when=_fix_qa_done,
    instructions=FIX_QA_INSTRUCTIONS.format(**_fmt),
)

# ═══════════════════════════════════════════════════════════════
# Stage 7: PR Creator (pipeline)
# ═══════════════════════════════════════════════════════════════

pr_creator = Agent(
    name="pr_creator",
    model=SONNET,
    stateful=True,
    max_turns=6,
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
# Stage 8: PR Feedback Agent (feedback mode only)
#   Fetches PR comments/reviews, writes them to contextbook
# ═══════════════════════════════════════════════════════════════

pr_feedback = Agent(
    name="pr_feedback",
    model=SONNET,
    stateful=True,
    max_turns=3,
    max_tokens=16000,
    credentials=[GITHUB_CREDENTIAL],
    tools=[fetch_pr_context, contextbook_write, web_fetch],
    stop_when=_feedback_collected,
    instructions=PR_FEEDBACK_INSTRUCTIONS.format(**_fmt),
)

# ═══════════════════════════════════════════════════════════════
# Stage 9: PR Updater (feedback mode only)
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
# coder implements → QA tests → DG reviews → fix if needed → PR
pipeline = issue_analyst >> tech_lead >> coder >> qa_agent >> dg_reviewer >> fix_coder >> fix_qa >> pr_creator

# PR feedback → address comments, re-test, review, update PR
feedback_pipeline = pr_feedback >> coder >> qa_agent >> dg_reviewer >> fix_coder >> fix_qa >> pr_updater


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

    # Patch cli_config.working_dir on all agents that use CliConfig.
    # Agents are defined at module level but working_dir is only known at runtime.
    for agent in (issue_analyst, coder, qa_agent, fix_coder, pr_creator, pr_feedback, pr_updater):
        if hasattr(agent, "cli_config") and agent.cli_config:
            agent.cli_config.working_dir = work_dir

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

        result = handle.join(timeout=3600)
        result.print_result()


if __name__ == "__main__":
    main()
