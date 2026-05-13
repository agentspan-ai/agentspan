#!/usr/bin/env python3
# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""Issue Fixer Agent (Tech Lead variant): fetch context, design + fan-out, finalize.

Pipeline:
    1. pr_fetcher        -- same as 100_issue_fixer_agent.py: emits Task Brief.
    2. tech_lead         -- reads task_brief + repo_conventions, designs the fix
                            and breaks it into 1..N independent subtasks. Each
                            subtask owns an EXCLUSIVE set of files.
    3. subtask_coders    -- N parallel implementer sub-workflows, one per
                            subtask. The tech lead picks N at runtime.
    4. integrator        -- runs build_check + lint_and_format on the merged
                            workdir; if anything fails, makes minimal fixups.
    5. PR finalization   -- deterministic, no LLM. Same as 100.

Fan-out mechanics — all conductor, no Python orchestration:
    The tech lead is built with ``scatter_gather(worker=subtask_coder, ...)``
    (see 58_scatter_gather.py for the canonical pattern). Internally, that:

      - Wraps ``subtask_coder`` as an ``agent_tool``. ``agent_tool`` is the
        ``tool_type`` that the server's ToolCompiler maps to a
        ``SUB_WORKFLOW`` task (see ToolCompiler.java: ``Map.entry(
        "agent_tool", "SUB_WORKFLOW")``).
      - When the tech lead emits multiple ``subtask_coder`` tool calls in a
        SINGLE assistant turn, agentspan packages them into a Conductor
        ``FORK_JOIN_DYNAMIC`` task. Conductor schedules and waits for all
        sub-workflows in parallel; no Python loop dispatches them.
      - ``retry_count`` / ``retry_delay_seconds`` / ``fail_fast`` propagate
        into the per-branch retry policy of that FORK_JOIN_DYNAMIC.

    There is no for-loop or manual sub-workflow start in this file. Fan-out
    width is decided by the tech lead's prompt (one tool call per subtask)
    and executed entirely by Conductor.

    Why not PLAN_EXECUTE? PAC (``PlanAndCompileTask.java``) compiles every
    plan op as a ``SIMPLE`` task regardless of toolType, so an ``agent_tool``
    op inside a plan would not dispatch a sub-workflow. scatter_gather is
    the conductor-native way to fan out to *agent* sub-workflows today.

Conflict avoidance:
    Each subtask is assigned a NON-OVERLAPPING list of files in the tech
    lead's design. The subtask coder's prompt names the exact files it owns
    and tells it not to touch anything else. If two pieces of work would
    have to share a file, the tech lead is told to merge them into a single
    subtask rather than producing overlapping ones. The integrator stage
    runs after the fan-out join and is the safety net: it runs the
    validation tools and patches any leftover issues before PR finalization.
"""

from __future__ import annotations

import argparse
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
    contextbook_write,
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

from agentspan.agents import (
    Agent,
    AgentRuntime,
    OnFail,
    Position,
    RegexGuardrail,
    Strategy,
    scatter_gather,
)
from agentspan.agents.tool import tool as _tool

BRANCH_PREFIX = "fix/issue-"
SONNET = "anthropic/claude-sonnet-4-6"

FETCHER_MAX_TURNS = 20
TECH_LEAD_MAX_TURNS = 30
SUBTASK_CODER_MAX_TURNS = 60
INTEGRATOR_MAX_TURNS = 30


FETCHER_INSTRUCTIONS = """\
You are the PR/Issue Fetcher.

The fetch and validation tools have already run through prefill_tools. The full
issue/PR dump is available in the prefilled `issue_pr` contextbook section.

Inspect the validation result first.
- If validation FAILED: summarize the failure in plain text and do not output
  FETCH_READY. Do not call write_task_brief.
- If validation PASSED: produce a Task Brief for the Tech Lead using ONLY the
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
Numbered, ordered, concrete steps for the Tech Lead. Each step is a single
actionable change, investigation, or validation. The final step must be a
validation step (build_check and/or lint_and_format).

Workflow:
1. Call write_task_brief(content=<the brief>) exactly once with the brief in
   the format above.
