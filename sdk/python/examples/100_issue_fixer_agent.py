#!/usr/bin/env python3
# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""Issue Fixer Agent — autonomous GitHub issue to PR pipeline.

Takes a GitHub repo and issue number, analyzes the codebase, implements a fix
with tests and docs, reviews it, and creates a pull request.

Architecture:
    issue_pr_fetcher >> tech_lead >> loop(coder, qa_agent) >> pr_updater

The coder<>qa loop uses SWARM strategy:
- Coder implements, outputs HANDOFF_TO_QA
- QA reviews, outputs QA_APPROVED (exit) or HANDOFF_TO_CODER (rework)
- Max 3 iterations

Usage:
    python 100_issue_fixer_agent.py owner/repo 42
    python 100_issue_fixer_agent.py owner/repo 42 --pr 157

Requirements:
    - Agentspan server running
    - GITHUB_TOKEN: agentspan credentials set GITHUB_TOKEN <your-token>
    - gh CLI installed and authenticated
"""

import os
import tempfile

from _issue_fixer_instructions import (
    CODER_IMPLEMENTER_INSTRUCTIONS,
    CODER_PLANNER_INSTRUCTIONS,
    ISSUE_PR_FETCHER_INSTRUCTIONS,
    PR_UPDATER_INSTRUCTIONS,
    QA_AGENT_INSTRUCTIONS,
    TECH_LEAD_INSTRUCTIONS,
)
from _issue_fixer_tools import (
    _contextbook_dir,
    build_check,
    contextbook_read,
    edit_file,
    edit_files,
    file_outline,
    find_references,
    git_diff,
    git_log,
    glob_find,
    grep_search,
    lint_and_format,
    list_directory,
    read_file,
    read_symbol,
    run_command,
    run_unit_tests,
    search_symbols,
    set_working_dir,
    setup_repo,
    write_architecture,
    write_coder_plan,
    write_file,
    write_implementation_report,
    write_qa_testing,
)

import dataclasses

from agentspan.agents import Agent, AgentRuntime, Strategy
from agentspan.agents.cli_config import CliConfig
from agentspan.agents.handoff import OnTextMention
from agentspan.agents.tool import get_tool_def

# ── Configuration ────────────────────────────────────────────
BRANCH_PREFIX = "fix/issue-"
OPUS = "anthropic/claude-opus-4-6"
SONNET = "anthropic/claude-sonnet-4-6"
GITHUB_CREDENTIAL = "GITHUB_TOKEN"
SERVER_URL = "http://localhost:6767"
MAX_QA_LOOPS = 10  # max coder<>qa iterations


def _limited(fn, max_calls: int):
    """Return a ToolDef copy with a per-agent max_calls limit."""
    return dataclasses.replace(get_tool_def(fn), max_calls=max_calls)


# ── Stop-when callbacks ──────────────────────────────────────
# File-based checks: deterministic, no LLM text parsing.
# The server skips stop_when evaluation on TOOL_CALLS turns, so these
# only run when the LLM produced text — no need to check finishReason here.

import time as _time

_EXECUTION_START = _time.time()


def _contextbook_written(section: str) -> bool:
    """Check if a contextbook section file was written during THIS execution."""
    path = _contextbook_dir() / f"{section}.md"
    if not path.exists() or path.stat().st_size == 0:
        return False
    return path.stat().st_mtime >= _EXECUTION_START


def _has_text_in_context(context: dict, *targets: str) -> bool:
    """Check if ALL target strings appear in the result or tool-result messages."""
    result = context.get("result", "")
    result_str = str(result) if result else ""
    if result_str and all(t in result_str for t in targets):
        return True
    messages = context.get("messages", [])
    if isinstance(messages, list):
        for msg in messages:
            if not isinstance(msg, dict):
                continue
            role = msg.get("role", "")
            if role in ("system", "user"):
                continue
            content = str(msg.get("message", "") or msg.get("content", ""))
            if content and all(t in content for t in targets):
                return True
    return False


def _tech_lead_done(context: dict, **kwargs) -> bool:
    """Stop when architecture_design_test contextbook file exists."""
    return _contextbook_written("architecture_design_test")


def _planner_done(context: dict, **kwargs) -> bool:
    """Stop when change map exists — accepts either section name."""
    return _contextbook_written("coder_plan") or _contextbook_written("implementation")


def _implementer_done(context: dict, **kwargs) -> bool:
    """Stop when implementation_report contextbook file exists."""
    return _contextbook_written("implementation_report")


def _qa_approved(context: dict, **kwargs) -> bool:
    """Stop the SWARM loop when QA approves (text-based — no file equivalent)."""
    return _has_text_in_context(context, "QA_APPROVED")


def _pr_done(context: dict, **kwargs) -> bool:
    """Stop PR updater when a PR URL is output (text-based — no file equivalent)."""
    return _has_text_in_context(context, "github.com", "/pull/")


def main():
    import argparse

    parser = argparse.ArgumentParser(
        description="Issue Fixer Agent — autonomous GitHub issue to PR pipeline",
        epilog="Examples:\n"
        "  python 100_issue_fixer_agent.py facebook/react 42\n"
        "  python 100_issue_fixer_agent.py facebook/react 42 --pr 157\n",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("repo", type=str, help="GitHub repo (owner/name)")
    parser.add_argument("issue", type=int, help="GitHub issue number")
    parser.add_argument("--pr", type=int, default=None, help="Existing PR number")
    args = parser.parse_args()

    import re as _re

    # Normalize repo to owner/name format
    repo = _re.sub(r"^https?://", "", args.repo)
    repo = _re.sub(r"^github\.com/", "", repo)
    repo = _re.sub(r"\.git$", "", repo)
    repo = repo.strip("/")

    issue_number = args.issue
    pr_number = args.pr

    _fmt = {"repo": repo, "branch_prefix": BRANCH_PREFIX}

    # Working directory — deterministic so restarts reuse existing repo clone + contextbook
    repo_slug = repo.replace("/", "-")
    issue_slug = f"pr-{pr_number}" if pr_number else f"issue-{issue_number}"
    work_dir = os.path.join(tempfile.gettempdir(), f"{repo_slug}-fix-{issue_slug}")
    set_working_dir(work_dir)

    cli = CliConfig(
        allowed_commands=["git", "gh", "find"],
        allow_shell=True,
        timeout=120,
        working_dir=work_dir,
    )

    # ═══════════════════════════════════════════════════════════════
    # Agents
    # ═══════════════════════════════════════════════════════════════

    issue_pr_fetcher = Agent(
        name="issue_pr_fetcher",
        model=SONNET,
        stateful=True,
        max_turns=5,
        max_tokens=16000,
        credentials=[GITHUB_CREDENTIAL],
        tools=[setup_repo],
        instructions=ISSUE_PR_FETCHER_INSTRUCTIONS.format(**_fmt),
    )

    tech_lead = Agent(
        name="tech_lead",
        model=OPUS,
        stateful=True,
        max_turns=100,
        max_tokens=60000,
        tools=[
            read_file,
            read_symbol,
            grep_search,
            glob_find,
            list_directory,
            file_outline,
            search_symbols,
            find_references,
            git_log,
            run_command,
            write_architecture,
            _limited(contextbook_read, 3),
        ],
        stop_when=_tech_lead_done,
        instructions=TECH_LEAD_INSTRUCTIONS.format(**_fmt),
    )

    # Coder is split into planner >> implementer (sequential).
    # Planner reads all context + explores codebase → writes change map.
    # Implementer reads ONLY the change map → writes code, tests, commits.

    coder_planner = Agent(
        name="coder_planner",
        model=OPUS,
        stateful=True,
        max_turns=100,
        max_tokens=60000,
        prefill_tools=[
            contextbook_read.call(section="issue_pr"),
            contextbook_read.call(section="architecture_design_test"),
            contextbook_read.call(section="implementation_report"),
            contextbook_read.call(section="qa_testing"),
        ],
        tools=[
            read_file,
            read_symbol,
            grep_search,
            glob_find,
            list_directory,
            file_outline,
            search_symbols,
            find_references,
            write_coder_plan,
        ],
        stop_when=_planner_done,
        instructions=CODER_PLANNER_INSTRUCTIONS.format(**_fmt),
    )

    coder_implementer = Agent(
        name="coder_implementer",
        model=SONNET,
        stateful=True,
        max_turns=1000,
        max_tokens=60000,
        credentials=[GITHUB_CREDENTIAL],
        cli_config=cli,
        prefill_tools=[contextbook_read.call(section="coder_plan")],
        tools=[
            read_file,
            write_file,
            edit_file,
            edit_files,
            run_command,
            lint_and_format,
            build_check,
            run_unit_tests,
            write_implementation_report,
        ],
        stop_when=_implementer_done,
        instructions=CODER_IMPLEMENTER_INSTRUCTIONS.format(**_fmt),
    )

    coder = Agent(
        name="coder",
        model=SONNET,
        agents=[coder_planner, coder_implementer],
        strategy=Strategy.SEQUENTIAL,
        max_turns=2000,
        max_tokens=16000,
    )

    qa_agent = Agent(
        name="qa_agent",
        model=SONNET,
        stateful=True,
        max_turns=1000,
        max_tokens=60000,
        credentials=[GITHUB_CREDENTIAL],
        cli_config=cli,
        tools=[
            read_symbol,
            grep_search,
            glob_find,
            git_diff,
            run_command,
            run_unit_tests,
            write_qa_testing,
            _limited(contextbook_read, 5),
        ],
        handoffs=[OnTextMention(text="HANDOFF_TO_CODER", target="coder")],
        instructions=QA_AGENT_INSTRUCTIONS.format(**_fmt),
    )

    # SWARM: coder<>qa loop. Terminates when QA outputs QA_APPROVED.
    coder_qa_loop = Agent(
        name="coder_qa_loop",
        model=SONNET,
        agents=[coder, qa_agent],
        strategy=Strategy.SWARM,
        max_turns=MAX_QA_LOOPS * 30,  # budget for N full coder+qa cycles
        max_tokens=16000,
        stop_when=_qa_approved,
    )

    pr_updater = Agent(
        name="pr_updater",
        model=SONNET,
        stateful=True,
        max_turns=50,
        max_tokens=16000,
        credentials=[GITHUB_CREDENTIAL],
        cli_config=cli,
        tools=[git_diff, git_log, _limited(contextbook_read, 8), run_command],
        stop_when=_pr_done,
        instructions=PR_UPDATER_INSTRUCTIONS.format(**_fmt),
    )

    # ═══════════════════════════════════════════════════════════════
    # Pipeline
    # ═══════════════════════════════════════════════════════════════

    pipeline = issue_pr_fetcher >> tech_lead >> coder_qa_loop >> pr_updater

    # Build prompt
    prompt_parts = [f"Fix issue #{issue_number} from {repo}."]
    if pr_number:
        prompt_parts.append(f"Address feedback on PR #{pr_number}.")
    prompt_parts.append(f"Working directory: {work_dir}")
    if pr_number:
        prompt_parts.append(f"PR number to pass to setup_repo: {pr_number}")
    prompt = " ".join(prompt_parts)

    idempotency_key = f"issue-{issue_number}" + (f"-pr-{pr_number}" if pr_number else "")

    print(f"Working directory: {work_dir}")
    print(f"Mode: {'PR feedback' if pr_number else 'New issue fix'}")

    with AgentRuntime() as rt:
        handle = rt.start(pipeline, prompt, idempotency_key=idempotency_key)
        print(f"Execution started: {handle.execution_id}")
        print(f"Idempotency key: {idempotency_key}")
        print(f"Monitor at: {SERVER_URL}/execution/{handle.execution_id}")

        result = handle.join(timeout=3600)
        result.print_result()


if __name__ == "__main__":
    main()
