#!/usr/bin/env python3
# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""Issue Fixer Agent: fetch issue/PR context, code the fix, publish the PR."""

from __future__ import annotations

import argparse
import dataclasses
import json
import os
import re
import tempfile
import time as _time

from _issue_fixer_tools import (
    _contextbook_dir,
    apply_patch,
    build_check,
    contextbook_read,
    edit_file,
    edit_files,
    file_outline,
    finalize_pr_update,
    git_diff,
    git_status,
    glob_find,
    grep_search,
    lint_and_format,
    list_directory,
    prepare_issue_workspace,
    read_file,
    read_symbol,
    search_symbols,
    set_working_dir,
    validate_issue_workspace,
    validate_pr_result,
    write_coder_context,
    write_file,
    write_implementation_report,
    write_task_brief,
)

from agentspan.agents import Agent, AgentRuntime, OnFail, Position, RegexGuardrail, Strategy
from agentspan.agents.tool import get_tool_def

BRANCH_PREFIX = "fix/issue-"
SONNET = "anthropic/claude-sonnet-4-6"
CODEX = "openai/gpt-5.3-codex"

FETCHER_MAX_TURNS = 20
CODER_MAX_TURNS = 120


FETCHER_INSTRUCTIONS = """\
You are the PR/Issue Fetcher.

The fetch and validation tools have already run through prefill_tools. The full
issue/PR dump is available in the prefilled `issue_pr` contextbook section.

Inspect the validation result first.
- If validation FAILED: summarize the failure in plain text and do not output
  FETCH_READY. Do not call write_task_brief.
- If validation PASSED: produce a Task Brief for the Coder using ONLY the
  prefilled context. Do not call any inspection or shell tools — none are
  available to you.

Task Brief format. Use these four markdown headings verbatim and in this order:

## Synopsis
Two to four sentences. State what the issue is asking for, the user-visible
symptom or feature, and the intended outcome. Note the mode (new issue fix vs.
PR feedback) and any salient labels.

## Issue Comments
Bulleted summary of each issue comment as `- @author: one-line takeaway`. If
there are none, write the single line `No issue comments.`.

## PR Comments
Bulleted summary of PR body, reviews, top-level PR comments, and inline review
comments (include `file:line` when present) as
`- @author [kind]: one-line takeaway`. If there is no PR, write `No PR.`. If
there is a PR with no feedback yet, write `No PR comments.`.

## TODO
Numbered, ordered, concrete steps for the Coder. Each step is a single
actionable change, investigation, or validation. The final step must be a
validation step (build_check and/or lint_and_format).

Workflow:
1. Call write_task_brief(content=<the brief>) exactly once with the brief in
   the format above.
2. After write_task_brief succeeds, emit one final response whose body is the
   same brief text followed by a final line containing exactly FETCH_READY.
   Do not include any tool calls in that final response.
"""


CODER_INSTRUCTIONS = """\
You are the Coder. Implement the requested GitHub issue/PR fix.

Context is already loaded through prefill tools:
- issue_pr: issue body, issue comments, PR body/comments/reviews when present
- repo_conventions: repository docs and detected build/test/lint commands

Treat the TODO in task_brief as the authoritative ordered checklist for this
fix. Follow it step-by-step; fall back to issue_pr only when more detail is
needed.

First thing first --> you have the issue context and task brief. Use it to come up with a plan on what you need to do,
what files to search, edit, what symbols to search etc.  Then use parallel tool calls to do this in parallel as much
as possible.  The system can do massive parallel forks so do not worry about that.
once you do that, write it up in the contextbook with the files you have searched for.
The contextbook for coder must contain information about a) files read b) files written
c) checklist of what needs to be done and their current status

Once the checklist is complete, ONLY then run build_check / lint_and_format and complete the work. If validation fails, repeat the process. Do not call run_unit_tests — it is temporarily disabled.

Your job - In the following order.  the order MUST be the following:
1. Understand the issue/PR context.
2. Make focused code changes.
3. Run relevant validation with build_check() and/or lint_and_format().
   (run_unit_tests is intentionally disabled for now — do not call it.)
4. Call write_coder_context(content=...) with a concise checklist/status.
5. Call write_implementation_report(content=...) with files changed, tests run,
   and remaining risks.
6. After write_implementation_report succeeds, make one final response with
   exactly CODER_DONE and no tool calls.

Do not commit, push, create a PR, or update a PR. The PR updater handles that.
Use run_command only for safe custom build/test/lint/status commands; it is not
for reading files. Use read_file, read_symbol, grep_search, glob_find,
file_outline, search_symbols for inspection. The tools enforce bounded inspection and validation budgets.
"""