2. After write_task_brief succeeds, emit one final response whose body is the
   same brief text followed by a final line containing exactly FETCH_READY.
   Do not include any tool calls in that final response.
"""


TECH_LEAD_INSTRUCTIONS = """\
You are the Tech Lead.

You have the Task Brief from the fetcher in the prefilled `task_brief`
contextbook section, plus `issue_pr` and `repo_conventions`. Your job is to:

1. UNDERSTAND the change. Use the inspection tools (read_file, grep_search,
   read_symbol, file_outline, glob_find, search_symbols) to look at the code
   that needs to change. Investigate enough to understand the scope — do not
   try to write the fix yourself.

2. DESIGN the fix. Decide what should change at the file level. Write a short
   design to the `design` contextbook section using ``write_design`` with
   these headings:
     - ## Overview          (2-4 sentences)
     - ## Affected files    (bullet list of every file that will be touched
                             with one line of "why")
     - ## Approach          (numbered, concrete steps at the design level)

3. BREAK DOWN the work into 1..N subtasks. Each subtask must:
     - Touch a NON-OVERLAPPING set of files. NEVER assign the same file to
       two subtasks. If two pieces of work would share a file, MERGE them
       into a single subtask.
     - Be independently implementable from the task brief + the design.
     - Be small enough that one coder can finish it in a handful of edits.

4. FAN OUT. Call the ``subtask_coder`` tool ONCE PER SUBTASK in a SINGLE
   response (all calls in the same assistant turn) so they run in parallel.
   Each call's ``request`` argument MUST be a self-contained prompt that
   includes:
     - The subtask id (1..N) and title.
     - The exact list of files the subtask owns (verbatim). Tell the coder
       to ONLY edit those files.
     - The acceptance criteria for that subtask.
     - A short pointer to the design section if the coder needs more context.

5. SYNTHESIZE. After all subtask_coder results return, write a brief summary
   to ``write_techlead_summary`` covering: which subtasks succeeded, any that
   reported blockers, and the integrated state of the fix.

6. Emit one final response whose last line is exactly TECHLEAD_DONE.

Conflict-avoidance rule (hard): the union of files across subtasks must have
no duplicates. If you find yourself wanting to assign the same file twice,
restructure into a single combined subtask. The integrator stage that runs
after you cannot rescue overlapping edits cleanly.
"""


SUBTASK_CODER_INSTRUCTIONS = """\
You are a Subtask Coder. The Tech Lead has decomposed a larger fix into
independent subtasks and dispatched you with exactly ONE of them.

Your incoming request describes:
  - subtask id + title
  - the EXACT list of files you own — you may ONLY edit those files
  - acceptance criteria
  - a pointer to the design section in the contextbook

Strict rules:
  1. Read ONLY the files listed in your subtask plus anything in the
     contextbook (issue_pr, task_brief, design, repo_conventions). Use the
     inspection tools (read_file, read_symbol, grep_search, file_outline,
     glob_find, search_symbols) to understand what needs to change.
  2. Make focused edits ONLY to files in your assigned list. Do not touch
     any file outside that list. If you discover you need to edit a file
     outside your list, STOP and return a clear blocker via
     write_implementation_report — do not silently expand scope.
  3. After your edits, run build_check and/or lint_and_format on the
     affected paths. Fix lint/build failures in your owned files only.
  4. Call write_coder_context with a short checklist showing what you did
     and the validation result.
  5. Call write_implementation_report with files changed, validations run,
     and any remaining concerns or blockers.
  6. Emit one final response whose last line is exactly CODER_DONE.

Do not commit, push, or create a PR — the pipeline's integrator and
finalizer handle those.
"""


INTEGRATOR_INSTRUCTIONS = """\
You are the Integrator. The Tech Lead has fanned out N coders that each
edited a disjoint set of files in the shared workdir. Your job is small and
mechanical:

1. Run ``git_status`` and ``git_diff`` to inspect what changed.
2. Run ``build_check`` and ``lint_and_format``. If both pass, you are done.
3. If validation FAILS, make the minimum edits to fix it. Common cases:
   - Lint/format errors a coder left behind in a file they owned.
   - Cross-file integration issues (a rename in one subtask not reflected
     in another). Pick the change that respects the design section and
     correct the other side.
