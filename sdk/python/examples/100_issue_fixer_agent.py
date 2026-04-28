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
import uuid

from _issue_fixer_instructions import (
    CODER_INSTRUCTIONS,
    ISSUE_PR_FETCHER_INSTRUCTIONS,
    PR_UPDATER_INSTRUCTIONS,
    QA_AGENT_INSTRUCTIONS,
    TECH_LEAD_INSTRUCTIONS,
)
from _issue_fixer_tools import (
    build_check,
    contextbook_read,
    contextbook_write,
    edit_file,
    edit_files,
    file_outline,
    find_references,
    get_coder_context,
    git_diff,
    git_log,
    glob_find,
    grep_search,
    lint_and_format,
    list_directory,
    read_file,
    read_files,
    run_command,
    run_unit_tests,
    search_symbols,
    set_working_dir,
    setup_repo,
    write_file,
)

from agentspan.agents import Agent, AgentRuntime, Strategy
from agentspan.agents.cli_config import CliConfig
from agentspan.agents.handoff import OnTextMention

# ── Configuration ────────────────────────────────────────────
BRANCH_PREFIX = "fix/issue-"
OPUS = "anthropic/claude-opus-4-6"
SONNET = "anthropic/claude-sonnet-4-6"
GITHUB_CREDENTIAL = "GITHUB_TOKEN"
SERVER_URL = "http://localhost:6767"
MAX_QA_LOOPS = 3  # max coder<>qa iterations


# ── Stop-when callbacks ──────────────────────────────────────


def _fetcher_done(context: dict, **kwargs) -> bool:
    """Stop fetcher when TODO list is output."""
    result = context.get("result", "")
    return "## TODO" in result and "REPO:" in result


def _tech_lead_done(context: dict, **kwargs) -> bool:
    """Stop Tech Lead when handoff or design was written."""
    result = context.get("result", "")
    if "HANDOFF_TO_CODER" in result:
        return True
    for msg in context.get("messages", []):
        if not isinstance(msg, dict):
            continue
        content = msg.get("content", "")
        if isinstance(content, str) and "wrote 'architecture_design_test'" in content:
            return True
        if isinstance(content, list):
            for part in content:
                if isinstance(part, dict) and "wrote 'architecture_design_test'" in str(
                    part.get("text", "")
                ):
                    return True
    return False


def _qa_approved(context: dict, **kwargs) -> bool:
    """Stop the SWARM loop when QA approves."""
    result = context.get("result", "")
    return "QA_APPROVED" in result


def _pr_done(context: dict, **kwargs) -> bool:
    """Stop PR updater when a PR URL is output."""
    result = context.get("result", "")
    return "github.com" in result and "/pull/" in result


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

    # Working directory
    repo_slug = repo.replace("/", "-")
    work_dir = os.path.join(tempfile.gettempdir(), f"{repo_slug}-fix-{uuid.uuid4().hex[:12]}")
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
        tools=[setup_repo, contextbook_write],
        stop_when=_fetcher_done,
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
            read_files,
            grep_search,
            glob_find,
            list_directory,
            file_outline,
            search_symbols,
            find_references,
            git_log,
            run_command,
            contextbook_write,
            contextbook_read,
        ],
        stop_when=_tech_lead_done,
        instructions=TECH_LEAD_INSTRUCTIONS.format(**_fmt),
    )

    coder = Agent(
        name="coder",
        model=SONNET,
        stateful=True,
        max_turns=20,
        max_tokens=60000,
        credentials=[GITHUB_CREDENTIAL],
        cli_config=cli,
        tools=[
            read_file,
            write_file,
            edit_file,
            read_files,
            edit_files,
            grep_search,
            glob_find,
            list_directory,
            file_outline,
            git_diff,
            git_log,
            run_command,
            lint_and_format,
            build_check,
            run_unit_tests,
            contextbook_write,
            contextbook_read,
            get_coder_context,
        ],
        handoffs=[OnTextMention(text="HANDOFF_TO_QA", target="qa_agent")],
        instructions=CODER_INSTRUCTIONS.format(**_fmt),
    )

    qa_agent = Agent(
        name="qa_agent",
        model=SONNET,
        stateful=True,
        max_turns=10,
        max_tokens=60000,
        credentials=[GITHUB_CREDENTIAL],
        cli_config=cli,
        tools=[
            read_file,
            read_files,
            grep_search,
            glob_find,
            git_diff,
            run_command,
            run_unit_tests,
            contextbook_write,
            contextbook_read,
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
        stop_when=_qa_approved,
    )

    pr_updater = Agent(
        name="pr_updater",
        model=SONNET,
        stateful=True,
        max_turns=10,
        max_tokens=16000,
        credentials=[GITHUB_CREDENTIAL],
        cli_config=cli,
        tools=[git_diff, git_log, contextbook_read, run_command],
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
