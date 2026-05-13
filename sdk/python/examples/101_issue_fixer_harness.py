#!/usr/bin/env python3
# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""Issue-fixer pipeline on the new HarnessRuntime.

This is the v1 demonstrator for the coding-agent harness. The harness
session is an agentspan ``Agent`` execution; tools run as Conductor SIMPLE
tasks under permission / sandbox / hook checks applied in-process.

  * Tool registry: read_file, list_files, search_text, write_file,
    patch_file, shell, update_plan, structured_output.
  * Sandbox: ChecksOnlySandbox restricting writes to the working dir,
    blocking private network URLs, allowlisting only ``git`` / ``gh`` /
    ``find`` shell commands.
  * Permissions: explicit ``allow`` rules for the tools this agent is
    expected to need; everything else falls through to the default
    deny-side-effects-by-default policy.
  * LLM: handled by Conductor's ``LLM_CHAT_COMPLETE`` task with per-user
    credentials from the agentspan credential vault. Set the model with
    the ``provider/model`` syntax, e.g. ``anthropic/claude-sonnet-4-6``.

Usage:
    python 101_issue_fixer_harness.py owner/repo 42
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
import tempfile

from agentspan.harness import HarnessConfig, HarnessRuntime
from agentspan.harness.permission import (
    PermissionEngine,
    PermissionRule,
    RuleSource,
)
from agentspan.harness.sandbox import ChecksOnlySandbox
from agentspan.harness.tools.builtins import (
    DeleteFile,
    ListFiles,
    PatchFile,
    ReadFile,
    SearchText,
    Shell,
    StopTask,
    StructuredOutput,
    UpdatePlan,
    WriteFile,
)


SYSTEM_PROMPT = """\
You are a coding agent fixing GitHub issues.

Tools available: read_file, list_files, search_text, write_file, patch_file,
delete_file, shell, update_plan, structured_output.

Process:
1. Inspect the repository with read_file / list_files / search_text.
2. Use update_plan to record the steps you intend to take.
3. Make focused edits with patch_file (preferred) or write_file.
4. Run tests with the shell tool. Only `git`, `gh`, and `find` are allowed.
5. When done, call structured_output with {"status": "complete", "summary": ...}.

Stay on task. Edit only files relevant to the issue. Don't add features beyond
what the issue asks for.
"""


def _build_runtime(*, repo: str, issue: int, work_dir: str) -> HarnessRuntime:
    sandbox = ChecksOnlySandbox(
        allowed_read_roots=[work_dir],
        allowed_write_roots=[work_dir],
        allowed_commands=["git", "gh", "find"],
        block_private_networks=True,
    )

    rules = [
        PermissionRule(source=RuleSource.PROJECT, behavior="allow", tool_name=name)
        for name in (
            "read_file", "list_files", "search_text",
            "update_plan", "structured_output",
            "write_file", "patch_file", "delete_file",
            "shell", "stop_task",
        )
    ]

    config = HarnessConfig(
        model=os.environ.get("AGENTSPAN_HARNESS_MODEL", "anthropic/claude-sonnet-4-6"),
        tools=[
            ReadFile(), ListFiles(), SearchText(),
            WriteFile(), PatchFile(), DeleteFile(),
            Shell(), StopTask(),
            UpdatePlan(), StructuredOutput(),
        ],
        cwd=work_dir,
        sandbox=sandbox,
        permission_engine=PermissionEngine(rules=rules),
        system=SYSTEM_PROMPT,
        max_turns=409,
        max_tokens=32000,
    )
    return HarnessRuntime(config)


async def _run(repo: str, issue: int) -> int:
    repo_slug = repo.replace("/", "-")
    work_dir = os.path.join(
        tempfile.gettempdir(), f"{repo_slug}-fix-issue-{issue}"
    )
    os.makedirs(work_dir, exist_ok=True)

    prompt = (
        f"Fix issue #{issue} in {repo}. The repo is checked out at {work_dir}. "
        f"When you're done, call structured_output with the summary."
    )

    rt = _build_runtime(repo=repo, issue=issue, work_dir=work_dir)
    print(f"session: {rt.session_id}")

    try:
        async for event in rt.submit(prompt):
            etype = getattr(event, "type", "?")
            text = getattr(event, "content", None)
            tool_name = getattr(event, "tool_name", None)
            if etype == "message" and text:
                print(f"[message] {text[:200]}")
            elif etype == "tool_call" and tool_name:
                print(f"[tool_call] {tool_name}({getattr(event, 'args', {})})")
            elif etype == "done":
                print(f"[done] {getattr(event, 'output', '')}")
            elif etype == "error":
                print(f"[error] {text}")
    finally:
        if rt.last_execution_id:
            print(f"execution: {rt.last_execution_id}")
        rt.close()

    structured = rt.session_store.get("structured_output")
    if structured:
        print(f"structured: {structured}")
    return 0


def main() -> int:
    p = argparse.ArgumentParser(description="Issue fixer on HarnessRuntime")
    p.add_argument("repo", help="GitHub repo (owner/name)")
    p.add_argument("issue", type=int, help="Issue number")
    args = p.parse_args()
    return asyncio.run(_run(args.repo, args.issue))


if __name__ == "__main__":
    sys.exit(main())
