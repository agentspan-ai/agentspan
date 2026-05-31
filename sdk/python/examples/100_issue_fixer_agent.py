#!/usr/bin/env python3
# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""Issue Fixer Agent — autonomous GitHub issue to PR pipeline.

A multi-agent coding agent that takes a GitHub issue number, analyzes the
codebase, implements a fix with tests, and creates a pull request.

Architecture: Deterministic pipeline with sequential review stages

    issue_analyst >> tech_lead >> [impl_loop: coder <-> tl_review]
                  >> (qa_lead >> test_coder >> qa_reviewer)
                  >> dg_reviewer >> (fix_coder >> fix_qa)
                  >> docs_agent >> pr_creator

The impl_loop SWARM handles coder <-> TL review for approval/rework cycles.
Testing is SEQUENTIAL: QA plans >> coder writes >> QA reviews + runs e2e.
DG review runs after testing, followed by fix+retest if needed.

Usage:
    python 100_issue_fixer_agent.py <issue_number>
    python 100_issue_fixer_agent.py 42

Requirements:
    - Agentspan server running
    - GH_TOKEN: agentspan credentials set GH_TOKEN <your-token>
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
    fetch_issue_context, fetch_pr_context, create_pr, update_pr,
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
GITHUB_CREDENTIAL = "GH_TOKEN"

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
    TEST_CODER_INSTRUCTIONS,
    DG_REVIEWER_INSTRUCTIONS,
    QA_PLANNER_INSTRUCTIONS,
    QA_REVIEWER_INSTRUCTIONS,
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
# Stage 1: Issue Analyst — deterministic tool, no LLM needed
#   Fetches issue, clones repo, creates branch, writes contextbook.
#   One tool call replaces 10-20 LLM turns of CLI orchestration.
# ═══════════════════════════════════════════════════════════════

issue_analyst = Agent(
    name="issue_analyst",
    model=SONNET,
    stateful=True,
    max_turns=2,
    max_tokens=4096,
    credentials=[GITHUB_CREDENTIAL],
    tools=[fetch_issue_context],
    instructions=(
        f"Call fetch_issue_context with repo='{REPO}', the issue number from the prompt, "
        f"and branch_prefix='{BRANCH_PREFIX}'. After the tool returns, output the FULL tool result "
        f"as your response verbatim — the next agent needs REPO, BRANCH, ISSUE, MODULE, DETAILS."
    ),
)

# ═══════════════════════════════════════════════════════════════
# Stage 2: Tech Lead — plan (pipeline)
# ═══════════════════════════════════════════════════════════════

tech_lead = Agent(
    name="tech_lead",
    model=OPUS,
    stateful=True,
    max_turns=50,
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
    max_turns=50,
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
        contextbook_write, contextbook_read,
    ],
    instructions=CODER_INSTRUCTIONS.format(**_fmt),
)

# DG skill + coordinator wrapper
dg_skill = skill(
    DG_SKILL_PATH,
    model=OPUS,
    agent_models={"gilfoyle": SONNET, "dinesh": SONNET},
    params={"rounds": 1},
)
# Hard limit: 1 round = gilfoyle(1 turn) + dinesh(1 turn) + orchestrator(2 turns) = 4 max.
# The params={"rounds": 1} + prompt prefix are hints; max_turns is the hard cap.
dg_skill.max_turns = 4

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

# Outer loop: coder <-> TL review until TL says IMPL_APPROVED
impl_loop = Agent(
    name="impl_loop",
    model=SONNET,
    stateful=True,
    strategy=Strategy.SWARM,
    agents=[coder, tl_reviewer],
    handoffs=[
        OnTextMention(text="NEEDS_REWORK", target="coder"),
        OnTextMention(text="HANDOFF_TO_CODER", target="coder"),
        OnTextMention(text="IMPL_APPROVED", target="tl_reviewer"),
    ],
    termination=TextMentionTermination("IMPL_APPROVED"),
    max_turns=MAX_REVIEW_CYCLES * 2 + 2,
    max_tokens=60000,
    timeout_seconds=SWARM_TIMEOUT,
    instructions="Start with coder.",
)

# ═══════════════════════════════════════════════════════════════
# Stage 4: Test Loop (coder <-> QA, until QA says TESTS_PASS)
# ═══════════════════════════════════════════════════════════════

# Separate coder instance for test writing — reduced tools, focused instructions
test_coder = Agent(
    name="test_coder",
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
        read_file, write_file,
        grep_search, glob_find, list_directory,
        run_command, contextbook_read,
    ],
    instructions=TEST_CODER_INSTRUCTIONS.format(**_fmt),
)