no_destructive_shell = RegexGuardrail(
    patterns=[
        r"\brm\s+-rf?\s+/(?:\s|$)",
        r"\brm\s+-rf?\s+/[a-zA-Z]",
        r"\bgit\s+push\s+(?:--force|-f)\b",
        r"\bgit\s+reset\s+--hard\b",
        r"\bdd\s+if=.*\s+of=/dev/(?:sd[a-z]|nvme)",
        r":\(\)\s*\{.*\}\s*;.*:",
    ],
    name="no_destructive_shell",
    position=Position.INPUT,
    on_fail=OnFail.RAISE,
    message="Blocked: destructive shell command pattern.",
)


_round_start_ts = _time.time()


def _limited(fn, max_calls: int):
    return dataclasses.replace(get_tool_def(fn), max_calls=max_calls)


def _guarded(fn, guardrails):
    return dataclasses.replace(get_tool_def(fn), guardrails=list(guardrails))


def _begin_round() -> None:
    global _round_start_ts
    _round_start_ts = _time.time()
    _time.sleep(0.05)


def _server_base_url() -> str:
    raw = os.environ.get("AGENTSPAN_SERVER_URL", "http://localhost:6767/api")
    return raw.rstrip("/").removesuffix("/api")


def _contextbook_written(section: str) -> bool:
    path = _contextbook_dir() / f"{section}.md"
    return path.exists() and path.stat().st_size > 0 and path.stat().st_mtime >= _round_start_ts


def _stop_result(context: dict, kwargs: dict) -> object:
    if isinstance(context, dict) and "result" in context:
        return context.get("result")
    return kwargs.get("result")


def _result_contains(result: object, marker: str) -> bool:
    if result is None:
        return False
    if isinstance(result, list):
        return any(_result_contains(item, marker) for item in result)
    if isinstance(result, dict):
        return any(_result_contains(value, marker) for value in result.values())
    return marker in str(result)


_BLOCKED_TOKEN = "Blocked: coder inspection budget exceeded"
# Net-blocked threshold for the Layer-2 stall detector. Raised 5 → 15 after
# execution 8d5fc4fe-aef0-4528-be68-fbba323bde64 where the agent terminated
# at iter 7 — only two turns after its single ``write_coder_context`` —
# because every blocked tool call counted. With 3–4 parallel calls per turn
# a threshold of 5 hit after just two turns of post-plan searching, before
# the model had time to digest the plan and pivot to editing. At 15, the
# agent gets ~4-5 turns of "your inspections are blocked" feedback before
# we force termination — enough to either commit to an edit OR call
# ``write_implementation_report`` with a concrete blocker.
_STALLED_BLOCKED_THRESHOLD = 15

# Progress-marker tool names — each call to one of these in recent history
# subtracts from the net-blocked count below. The reasoning: a model that
# has just emitted ``write_coder_context`` or ``write_implementation_report``
# IS converging (just slowly); we don't want a few stale blocked messages
# from before the progress call to mask actual forward motion. Each progress
# call discounts the blocked count by ``_PROGRESS_DISCOUNT`` so a planning
# event "buys back" some of the budget without infinitely suppressing the
# stall detector.
_PROGRESS_MARKERS = ("write_coder_context", "write_implementation_report")
_PROGRESS_DISCOUNT = 5


def _budget_blocked(result: object) -> bool:
    text = str(result or "")
    return (
        _BLOCKED_TOKEN in text
        or "Blocked: validation budget exceeded" in text
        or "implementation_report is blocked" in text
    )