4. Re-run build_check and lint_and_format until both pass OR you cannot
   make further progress without changing scope.
5. Call write_coder_context with a one-paragraph integration summary plus a
   final pass/fail line.
6. Emit one final response whose last line is exactly INTEGRATION_DONE.

You may NOT redesign or expand scope. If the build is broken in a way that
requires new design decisions, stop and explain that in write_coder_context.
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
_STALLED_BLOCKED_THRESHOLD = 15
_PROGRESS_MARKERS = (
    "write_coder_context",
    "write_implementation_report",
    "write_design",
    "write_techlead_summary",
)
_PROGRESS_DISCOUNT = 5


def _budget_blocked(result: object) -> bool:
    text = str(result or "")
    return (
        _BLOCKED_TOKEN in text
        or "Blocked: validation budget exceeded" in text
        or "implementation_report is blocked" in text
    )


def _count_blocked_tool_messages(messages: object) -> int:
    if not isinstance(messages, list):
        return 0
    blocked = 0
    progress = 0
    for m in messages:
        if not isinstance(m, dict):
            continue
        role = m.get("role")
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


def _tech_lead_done(context: dict, **kwargs) -> bool:
    if _budget_blocked(_stop_result(context, kwargs)):
        return True
    messages = None
    if isinstance(context, dict):
        messages = context.get("messages")
    if messages is None:
        messages = kwargs.get("messages")
    if _count_blocked_tool_messages(messages) >= _STALLED_BLOCKED_THRESHOLD:
        return True
    return _contextbook_written("design") and _result_contains(
        _stop_result(context, kwargs), "TECHLEAD_DONE"
    )


def _integrator_done(context: dict, **kwargs) -> bool:
    if _budget_blocked(_stop_result(context, kwargs)):
        return True
    messages = None
    if isinstance(context, dict):
        messages = context.get("messages")
    if messages is None:
        messages = kwargs.get("messages")
    if _count_blocked_tool_messages(messages) >= _STALLED_BLOCKED_THRESHOLD:
        return True
    return _result_contains(_stop_result(context, kwargs), "INTEGRATION_DONE")


# Per-stage contextbook writers. The tech lead writes the structured design
# to the ``design`` section; the integrator reuses ``coder_context`` for its
# own status line. Binding sections via a tiny helper matches the pattern in
# _issue_fixer_tools.py.


@_tool(name="write_design", stateful=True, max_calls=2)
def write_design(content: str, append: bool = False) -> str:
    """Write the tech lead's design + subtask breakdown to the 'design' section.

    Content must include '## Overview', '## Affected files', '## Approach',
    and a '## Subtasks' section listing the disjoint subtasks the tech lead
    will fan out. append=False replaces the section.
    """
    return contextbook_write("design", content, append)