qa_lead = Agent(
    name="qa_lead",
    model=SONNET,
    stateful=True,
    max_turns=30,
    max_tokens=60000,
    tools=[
        read_file, write_file, grep_search, glob_find, list_directory,
        file_outline, git_diff, run_command, web_fetch,
        run_unit_tests, run_e2e_tests,
        contextbook_write, contextbook_read, contextbook_summary,
    ],
    instructions=QA_PLANNER_INSTRUCTIONS.format(**_fmt),
)

# QA reviewer: reviews tests, runs e2e, captures evidence
qa_reviewer = Agent(
    name="qa_reviewer",
    model=SONNET,
    stateful=True,
    max_turns=40,
    max_tokens=60000,
    tools=[
        read_file, write_file, grep_search, glob_find, list_directory,
        file_outline, git_diff, run_command, web_fetch,
        run_unit_tests, run_e2e_tests,
        contextbook_write, contextbook_read, contextbook_summary,
    ],
    instructions=QA_REVIEWER_INSTRUCTIONS.format(**_fmt),
)

# Sequential: QA plans → coder writes tests → QA reviews + runs e2e
# All three steps are deterministic — no handoff text needed.
test_then_verify = qa_lead >> test_coder >> qa_reviewer

# ═══════════════════════════════════════════════════════════════
# Stage 4b: Fix + Retest (post-DG rework)
# ═══════════════════════════════════════════════════════════════

fix_coder = Agent(
    name="fix_coder",
    model=SONNET,
    stateful=True,
    max_turns=25,
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
        contextbook_write, contextbook_read,
    ],
    instructions=CODER_INSTRUCTIONS.format(**_fmt),
)

fix_qa = Agent(
    name="fix_qa",
    model=SONNET,
    stateful=True,
    max_turns=30,
    max_tokens=60000,
    tools=[
        read_file, write_file, grep_search, glob_find, list_directory,
        file_outline, git_diff, run_command, web_fetch,
        run_unit_tests, run_e2e_tests,
        contextbook_write, contextbook_read, contextbook_summary,
    ],
    instructions=QA_REVIEWER_INSTRUCTIONS.format(**_fmt),
)

fix_and_retest = fix_coder >> fix_qa

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
# Stage 6: PR Creator — deterministic tool, no LLM needed
#   Reads contextbook, commits, pushes, creates PR with change_context JSON.
# ═══════════════════════════════════════════════════════════════

pr_creator = Agent(
    name="pr_creator",
    model=SONNET,
    stateful=True,
    max_turns=2,
    max_tokens=4096,
    credentials=[GITHUB_CREDENTIAL],
    tools=[create_pr],
    instructions=(
        f"Call create_pr with repo='{REPO}', the issue number from the prompt, "
        f"and qa_evidence_dir='{QA_EVIDENCE_DIR}'. After the tool returns, "
        f"output the FULL tool result as your response — include the PR URL."
    ),
)

# ═══════════════════════════════════════════════════════════════
# Stage 7: PR Feedback — deterministic tool, no LLM needed
#   Fetches PR comments/reviews, clones repo, writes contextbook.
#   One tool call replaces 20 LLM turns of CLI orchestration.
# ═══════════════════════════════════════════════════════════════

pr_feedback = Agent(
    name="pr_feedback",
    model=SONNET,
    stateful=True,
    max_turns=2,
    max_tokens=4096,
    credentials=[GITHUB_CREDENTIAL],
    tools=[fetch_pr_context],
    instructions=(
        f"Call fetch_pr_context with repo='{REPO}' and the PR number from the prompt. "
        f"After the tool returns, output the FULL tool result as your response. "
        f"Include all details — PR title, branch, feedback found, contextbook status."
    ),
)

# ═══════════════════════════════════════════════════════════════
# Stage 8: PR Updater — deterministic tool, no LLM needed
#   Pushes changes to existing branch, posts comment with feedback resolution.
# ═══════════════════════════════════════════════════════════════

pr_updater = Agent(
    name="pr_updater",
    model=SONNET,
    stateful=True,
    max_turns=2,
    max_tokens=4096,
    credentials=[GITHUB_CREDENTIAL],
    tools=[update_pr],
    instructions=(
        f"Call update_pr with repo='{REPO}' and the PR number from the prompt. "
        f"After the tool returns, output the FULL tool result as your response — include the PR URL."
    ),
)

# ═══════════════════════════════════════════════════════════════
# Pipelines
# ═══════════════════════════════════════════════════════════════

# New issue → full pipeline
pipeline = issue_analyst >> tech_lead >> impl_loop >> test_then_verify >> dg_reviewer >> fix_and_retest >> docs_agent >> pr_creator

# PR feedback → address comments, re-review, re-test, update PR
feedback_pipeline = pr_feedback >> impl_loop >> test_then_verify >> dg_reviewer >> fix_and_retest >> pr_updater


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