def _count_blocked_tool_messages(messages: object) -> int:
    """Net count of blocked tool messages minus progress-marker calls.

    Counts ``tool``-role messages whose content carries the inspection-blocked
    sentinel — these are the agent's evidence of being stuck. Subtracts
    ``_PROGRESS_DISCOUNT`` per progress-marker call (``write_coder_context``
    or ``write_implementation_report``) seen in the same window: those signal
    forward motion and should "buy back" some of the budget. Returns a
    non-negative integer the caller compares against
    ``_STALLED_BLOCKED_THRESHOLD``.
    """
    if not isinstance(messages, list):
        return 0
    blocked = 0
    progress = 0
    for m in messages:
        if not isinstance(m, dict):
            continue
        role = m.get("role")
        # Tool result messages: blocked sentinel lives in ``message`` or
        # ``toolCalls[*].output.result``.
        if role == "tool":
            blob = str(m.get("message") or "")
            if _BLOCKED_TOKEN in blob:
                blocked += 1
                continue
            for tc in m.get("toolCalls") or []:
                out = (tc or {}).get("output")
                if isinstance(out, dict):
                    if _BLOCKED_TOKEN in str(out.get("result") or ""):
                        blocked += 1
                        break
                    if _BLOCKED_TOKEN in json.dumps(out):
                        blocked += 1
                        break
        # Assistant tool_call messages: detect progress-marker emissions.
        # ChatMessage.Role.tool_call serializes with these toolCalls entries
        # and an empty ``message`` field (see AgentChatCompleteTaskMapper).
        elif role == "tool_call":
            for tc in m.get("toolCalls") or []:
                name = (tc or {}).get("name") or ""
                if name in _PROGRESS_MARKERS:
                    progress += 1
    return max(0, blocked - progress * _PROGRESS_DISCOUNT)


def _fetcher_done(context: dict, **kwargs) -> bool:
    return (
        _contextbook_written("issue_pr")
        and _contextbook_written("repo_conventions")
        and _contextbook_written("task_brief")
        and _result_contains(_stop_result(context, kwargs), "FETCH_READY")
    )


def _coder_done(context: dict, **kwargs) -> bool:
    # Termination paths, in priority order:
    # 1) The LLM's own result echoed a budget-blocked message → stop.
    if _budget_blocked(_stop_result(context, kwargs)):
        return True
    # 2) Layer 2 forcing function: the model has been silently ignoring
    #    inspection-budget-blocked tool results and looping. If recent
    #    history contains >= _STALLED_BLOCKED_THRESHOLD blocked tool
    #    messages, terminate hard so the agent doesn't run to max_turns.
    messages = None
    if isinstance(context, dict):
        messages = context.get("messages")
    if messages is None:
        messages = kwargs.get("messages")
    if _count_blocked_tool_messages(messages) >= _STALLED_BLOCKED_THRESHOLD:
        return True
    # 3) Normal happy-path completion.
    return (
        _contextbook_written("coder_context")
        and _contextbook_written("implementation_report")
        and _result_contains(_stop_result(context, kwargs), "CODER_DONE")
    )


def _normalize_repo_for_path(repo: str) -> str:
    repo = re.sub(r"^https?://", "", repo or "")
    repo = re.sub(r"^github\.com/", "", repo)
    repo = re.sub(r"\.git$", "", repo).strip("/")
    if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repo):
        raise ValueError(f"Invalid GitHub repo {repo!r}; expected owner/name")
    return repo


