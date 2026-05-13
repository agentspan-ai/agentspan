# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""GitHub primitives: ``setup_repo``, ``fetch_issue``, ``fetch_pr``, ``open_pr``.

All four shell out to the ``gh`` CLI (which the user is expected to have
authenticated). They're convenience tools — the underlying operations
could equally be done via the generic ``shell`` tool, but bundling them
saves the model multi-step orchestration and gives stable structured
results.

Sandbox is bypassed deliberately for ``gh``: the user opted in by adding
this tool to the harness. The sandbox still gates path writes for
``setup_repo``'s clone target.
"""

from __future__ import annotations

import asyncio
import json
import os
import shutil
from typing import Any, Callable, Dict, Optional

from ..contract import Tool, ToolResult, ToolUseContext


async def _run(args, *, cwd=None, env=None) -> "tuple[int, str, str]":
    proc = await asyncio.create_subprocess_exec(
        *args,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        cwd=cwd,
        env=env,
    )
    out, err = await proc.communicate()
    return (
        proc.returncode or 0,
        out.decode("utf-8", errors="replace"),
        err.decode("utf-8", errors="replace"),
    )


def _gh_path() -> Optional[str]:
    return shutil.which("gh")


def _git_path() -> Optional[str]:
    return shutil.which("git")


# ── setup_repo ─────────────────────────────────────────────────────────


class SetupRepo(Tool[Dict[str, Any], Dict[str, Any]]):
    @property
    def name(self) -> str:
        return "setup_repo"

    @property
    def description(self) -> str:
        return (
            "Clone (or update) a GitHub repo into the workspace and check out "
            "a working branch. If the directory already exists, fetches and "
            "switches to the branch instead of re-cloning. Idempotent — safe "
            "to call across resumes."
        )

    @property
    def input_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "repo": {"type": "string", "description": "owner/name"},
                "directory": {
                    "type": "string",
                    "description": "Absolute or session-relative directory to clone into.",
                },
                "branch": {
                    "type": "string",
                    "description": "Working branch name. Created from base if needed.",
                },
                "base": {"type": "string", "description": "Base branch (default 'main')."},
                "pr_number": {
                    "type": "integer",
                    "description": "If set, checks out the PR branch instead of creating one.",
                },
            },
            "required": ["repo", "directory"],
        }

    def is_read_only(self, input: Dict[str, Any]) -> bool:
        return False

    def is_concurrency_safe(self, input: Dict[str, Any]) -> bool:
        return False

    def is_open_world(self, input: Dict[str, Any]) -> bool:
        return True

    async def call(self, input, context, parent_message=None, on_progress=None):
        gh, git = _gh_path(), _git_path()
        if not gh or not git:
            return ToolResult.error("gh and git CLIs must be on PATH")

        repo = input["repo"]
        directory = input["directory"]
        if not os.path.isabs(directory):
            directory = os.path.normpath(os.path.join(context.cwd, directory))
        base = input.get("base", "main")
        branch = input.get("branch")
        pr_number = input.get("pr_number")

        sandbox = context.store.get("sandbox")
        if sandbox is not None:
            check = sandbox.check_path_write(directory)
            if not check.allowed:
                return ToolResult.error(f"sandbox: {check.reason}")

        # Clone if missing.
        if not os.path.isdir(os.path.join(directory, ".git")):
            os.makedirs(os.path.dirname(directory) or ".", exist_ok=True)
            code, out, err = await _run([gh, "repo", "clone", repo, directory])
            if code != 0:
                return ToolResult.error(f"clone failed: {err.strip() or out.strip()}")

        # Update.
        for cmd in (
            [git, "fetch", "--all", "--prune"],
        ):
            code, _out, err = await _run(cmd, cwd=directory)
            if code != 0:
                return ToolResult.error(f"git fetch failed: {err.strip()}")

        if pr_number is not None:
            code, _out, err = await _run(
                [gh, "pr", "checkout", str(pr_number)], cwd=directory
            )
            if code != 0:
                return ToolResult.error(f"gh pr checkout failed: {err.strip()}")
        elif branch:
            # Create-or-checkout.
            code, _out, _err = await _run(
                [git, "rev-parse", "--verify", branch], cwd=directory
            )
            if code == 0:
                await _run([git, "checkout", branch], cwd=directory)
            else:
                # Create from base.
                await _run([git, "checkout", base], cwd=directory)
                code, _out, err = await _run(
                    [git, "checkout", "-b", branch], cwd=directory
                )
                if code != 0:
                    return ToolResult.error(f"branch create failed: {err.strip()}")

        return ToolResult.ok(
            content=f"Workspace ready at {directory}",
            output={
                "directory": directory,
                "repo": repo,
                "branch": branch,
                "pr_number": pr_number,
            },
        )


# ── fetch_issue / fetch_pr ─────────────────────────────────────────────


class FetchIssue(Tool[Dict[str, Any], Dict[str, Any]]):
    @property
    def name(self) -> str:
        return "fetch_issue"

    @property
    def description(self) -> str:
        return (
            "Fetch a GitHub issue's title, body, labels, and comments via gh. "
            "Returns structured JSON for programmatic use plus a human summary."
        )

    @property
    def input_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "repo": {"type": "string"},
                "issue_number": {"type": "integer"},
            },
            "required": ["repo", "issue_number"],
        }

    def is_read_only(self, input: Dict[str, Any]) -> bool:
        return True

    def is_concurrency_safe(self, input: Dict[str, Any]) -> bool:
        return True

    def is_open_world(self, input: Dict[str, Any]) -> bool:
        return True

    async def call(self, input, context, parent_message=None, on_progress=None):
        gh = _gh_path()
        if not gh:
            return ToolResult.error("gh CLI must be on PATH")
        repo = input["repo"]
        num = int(input["issue_number"])
        code, out, err = await _run([
            gh, "issue", "view", str(num),
            "--repo", repo,
            "--json", "title,body,labels,comments,state,url,author",
        ])
        if code != 0:
            return ToolResult.error(f"gh issue view failed: {err.strip() or out.strip()}")
        try:
            data = json.loads(out)
        except Exception as exc:  # noqa: BLE001
            return ToolResult.error(f"gh returned non-JSON: {exc}")
        summary = (
            f"#{num} {data.get('title', '').strip()}\n"
            f"State: {data.get('state')} URL: {data.get('url')}\n\n"
            f"{(data.get('body') or '').strip()[:4000]}"
        )
        return ToolResult.ok(content=summary, output=data)


class FetchPR(Tool[Dict[str, Any], Dict[str, Any]]):
    @property
    def name(self) -> str:
        return "fetch_pr"

    @property
    def description(self) -> str:
        return (
            "Fetch a GitHub PR's title, body, files, comments, review comments. "
            "Useful for 'address feedback on PR #N' workflows."
        )

    @property
    def input_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "repo": {"type": "string"},
                "pr_number": {"type": "integer"},
            },
            "required": ["repo", "pr_number"],
        }

    def is_read_only(self, input: Dict[str, Any]) -> bool:
        return True

    def is_concurrency_safe(self, input: Dict[str, Any]) -> bool:
        return True

    def is_open_world(self, input: Dict[str, Any]) -> bool:
        return True

    async def call(self, input, context, parent_message=None, on_progress=None):
        gh = _gh_path()
        if not gh:
            return ToolResult.error("gh CLI must be on PATH")
        repo = input["repo"]
        num = int(input["pr_number"])
        code, out, err = await _run([
            gh, "pr", "view", str(num),
            "--repo", repo,
            "--json", "title,body,state,headRefName,baseRefName,url,files,comments,reviews",
        ])
        if code != 0:
            return ToolResult.error(f"gh pr view failed: {err.strip() or out.strip()}")
        try:
            data = json.loads(out)
        except Exception as exc:  # noqa: BLE001
            return ToolResult.error(f"gh returned non-JSON: {exc}")
        summary = (
            f"#{num} {data.get('title', '').strip()}\n"
            f"State: {data.get('state')} {data.get('headRefName')} → {data.get('baseRefName')}\n"
            f"URL: {data.get('url')}\n\n"
            f"{(data.get('body') or '').strip()[:4000]}"
        )
        return ToolResult.ok(content=summary, output=data)


# ── open_pr ────────────────────────────────────────────────────────────


class OpenPR(Tool[Dict[str, Any], Dict[str, Any]]):
    @property
    def name(self) -> str:
        return "open_pr"

    @property
    def description(self) -> str:
        return (
            "Open a pull request from the current branch via gh. The branch "
            "must already be pushed (this tool will push if needed). Returns "
            "the PR URL and number."
        )

    @property
    def input_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "title": {"type": "string"},
                "body": {"type": "string"},
                "base": {"type": "string", "description": "Base branch (default 'main')."},
                "draft": {"type": "boolean"},
                "directory": {
                    "type": "string",
                    "description": "Repo directory; defaults to session cwd.",
                },
            },
            "required": ["title", "body"],
        }

    def is_read_only(self, input: Dict[str, Any]) -> bool:
        return False

    def is_destructive(self, input: Dict[str, Any]) -> bool:
        return False

    def is_concurrency_safe(self, input: Dict[str, Any]) -> bool:
        return False

    def is_open_world(self, input: Dict[str, Any]) -> bool:
        return True

    async def call(self, input, context, parent_message=None, on_progress=None):
        gh, git = _gh_path(), _git_path()
        if not gh or not git:
            return ToolResult.error("gh and git CLIs must be on PATH")

        cwd = input.get("directory") or context.cwd
        if not os.path.isabs(cwd):
            cwd = os.path.normpath(os.path.join(context.cwd, cwd))
        if not os.path.isdir(os.path.join(cwd, ".git")):
            return ToolResult.error(f"not a git repo: {cwd}")

        # Make sure HEAD is pushed.
        code, out, err = await _run([git, "rev-parse", "--abbrev-ref", "HEAD"], cwd=cwd)
        if code != 0:
            return ToolResult.error(f"rev-parse HEAD failed: {err.strip()}")
        branch = out.strip()
        await _run([git, "push", "-u", "origin", branch], cwd=cwd)

        args = [
            gh, "pr", "create",
            "--title", input["title"],
            "--body", input["body"],
            "--head", branch,
        ]
        if "base" in input:
            args.extend(["--base", input["base"]])
        if input.get("draft"):
            args.append("--draft")
        code, out, err = await _run(args, cwd=cwd)
        if code != 0:
            return ToolResult.error(f"gh pr create failed: {err.strip() or out.strip()}")
        url = out.strip().splitlines()[-1] if out.strip() else ""
        return ToolResult.ok(
            content=f"PR opened: {url}",
            output={"url": url, "branch": branch},
        )