@_tool(name="write_techlead_summary", stateful=True, max_calls=2)
def write_techlead_summary(content: str, append: bool = False) -> str:
    """Write the tech lead's post-fanout synthesis to the 'design' section.

    Use append=True to add the synthesis under the existing design block.
    """
    return contextbook_write("design", content, append=True)


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
        description="Issue Fixer Agent (Tech Lead variant): fetch, design, fan-out, PR",
        epilog=(
            "Examples:\n"
            "  python 105_issue_fixer_techlead.py facebook/react 42\n"
            "  python 105_issue_fixer_techlead.py facebook/react 42 --pr 157\n"
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
    base_idempotency_key = f"issue-fixer-techlead-v1-{repo_slug}-issue-{issue_number}" + (
        f"-pr-{pr_number}" if pr_number else ""
    )
    work_dir = _workspace_dir_for_key(base_idempotency_key)
    os.makedirs(work_dir, exist_ok=True)
    set_working_dir(work_dir)

    # ── 1. PR/Issue fetcher ─────────────────────────────────────────────
    pr_fetcher = Agent(
        name="techlead_pr_fetcher",
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

    # ── 2a. Subtask coder (worker for scatter_gather) ───────────────────
    subtask_coder = Agent(
        name="techlead_subtask_coder",
        model=SONNET,
        stateful=True,
        reasoning_effort="medium",
        max_turns=SUBTASK_CODER_MAX_TURNS,
        max_tokens=32000,
        prefill_tools=[
            contextbook_read.call(section="task_brief"),
            contextbook_read.call(section="design"),
            contextbook_read.call(section="repo_conventions"),
            list_directory.call(),
            git_status.call(),
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
        instructions=SUBTASK_CODER_INSTRUCTIONS,
    )

    # ── 2b. Tech Lead — scatter_gather coordinator over subtask_coder ───
    # This is THE fan-out boundary. scatter_gather wraps subtask_coder as an
    # ``agent_tool`` (toolType → SUB_WORKFLOW per ToolCompiler.java) and gives
    # the tech lead that tool. When the tech lead emits multiple
    # ``subtask_coder`` tool calls in one assistant turn, agentspan compiles
    # them into a Conductor ``FORK_JOIN_DYNAMIC`` task — each subtask runs
    # as its own parallel sub-workflow with the retry policy below. There is
    # no Python-side dispatch loop; Conductor owns the parallelism.
    # scatter_gather forwards **kwargs to the Agent constructor, so
    # prefill_tools / stop_when / stateful all pass through.
    tech_lead = scatter_gather(
        name="techlead",
        worker=subtask_coder,
        model=SONNET,
        instructions=TECH_LEAD_INSTRUCTIONS,
        tools=[
            read_file,
            read_symbol,
            grep_search,
            glob_find,
            file_outline,
            search_symbols,
            write_design,
            write_techlead_summary,
        ],
        # Sub-task durability: 2 retries on transient failures. Don't fail
        # fast — if one subtask permanently fails the tech lead can still
        # synthesize and the integrator stage will pick up the slack.
        retry_count=2,
        retry_delay_seconds=3,
        fail_fast=False,
        max_turns=TECH_LEAD_MAX_TURNS,
        max_tokens=32000,
        # 15 minutes — N parallel subtask coders each doing real work
        timeout_seconds=900,
        stateful=True,
        stop_when=_tech_lead_done,
        prefill_tools=[
            contextbook_read.call(section="issue_pr"),
            contextbook_read.call(section="task_brief"),
            contextbook_read.call(section="repo_conventions"),
            list_directory.call(),
            git_status.call(),
        ],
    )

    # ── 3. Integrator ──────────────────────────────────────────────────
    integrator = Agent(
        name="techlead_integrator",
        model=SONNET,
        stateful=True,
        max_turns=INTEGRATOR_MAX_TURNS,
        max_tokens=32000,
        prefill_tools=[
            contextbook_read.call(section="design"),
            git_status.call(),
            git_diff.call(),
        ],
        tools=[
            read_file,
            read_symbol,
            grep_search,
            glob_find,
            file_outline,
            edit_file,
            edit_files,
            apply_patch,
            lint_and_format,
            build_check,
            write_coder_context,
        ],
        stop_when=_integrator_done,
        instructions=INTEGRATOR_INSTRUCTIONS,
    )

    # ── Pipeline: fetcher → tech_lead (designs + fans out) → integrator ─
    pipeline = Agent(
        name="issue_fixer_techlead_pipeline",
        model=SONNET,
        stateful=True,
        agents=[pr_fetcher, tech_lead, integrator],
        strategy=Strategy.SEQUENTIAL,
        timeout_seconds=0,
        instructions=(
            "Run the issue fixer (tech-lead variant) in order: fetcher, then "
            "tech lead (which fans out parallel coders), then integrator. "
            "Do not skip stages. PR finalization happens deterministically "
            "after this pipeline returns and is not an agent stage."
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
        print("\n=== Running issue_fixer_techlead_pipeline ===")
        print("    fetcher -> tech_lead (fan-out) -> integrator")
        _begin_round()
        result = rt.run(
            pipeline,
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

    # ── 4. Deterministic PR finalization (no LLM) ──────────────────────
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

    print("\nIssue fixer (tech-lead) pipeline completed without a PR URL.")
    print(f"pr_result: {result_path}")
    result.print_result()
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