def _workspace_dir_for_key(idempotency_key: str) -> str:
    safe_key = re.sub(r"[^A-Za-z0-9_.-]+", "-", idempotency_key).strip("-")
    return os.path.join(tempfile.gettempdir(), safe_key)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Issue Fixer Agent: fetch issue/PR context, code, publish PR",
        epilog=(
            "Examples:\n"
            "  python 100_issue_fixer_agent.py facebook/react 42\n"
            "  python 100_issue_fixer_agent.py facebook/react 42 --pr 157\n"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("repo", type=str, help="GitHub repo (owner/name)")
    parser.add_argument("issue", type=int, help="GitHub issue number")
    parser.add_argument("--pr", type=int, default=0, help="Existing PR number")
    args = parser.parse_args()

    repo = _normalize_repo_for_path(args.repo)
    issue_number = args.issue
    pr_number = args.pr or 0
    repo_slug = repo.replace("/", "-")
    base_idempotency_key = f"issue-fixer-v12-{repo_slug}-issue-{issue_number}" + (
        f"-pr-{pr_number}" if pr_number else ""
    )
    work_dir = _workspace_dir_for_key(base_idempotency_key)
    os.makedirs(work_dir, exist_ok=True)
    set_working_dir(work_dir)

    pr_fetcher = Agent(
        name="issue_fixer_pr_fetcher",
        model=SONNET,
        stateful=True,
        max_turns=FETCHER_MAX_TURNS,
        max_tokens=32000,
        prefill_tools=[
            prepare_issue_workspace.call(
                repo=repo,
                issue_number=issue_number,
                pr_number=pr_number,
                branch_prefix=BRANCH_PREFIX,
            ),
            validate_issue_workspace.call(),
            contextbook_read.call(section="issue_pr"),
        ],
        tools=[write_task_brief],
        stop_when=_fetcher_done,
        instructions=FETCHER_INSTRUCTIONS,
    )

    coder = Agent(
        name="issue_fixer_coder",
        model=SONNET,
        stateful=True,
        reasoning_effort="medium",
        max_turns=CODER_MAX_TURNS,
        max_tokens=32000,
        prefill_tools=[
            contextbook_read.call(section="issue_pr"),
            contextbook_read.call(section="repo_conventions"),
            contextbook_read.call(section="task_brief"),
            list_directory.call(),
            git_status.call(),
            git_diff.call(),
        ],
        tools=[
            read_file,
            read_symbol,
            grep_search,
            glob_find,
            file_outline,
            search_symbols,
            write_file,
            edit_file,
            edit_files,
            apply_patch,
            lint_and_format,
            build_check,
            write_coder_context,
            write_implementation_report,
        ],
        stop_when=_coder_done,
        instructions=CODER_INSTRUCTIONS,
    )

    # PR finalization is intentionally NOT an Agent — it's a fully
    # deterministic sequence (commit, push, create/update PR, validate). When
    # it was wrapped as an Agent with prefill_tools and no tools, the LLM
    # still got invoked one final time and would occasionally hallucinate
    # ("I'll implement issue #N from scratch..."). Prompt fixes don't survive
    # strong agent priors. The structural fix is to drop the LLM round and
    # call the tools directly after the agent pipeline finishes — see below.

    issue_fixer = Agent(
        name="issue_fixer_pipeline",
        model=SONNET,
        stateful=True,
        agents=[pr_fetcher, coder],
        strategy=Strategy.SEQUENTIAL,
        timeout_seconds=0,
        instructions=(
            "Run the issue fixer pipeline in order: PR/issue fetcher, then coder. "
            "Do not skip stages. PR finalization happens deterministically after "
            "this pipeline returns and is not an agent stage."
        ),
    )

    prompt = (
        f"Fix issue #{issue_number} from {repo}. "
        f"Working directory: {work_dir}. "
        f"{'Address feedback on PR #' + str(pr_number) + '.' if pr_number else ''}"
    )

    print(f"Idempotency key: {base_idempotency_key}")
    print(f"Working directory: {work_dir}")
    print(f"Mode: {'PR feedback' if pr_number else 'New issue fix'}")
    server_base = _server_base_url()

    with AgentRuntime() as rt:
        print("\n=== Running issue_fixer_pipeline: fetcher -> coder ===")
        _begin_round()
        result = rt.run(
            issue_fixer,
            (
                f"{prompt}\n\n"
                f"repo={repo}\nissue_number={issue_number}\npr_number={pr_number}\n"
                f"branch_prefix={BRANCH_PREFIX}"
            ),
            idempotency_key=base_idempotency_key,
            cwd=work_dir,
        )
        print(f"Pipeline execution: {result.execution_id}")
        print(f"Monitor at: {server_base}/execution/{result.execution_id}")
        if result.status not in ("COMPLETED", ""):
            result.print_result()
            return 1

    # Deterministic PR finalization — no LLM involved. Calls the same @tool
    # functions the old pr_updater Agent used to invoke via prefill_tools, but
    # directly, so a hallucinating model can't derail this stage.
    print("\n=== Finalizing PR (deterministic, no LLM) ===")
    finalize_summary = finalize_pr_update(
        repo=repo,
        issue_number=issue_number,
        pr_number=pr_number,
        branch_prefix=BRANCH_PREFIX,
    )
    print(finalize_summary)
    validation = validate_pr_result()
    print(validation)

    result_path = _contextbook_dir() / "pr_result.md"
    result_text = (
        result_path.read_text(encoding="utf-8", errors="replace") if result_path.exists() else ""
    )
    match = re.search(r"https://github\.com/\S+/pull/\d+", result_text)
    if match:
        print(f"\nPR ready: {match.group(0)}")
        return 0

    print("\nIssue fixer pipeline completed without a PR URL.")
    print(f"pr_result: {result_path}")
    result.print_result()
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
