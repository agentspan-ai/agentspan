#!/usr/bin/env python3
"""GitHub Repo URL -> Issue -> PR Agent.

This agent takes a GitHub repository URL, clones the codebase locally,
analyzes the source and test layout, inspects open GitHub issues, chooses
one high-likelihood bug/feature request, implements the fix, validates it,
and opens a pull request plus a follow-up issue comment.

The GitHub account that publishes the PR/comment is controlled by the
stored ``GITHUB_TOKEN`` credential resolved by AgentSpan. By default this
agent expects that token to belong to the ``agentspan`` user.

Usage:
    python repo_url_issue_pr_agent.py https://github.com/pytest-dev/pytest-asyncio
    python repo_url_issue_pr_agent.py https://github.com/pytest-dev/pytest-asyncio --issue 1334
    AGENTSPAN_DRY_RUN=true python repo_url_issue_pr_agent.py https://github.com/pytest-dev/pytest-asyncio
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import tempfile
from pathlib import Path
from urllib.parse import quote, urlparse

SDK_SRC = Path(__file__).resolve().parents[1] / "src"
if SDK_SRC.exists():
    sys.path.insert(0, str(SDK_SRC))

from agentspan.agents import Agent, AgentRuntime, Strategy, tool
from agentspan.agents.gate import TextGate
from agentspan.agents.handoff import OnTextMention

import repo_url_issue_pr_shared as shared
from repo_url_issue_pr_shared import (
    RepoProfile,
    cleanup_workspace,
    create_workspace,
    get_model,
    get_server_url,
    is_draft_pr,
    is_dry_run,
    is_review_branch_only,
)


def run_cmd(*args, **kwargs):
    """Delegate through `_shared` so tests can patch either import path."""
    return shared.run_cmd(*args, **kwargs)


def normalize_repo_input(repo_url: str) -> str:
    """Convert common GitHub URL formats into `owner/repo`."""
    repo_url = repo_url.strip()
    if not repo_url:
        raise ValueError("Repository input cannot be empty")

    if re.fullmatch(r"[\w.-]+/[\w.-]+", repo_url):
        return repo_url

    ssh_match = re.fullmatch(r"git@github\.com:([\w.-]+/[\w.-]+?)(?:\.git)?", repo_url)
    if ssh_match:
        return ssh_match.group(1)

    parsed = urlparse(repo_url)
    if parsed.netloc not in ("github.com", "www.github.com"):
        raise ValueError("Only github.com repositories are supported")

    path = parsed.path.strip("/")
    if path.endswith(".git"):
        path = path[:-4]

    parts = [part for part in path.split("/") if part]
    if len(parts) < 2:
        raise ValueError("Repository URL must include owner and repo")
    return f"{parts[0]}/{parts[1]}"


def slugify_branch_value(text: str, *, limit: int = 40) -> str:
    """Convert an issue title into a safe branch suffix."""
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    slug = re.sub(r"-{2,}", "-", slug)
    return slug[:limit].rstrip("-") or "issue"


def expected_github_login() -> str:
    return os.environ.get("AGENTSPAN_GITHUB_USER", "agentspan")


def git_identity() -> tuple[str, str]:
    git_user = os.environ.get("AGENTSPAN_GIT_USER", "AgentSpan")
    git_email = os.environ.get(
        "AGENTSPAN_GIT_EMAIL",
        f"{expected_github_login()}@users.noreply.github.com",
    )
    return git_user, git_email


def publication_mode_label() -> str:
    if is_dry_run():
        return "dry_run"
    if is_review_branch_only():
        return "review_branch"
    return "live_pr"


def stage_max_tokens(default: int = 12000) -> int:
    """Per-stage completion cap tuned to stay under common model limits."""
    raw = os.environ.get("AGENTSPAN_AGENT_MAX_TOKENS", "").strip()
    if not raw:
        return default
    try:
        value = int(raw)
    except ValueError:
        return default
    return max(512, min(value, 16000))


def stage_timeout_seconds(live_default: int, dry_run_default: int | None = None) -> int:
    """Stage timeout tuned for live runs, with faster defaults for dry runs."""
    raw = os.environ.get("AGENTSPAN_AGENT_STAGE_TIMEOUT", "").strip()
    if raw:
        try:
            value = int(raw)
        except ValueError:
            value = 0
        if value > 0:
            return value
    if is_dry_run() and dry_run_default is not None:
        return dry_run_default
    return live_default


def runtime_timeout_seconds(
    default_live: int = 7200, default_dry_run: int = 1800
) -> int:
    """Top-level runtime timeout in seconds."""
    raw = os.environ.get("AGENTSPAN_AGENT_TIMEOUT", "").strip()
    if raw:
        try:
            value = int(raw)
        except ValueError:
            value = 0
        if value > 0:
            return value
    return default_dry_run if is_dry_run() else default_live


def local_exec_file_commands() -> list[str]:
    """Common workspace-safe file operations used during repo analysis and fixes."""
    return ["cp", "mkdir", "mv", "pwd", "rm", "touch"]


def local_exec_shell_helpers() -> list[str]:
    """Common read-only shell helpers used in repo inspection pipelines."""
    return [
        "awk",
        "basename",
        "cd",
        "cut",
        "dirname",
        "env",
        "realpath",
        "tr",
        "which",
        "xargs",
    ]


def github_token() -> str:
    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    if token:
        return token
    raise RuntimeError(
        "Missing GITHUB_TOKEN credential. Store it with: agentspan credentials set GITHUB_TOKEN <token>"
    )


def github_env() -> dict[str, str]:
    env = os.environ.copy()
    token = env.get("GITHUB_TOKEN") or env.get("GH_TOKEN")
    if token:
        env.setdefault("GITHUB_TOKEN", token)
        env.setdefault("GH_TOKEN", token)
    env.setdefault("GIT_TERMINAL_PROMPT", "0")
    env.setdefault("GH_PROMPT_DISABLED", "1")
    return env


def run_github_cmd(cmd: list[str], **kwargs):
    """Run a GitHub-facing command with token-backed env and prompts disabled."""
    return run_cmd(cmd, env=github_env(), **kwargs)


def credentialed_remote_url(login: str, repo_name: str) -> str:
    token = quote(github_token(), safe="")
    return f"https://x-access-token:{token}@github.com/{login}/{repo_name}.git"


def fork_branch_url(login: str, repo: str, branch: str) -> str:
    repo_name = repo.split("/", 1)[1]
    return f"https://github.com/{login}/{repo_name}/tree/{quote(branch, safe='')}"


def fork_commit_url(login: str, repo: str, commit_sha: str) -> str:
    repo_name = repo.split("/", 1)[1]
    return f"https://github.com/{login}/{repo_name}/commit/{quote(commit_sha, safe='')}"


def current_github_login() -> str:
    result = run_github_cmd(["gh", "api", "user", "--jq", ".login"], timeout=15)
    if result.returncode != 0:
        raise RuntimeError(
            result.stderr[:500] or "Unable to determine GitHub user from GITHUB_TOKEN"
        )
    return (result.stdout or "").strip()


def _workdir_looks_like_placeholder(workdir: str) -> bool:
    if not workdir:
        return True
    stripped = workdir.strip()
    return stripped in {"...", "<path>", "/path/to/repo"} or stripped.startswith(
        "/path/to/"
    )


def _git_dir_exists(path: str) -> bool:
    return (
        bool(path) and os.path.isdir(path) and os.path.isdir(os.path.join(path, ".git"))
    )


def _workspace_matches_repo(candidate: Path, repo: str) -> bool:
    if not repo:
        return True
    remote = run_cmd(
        ["git", "-C", str(candidate), "config", "--get", "remote.origin.url"],
        timeout=10,
    )
    if remote.returncode != 0:
        return False
    remote_url = (remote.stdout or "").strip().lower()
    normalized = repo.lower()
    return normalized in remote_url or f"{normalized}.git" in remote_url


def resolve_workdir(workdir: str, repo: str = "") -> str:
    """Resolve a real cloned repo path, recovering from placeholder paths."""
    if _git_dir_exists(workdir):
        return workdir

    temp_root = Path(tempfile.gettempdir())
    candidates: list[Path] = []
    for candidate in temp_root.glob("agentspan_*"):
        if not candidate.is_dir() or not (candidate / ".git").is_dir():
            continue
        if repo and not _workspace_matches_repo(candidate, repo):
            continue
        candidates.append(candidate)

    if candidates:
        candidates.sort(key=lambda path: path.stat().st_mtime, reverse=True)
        return str(candidates[0])

    hint = f" matching repo '{repo}'" if repo else ""
    if _workdir_looks_like_placeholder(workdir):
        raise RuntimeError(
            f"Could not resolve a cloned workspace{hint}; got placeholder path '{workdir}'."
        )
    raise RuntimeError(
        f"Working directory '{workdir}' does not exist and no fallback workspace was found{hint}."
    )


def ensure_fork_remote(repo: str, workdir: str, remote_name: str, login: str) -> None:
    """Ensure a fork remote exists and uses the current token for git pushes."""
    remotes = run_cmd(["git", "-C", workdir, "remote"], env=github_env(), timeout=10)
    remote_names = set(remotes.stdout.split()) if remotes.returncode == 0 else set()

    fork = run_cmd(
        ["gh", "repo", "fork", repo, "--clone=false"],
        env=github_env(),
        cwd=workdir,
        timeout=120,
    )
    repo_name = repo.split("/", 1)[1]
    remote_url = credentialed_remote_url(login, repo_name)

    if remote_name in remote_names:
        set_url = run_cmd(
            ["git", "-C", workdir, "remote", "set-url", remote_name, remote_url],
            env=github_env(),
            timeout=15,
        )
        if set_url.returncode != 0:
            raise RuntimeError(set_url.stderr[:500] or "Unable to update fork remote")
        return

    fork_output = f"{fork.stdout}\n{fork.stderr}".lower()
    if (
        fork.returncode != 0
        and "already exists" not in fork_output
        and "name already exists" not in fork_output
    ):
        raise RuntimeError(
            fork.stderr[:500] or "Unable to create fork for authenticated token owner"
        )

    add = run_cmd(
        ["git", "-C", workdir, "remote", "add", remote_name, remote_url],
        env=github_env(),
        timeout=15,
    )
    if add.returncode != 0:
        raise RuntimeError(add.stderr[:500] or "Unable to add fork remote")


@tool(credentials=["GITHUB_TOKEN"])
def prepare_repo_workspace(repo_url: str) -> dict:
    """Normalize a GitHub repo URL, clone it locally, and detect the repo profile."""
    try:
        repo = normalize_repo_input(repo_url)
    except ValueError as exc:
        return {"error": str(exc), "repo_url": repo_url}

    workdir = create_workspace(prefix=f"agentspan_{repo.replace('/', '_')}_")

    view = run_github_cmd(
        ["gh", "repo", "view", repo, "--json", "nameWithOwner,url,defaultBranchRef"],
        timeout=30,
    )
    if view.returncode != 0:
        cleanup_workspace(workdir)
        return {"error": view.stderr[:500], "repo": repo}

    try:
        info = json.loads(view.stdout)
    except json.JSONDecodeError:
        cleanup_workspace(workdir)
        return {"error": "Failed to parse repo metadata", "repo": repo}

    clone = run_github_cmd(
        ["gh", "repo", "clone", repo, workdir, "--", "--depth", "1"],
        timeout=300,
    )
    if clone.returncode != 0:
        cleanup_workspace(workdir)
        return {"error": clone.stderr[:500], "repo": repo}

    profile = RepoProfile.detect(workdir)
    return {
        "repo": info.get("nameWithOwner", repo),
        "repo_url": info.get("url", f"https://github.com/{repo}"),
        "workdir": workdir,
        "default_branch": (info.get("defaultBranchRef") or {}).get("name", "main"),
        "languages": profile.languages,
        "test_cmd": profile.test_cmd or "none",
        "lint_cmd": profile.lint_cmd or "none",
        "build_cmd": profile.build_cmd or "none",
    }


@tool(credentials=["GITHUB_TOKEN"])
def search_repo_issues(repo: str, max_results: int = 25) -> dict:
    """Search open issues and rank them for merge-likelihood and tractability."""
    result = run_github_cmd(
        [
            "gh",
            "issue",
            "list",
            "--repo",
            repo,
            "--state",
            "open",
            "--search",
            "no:assignee sort:updated-desc",
            "--json",
            "number,title,body,labels,comments,assignees,createdAt,updatedAt,url",
            "--limit",
            str(max_results * 3),
        ],
        timeout=45,
    )
    if result.returncode != 0:
        return {"error": result.stderr[:500], "repo": repo}

    try:
        issues = json.loads(result.stdout) if result.stdout.strip() else []
    except json.JSONDecodeError:
        return {"error": "Failed to parse issue search results", "repo": repo}

    wip_signals = [
        "working on this",
        "i'll take this",
        "i will take this",
        "reserved",
        "draft pr",
        "opened a pull request",
        "submitted a pr",
        "i have a pr",
    ]
    broad_signals = [
        "feature request",
        "support for",
        "rewrite",
        "refactor",
        "roadmap",
        "epic",
    ]

    ranked: list[dict] = []
    for issue in issues:
        if issue.get("assignees"):
            continue

        labels = [
            str(label.get("name", "")).lower() for label in issue.get("labels", [])
        ]
        comments_text = " ".join(
            str(comment.get("body", "")) for comment in issue.get("comments", [])
        ).lower()
        body = str(issue.get("body") or "")
        body_lc = body.lower()

        if any(signal in comments_text for signal in wip_signals):
            continue

        score = 0
        if "good first issue" in labels:
            score += 50
        if "help wanted" in labels:
            score += 40
        if "bug" in labels:
            score += 30
        if "tests" in labels:
            score += 20
        if "docs" in labels:
            score += 10
        if "enhancement" in labels or "feature" in labels:
            score += 5
        if len(issue.get("comments", [])) <= 2:
            score += 5
        if any(signal in body_lc for signal in broad_signals):
            score -= 15

        ranked.append(
            {
                "number": issue["number"],
                "title": issue["title"],
                "body": body[:3000],
                "url": issue.get("url", ""),
                "labels": labels,
                "comment_count": len(issue.get("comments", [])),
                "updated_at": issue.get("updatedAt", ""),
                "score": score,
            }
        )

    ranked = sorted(ranked, key=lambda item: (-item["score"], item["comment_count"]))
    return {"repo": repo, "candidates": ranked[:max_results]}


@tool(credentials=["GITHUB_TOKEN"])
def read_issue_detail(repo: str, issue_number: int) -> dict:
    """Read a specific GitHub issue with full body and recent comments."""
    result = run_github_cmd(
        [
            "gh",
            "issue",
            "view",
            str(issue_number),
            "--repo",
            repo,
            "--json",
            "number,title,body,labels,comments,assignees,state,url,createdAt,updatedAt",
        ],
        timeout=20,
    )
    if result.returncode != 0:
        return {
            "error": result.stderr[:500],
            "repo": repo,
            "issue_number": issue_number,
        }

    try:
        detail = json.loads(result.stdout)
    except json.JSONDecodeError:
        return {
            "error": "Failed to parse issue detail",
            "repo": repo,
            "issue_number": issue_number,
        }

    if detail.get("body"):
        detail["body"] = detail["body"][:6000]
    detail["labels"] = [label.get("name", "") for label in detail.get("labels", [])]
    for comment in detail.get("comments", []):
        if comment.get("body"):
            comment["body"] = comment["body"][:2000]
    return detail


@tool
def create_issue_branch(
    workdir: str,
    issue_number: int,
    issue_title: str,
    default_branch: str = "main",
) -> dict:
    """Create or reset a local working branch for the selected issue."""
    branch = f"agentspan/issue-{issue_number}-{slugify_branch_value(issue_title)}"
    checkout = run_cmd(
        ["git", "-C", workdir, "checkout", "-B", branch, f"origin/{default_branch}"],
        timeout=30,
    )
    if checkout.returncode != 0:
        checkout = run_cmd(
            ["git", "-C", workdir, "checkout", "-B", branch, default_branch],
            timeout=30,
        )
    if checkout.returncode != 0:
        return {"error": checkout.stderr[:500], "workdir": workdir}
    return {"workdir": workdir, "branch": branch, "base_branch": default_branch}


@tool(credentials=["GITHUB_TOKEN"])
def sync_branch_with_base(workdir: str, branch: str, base_branch: str) -> dict:
    """Fetch the latest upstream base branch and rebase the working branch onto it."""
    try:
        workdir = resolve_workdir(workdir)
    except RuntimeError as exc:
        return {"error": str(exc), "workdir": workdir}

    fetch = run_cmd(
        ["git", "-C", workdir, "fetch", "origin", base_branch],
        env=github_env(),
        timeout=120,
    )
    if fetch.returncode != 0:
        return {"error": f"Fetch failed: {fetch.stderr[:500]}", "workdir": workdir}

    checkout = run_cmd(
        ["git", "-C", workdir, "checkout", branch], env=github_env(), timeout=30
    )
    if checkout.returncode != 0:
        return {
            "error": f"Checkout failed: {checkout.stderr[:500]}",
            "workdir": workdir,
        }

    rebase = run_cmd(
        ["git", "-C", workdir, "rebase", f"origin/{base_branch}"],
        env=github_env(),
        timeout=180,
    )
    if rebase.returncode != 0:
        abort = run_cmd(
            ["git", "-C", workdir, "rebase", "--abort"], env=github_env(), timeout=30
        )
        return {
            "error": f"Rebase failed: {rebase.stderr[:500] or rebase.stdout[:500]}",
            "abort_status": abort.returncode == 0,
            "workdir": workdir,
        }

    return {"status": "rebased", "branch": branch, "base_branch": base_branch}


@tool(approval_required=True)
def approve_publication(
    repo: str,
    issue_number: int,
    branch: str,
    change_summary: str,
    test_evidence: str,
    pr_title: str,
    pr_body: str,
) -> dict:
    """Pause for human review of the final tested change set before publication."""
    return {
        "status": "approved",
        "repo": repo,
        "issue_number": issue_number,
        "branch": branch,
        "pr_title": pr_title,
        "change_summary": change_summary[:1000],
        "test_evidence": test_evidence[:1500],
        "pr_body_preview": pr_body[:2000],
    }


@tool
def configure_git_identity(
    workdir: str, git_user: str = "", git_email: str = ""
) -> dict:
    """Configure local git author identity for commits made by this agent."""
    try:
        workdir = resolve_workdir(workdir)
    except RuntimeError as exc:
        return {"error": str(exc), "workdir": workdir}

    git_user = git_user or git_identity()[0]
    git_email = git_email or git_identity()[1]

    if is_dry_run():
        return {
            "status": "dry_run",
            "would_configure": {"user": git_user, "email": git_email},
        }

    user_result = run_cmd(
        ["git", "-C", workdir, "config", "user.name", git_user], timeout=15
    )
    email_result = run_cmd(
        ["git", "-C", workdir, "config", "user.email", git_email], timeout=15
    )
    if user_result.returncode != 0 or email_result.returncode != 0:
        return {
            "error": (user_result.stderr or email_result.stderr)[:500],
            "workdir": workdir,
        }
    return {"status": "configured", "user": git_user, "email": git_email}


@tool(credentials=["GITHUB_TOKEN"])
def push_review_branch(
    repo: str = "",
    workdir: str = "",
    branch: str = "",
    remote_name: str = "agentspan",
) -> dict:
    """Push the issue branch to the authenticated user's fork for manual review."""
    try:
        workdir = resolve_workdir(workdir or "/path/to/repo", repo=repo)
    except RuntimeError as exc:
        return {"error": str(exc), "workdir": workdir, "repo": repo}

    if not repo:
        remote = run_cmd(
            ["git", "-C", workdir, "config", "--get", "remote.origin.url"], timeout=15
        )
        if remote.returncode != 0 or not (remote.stdout or "").strip():
            return {
                "error": "Could not determine repo from remote.origin.url",
                "workdir": workdir,
            }
        try:
            repo = normalize_repo_input((remote.stdout or "").strip())
        except ValueError as exc:
            return {"error": str(exc), "workdir": workdir}

    if not branch:
        current_branch = run_cmd(
            ["git", "-C", workdir, "branch", "--show-current"], timeout=15
        )
        branch = (current_branch.stdout or "").strip()
        if current_branch.returncode != 0 or not branch:
            return {
                "error": "Could not determine current git branch for review push",
                "workdir": workdir,
                "repo": repo,
            }

    if is_dry_run():
        return {
            "status": "dry_run",
            "would_push": {
                "repo": repo,
                "branch": branch,
                "remote_name": remote_name,
            },
        }

    expected_login = expected_github_login()
    try:
        login = current_github_login()
    except RuntimeError as exc:
        return {"error": str(exc)}

    if expected_login and login != expected_login:
        return {
            "error": (
                f"Stored GITHUB_TOKEN resolves to '{login}', expected '{expected_login}'. "
                f"Update the stored GITHUB_TOKEN before pushing the review branch."
            )
        }

    try:
        ensure_fork_remote(repo, workdir, remote_name, login)
    except RuntimeError as exc:
        return {"error": str(exc)}

    push = run_cmd(
        ["git", "-C", workdir, "push", "-u", remote_name, branch],
        env=github_env(),
        timeout=180,
    )
    if push.returncode != 0:
        return {"error": f"Push failed: {push.stderr[:500]}"}

    head = run_cmd(["git", "-C", workdir, "rev-parse", "HEAD"], timeout=15)
    commit_sha = (head.stdout or "").strip()
    if head.returncode != 0 or not commit_sha:
        return {
            "error": "Review branch pushed, but current commit SHA could not be determined",
            "branch": branch,
            "branch_url": fork_branch_url(login, repo, branch),
            "login": login,
        }

    return {
        "status": "pushed",
        "branch": branch,
        "branch_url": fork_branch_url(login, repo, branch),
        "commit_sha": commit_sha,
        "commit_url": fork_commit_url(login, repo, commit_sha),
        "login": login,
    }


@tool(credentials=["GITHUB_TOKEN"])
def create_pull_request(
    repo: str,
    workdir: str,
    branch: str,
    base_branch: str,
    title: str,
    body: str,
    remote_name: str = "agentspan",
) -> dict:
    """Push the branch to the authenticated user's fork and open a pull request."""
    try:
        workdir = resolve_workdir(workdir, repo=repo)
    except RuntimeError as exc:
        return {"error": str(exc), "workdir": workdir, "repo": repo}

    if is_dry_run():
        return {
            "status": "dry_run",
            "would_create": {
                "repo": repo,
                "branch": branch,
                "base_branch": base_branch,
                "title": title,
            },
        }

    expected_login = expected_github_login()
    try:
        login = current_github_login()
    except RuntimeError as exc:
        return {"error": str(exc)}

    if expected_login and login != expected_login:
        return {
            "error": (
                f"Stored GITHUB_TOKEN resolves to '{login}', expected '{expected_login}'. "
                f"Update the stored GITHUB_TOKEN before live publication."
            )
        }

    try:
        ensure_fork_remote(repo, workdir, remote_name, login)
    except RuntimeError as exc:
        return {"error": str(exc)}

    push = run_cmd(
        ["git", "-C", workdir, "push", "-u", remote_name, branch],
        env=github_env(),
        timeout=180,
    )
    if push.returncode != 0:
        return {"error": f"Push failed: {push.stderr[:500]}"}

    draft_flag = ["--draft"] if is_draft_pr() else []
    pr = run_github_cmd(
        [
            "gh",
            "pr",
            "create",
            "--repo",
            repo,
            "--base",
            base_branch,
            "--head",
            f"{login}:{branch}",
            "--title",
            title,
            "--body",
            body,
            *draft_flag,
        ],
        cwd=workdir,
        timeout=60,
    )
    if pr.returncode != 0:
        return {"error": f"PR creation failed: {pr.stderr[:500]}"}
    return {"status": "created", "pr_url": (pr.stdout or "").strip(), "login": login}


@tool(credentials=["GITHUB_TOKEN"])
def comment_on_issue(repo: str, issue_number: int, body: str) -> dict:
    """Post a follow-up issue comment, typically linking the new PR."""
    if is_dry_run():
        return {
            "status": "dry_run",
            "would_comment": {
                "repo": repo,
                "issue_number": issue_number,
                "body": body[:200],
            },
        }

    expected_login = expected_github_login()
    try:
        login = current_github_login()
    except RuntimeError as exc:
        return {"error": str(exc)}

    if expected_login and login != expected_login:
        return {
            "error": (
                f"Stored GITHUB_TOKEN resolves to '{login}', expected '{expected_login}'. "
                f"Update the stored GITHUB_TOKEN before live commenting."
            )
        }

    comment = run_github_cmd(
        ["gh", "issue", "comment", str(issue_number), "--repo", repo, "--body", body],
        timeout=45,
    )
    if comment.returncode != 0:
        return {"error": f"Issue comment failed: {comment.stderr[:500]}"}
    return {
        "status": "commented",
        "repo": repo,
        "issue_number": issue_number,
        "login": login,
    }


def build_pipeline(
    repo_url: str, issue_number: int = 0, extra_guidance: str = ""
) -> Agent:
    """Build the repo-url -> issue -> fix -> PR pipeline."""
    model = get_model()
    dry_run_note = (
        " (DRY RUN - do not publish PRs or issue comments)" if is_dry_run() else ""
    )
    review_branch_note = (
        " (REVIEW BRANCH MODE - push a fork branch for manual review, do not open a PR or issue comment)"
        if is_review_branch_only()
        else ""
    )
    review_branch_analysis_note = (
        "\n\nReview-branch mode rules:\n"
        "- Keep analysis tight and practical; stop once you can identify the likely file(s), smallest test target, and root-cause hypothesis.\n"
        "- Prefer one or two focused repo-inspection commands over broad recursive searches.\n"
        "- Do not spend turns repeating the same search with different shell syntax.\n"
        if is_review_branch_only()
        else ""
    )
    review_branch_fixer_note = (
        "\n\nReview-branch mode rules:\n"
        "- The issue branch from IMPLEMENTATION_DOSSIER already exists. Use `git checkout <BRANCH>` if needed, but never try to create it again.\n"
        "- Prefer targeted tests from TEST_STRATEGY before running the full TEST_CMD.\n"
        "- Prefer small Python scripts for code edits over fragile `sed`/`xargs` one-liners when changing source or tests.\n"
        "- After the first material edit plus validation attempt, hand off to reviewer with honest results instead of silently retrying many shell variations.\n"
        "- If the branch has a focused diff but validation is incomplete, still hand off to reviewer so publisher can push the branch for manual review.\n"
        "- Do not spend more than two turns retrying shell syntax or dependency installation.\n"
        if is_review_branch_only()
        else ""
    )
    review_branch_reviewer_note = (
        "\n\nReview-branch mode rules:\n"
        "- Optimize for deciding whether the current branch is reviewable, not for perfect publication readiness.\n"
        "- Re-run only the smallest relevant validation needed to judge the current diff.\n"
        "- If the branch is understandable but not publication-ready, emit HANDOFF_TO_FIXER with concise feedback after one review pass.\n"
        "- Keep feedback short and actionable so the loop can finish before publisher runs.\n"
        if is_review_branch_only()
        else ""
    )
    review_branch_loop_note = (
        "\n8. In review-branch mode, cap the loop aggressively so publisher still runs before the top-level timeout.\n"
        "9. In review-branch mode, stop after two fixer turns or one reviewer pass without approval.\n"
        "10. Preserve the latest handoff verbatim so publisher can push the branch even if approval was not reached.\n"
        if is_review_branch_only()
        else ""
    )
    forced_issue_note = (
        f"Forced issue: #{issue_number}." if issue_number else "No forced issue."
    )
    forced_issue_rules = (
        "\nForced-issue rules:\n"
        f"- The target issue is already chosen: #{issue_number}.\n"
        "- Do not call search_repo_issues.\n"
        "- Call read_issue_detail exactly once for the forced issue, then create_issue_branch.\n"
        "- Do not debate alternative issues or reread the same issue multiple times.\n"
        if issue_number
        else ""
    )
    code_commands = [
        "bash",
        "sh",
        "git",
        "python",
        "python3",
        "pytest",
        "uv",
        "pip",
        "ruff",
        "flake8",
        "mypy",
        "black",
        "isort",
        "node",
        "npm",
        "npx",
        "pnpm",
        "yarn",
        "tsc",
        "go",
        "cargo",
        "make",
        "cmake",
        "bundle",
        "rake",
        "mvn",
        "ls",
        "cat",
        "find",
        "grep",
        "sed",
        "head",
        "tail",
        "wc",
        "diff",
        "sort",
        "curl",
        *local_exec_file_commands(),
        *local_exec_shell_helpers(),
    ]

    repo_intake = Agent(
        name="repo_intake",
        model=model,
        instructions=f"""\
You are preparing a GitHub repository workspace for a code-fixing agent.{dry_run_note}

Input repo URL: {repo_url}

Steps:
1. Use prepare_repo_workspace.
2. Stop if setup fails.
3. Output EXACTLY:

REPO_READY
REPO: <owner/name>
REPO_URL: <canonical url>
WORKDIR: <local clone path>
DEFAULT_BRANCH: <default branch>
TEST_CMD: <detected test command or "none">
LINT_CMD: <detected lint command or "none">
BUILD_CMD: <detected build command or "none">
LANGUAGES: <comma-separated languages>
""",
        tools=[prepare_repo_workspace],
        max_turns=10,
        timeout_seconds=stage_timeout_seconds(900, 300),
    )

    issue_scout = Agent(
        name="issue_scout",
        model=model,
        instructions=f"""\
You are selecting a GitHub issue that is worth turning into a real PR.{dry_run_note}

{forced_issue_note}
Extra guidance: {extra_guidance or "none"}
{forced_issue_rules}

Selection rubric:
1. Clear bug or tightly scoped enhancement.
2. No assignee, no linked PR, no WIP signals.
3. Easy to validate locally with tests or a minimal smoke run.
4. Small-to-medium patch, maintainers can review quickly.
5. High likelihood of acceptance, not a speculative redesign.

Use search_repo_issues unless a forced issue number was provided.
Use read_issue_detail on the best candidates.
Inspect the local codebase and tests before deciding.
After choosing an issue, use create_issue_branch.

If nothing is suitable, output:
NO_CANDIDATE_ISSUES

If you choose an issue, output EXACTLY:

TARGET_ISSUE_READY
REPO: <owner/name>
REPO_URL: <url>
WORKDIR: <path>
DEFAULT_BRANCH: <branch>
BRANCH: <working branch>
ISSUE: <number>
ISSUE_URL: <url>
TITLE: <issue title>
TEST_CMD: <command or "none">
LINT_CMD: <command or "none">
BUILD_CMD: <command or "none">
RATIONALE: <why this is the right issue>
SUCCESS_CRITERIA: <observable acceptance criteria>
""",
        tools=(
            [read_issue_detail, create_issue_branch]
            if issue_number
            else [search_repo_issues, read_issue_detail, create_issue_branch]
        ),
        local_code_execution=True,
        allowed_languages=["python", "bash", "javascript", "typescript"],
        allowed_commands=code_commands,
        gate=TextGate("NO_CANDIDATE_ISSUES"),
        max_turns=8 if issue_number else 20,
        max_tokens=stage_max_tokens(8000),
        timeout_seconds=180 if issue_number else stage_timeout_seconds(1200, 420),
    )

    repo_analyst = Agent(
        name="repo_analyst",
        model=model,
        instructions=f"""\
You are doing a deep implementation analysis before any edits happen.

You receive TARGET_ISSUE_READY with the cloned repository path.

Analyze:
1. Source architecture relevant to the issue.
2. The existing test suite and nearest comparable tests.
3. Files and symbols likely to change.
4. The smallest reliable validation plan.
5. Whether a local smoke command is needed beyond tests.

Do not edit code yet. Produce a precise engineering dossier.

Execution rules:
- Treat WORKDIR from the prior stage as the source of truth.
- Never use placeholder paths like /path/to/repo.
- Never ask the user for the repo path.
- For directory changes, file discovery, and shell pipelines, use bash code rather than Python subprocess wrappers.
- Prefer commands that run inside WORKDIR or reference WORKDIR explicitly.
- The execute_code tool input must be executable code only: no prose, no markdown fences, no labels like WORKDIR:, run:, content:, or def:.
- Do not start bash snippets with variable-assignment lines like WORKDIR=...; inline the real path directly in commands.
- Default to bash for repo inspection. Use python only for actual Python scripts.
{review_branch_analysis_note}

Output EXACTLY:

IMPLEMENTATION_DOSSIER
REPO: ...
WORKDIR: ...
BRANCH: ...
ISSUE: ...
ARCHITECTURE_SUMMARY: <how the relevant code and tests fit together>
LIKELY_FILES: <comma-separated paths>
ROOT_CAUSE_HYPOTHESIS: <best current explanation>
TEST_STRATEGY: <targeted tests, then broader checks>
LOCAL_SMOKE_CMD: <smallest runtime verification command or "none">
RISK_NOTES: <what could easily go wrong>
""",
        local_code_execution=True,
        allowed_languages=["python", "bash", "javascript", "typescript"],
        allowed_commands=code_commands,
        max_turns=8 if is_review_branch_only() else 20,
        max_tokens=stage_max_tokens(12000),
        timeout_seconds=420 if is_review_branch_only() else stage_timeout_seconds(1800, 600),
    )

    fixer = Agent(
        name="fixer",
        model=model,
        instructions=f"""\
You are implementing the issue fix.

You receive IMPLEMENTATION_DOSSIER with repo context, target files, and a test strategy.

Rules:
1. Make the smallest correct change that fully resolves the issue.
2. Keep the diff tightly scoped.
3. Add or update tests whenever the repo has test coverage for the area.
4. Run TEST_CMD and LINT_CMD when available.
5. If LOCAL_SMOKE_CMD is not "none", run it when the issue touches runtime behavior.
6. Clean up any temporary artifacts or background processes you create.
7. Stage only relevant files.

Execution rules:
- Treat WORKDIR from IMPLEMENTATION_DOSSIER as the source of truth.
- Never use placeholder paths like /path/to/repo.
- Never ask the user for the repo path.
- For changing directories or multi-step shell commands, use bash code rather than Python subprocess wrappers.
- Keep commands scoped to WORKDIR.
- The execute_code tool input must be executable code only: no prose, no markdown fences, no labels like WORKDIR:, run:, content:, or def:.
- Do not start bash snippets with variable-assignment lines like WORKDIR=...; inline the real path directly in commands.
- Default to bash for edits, git commands, and tests. Use python only for actual Python scripts.
{review_branch_fixer_note}

When ready, output:

HANDOFF_TO_REVIEWER
REPO: ...
WORKDIR: ...
BRANCH: ...
ISSUE: ...
CHANGE_SUMMARY: <what changed and why>
FILES_CHANGED: <list>
TEST_OUTPUT: <results>
LINT_OUTPUT: <results>
SMOKE_OUTPUT: <results or "not needed">
""",
        local_code_execution=True,
        allowed_languages=["python", "bash", "javascript", "typescript"],
        allowed_commands=code_commands,
        include_contents="none",
        max_turns=12 if is_review_branch_only() else 35,
        max_tokens=stage_max_tokens(12000),
        timeout_seconds=300 if is_review_branch_only() else stage_timeout_seconds(2400, 900),
    )

    reviewer = Agent(
        name="reviewer",
        model=model,
        instructions=f"""\
You are the final quality gate before a public PR.

Review checklist:
1. The issue is actually solved, not partially addressed.
2. Tests demonstrate the fix and don't overfit.
3. The diff is narrow and maintainable.
4. The code matches existing project style and patterns.
5. Runtime behavior was smoke-tested when appropriate.

Re-run the relevant validation yourself.

Execution rules:
- Treat WORKDIR from the latest handoff as the source of truth.
- Never use placeholder paths like /path/to/repo.
- Never ask the user for the repo path.
- For shell validation or directory changes, prefer bash code over Python subprocess wrappers.
- The execute_code tool input must be executable code only: no prose, no markdown fences, no labels like WORKDIR:, run:, content:, or def:.
- Do not start bash snippets with variable-assignment lines like WORKDIR=...; inline the real path directly in commands.
- Default to bash for validation commands. Use python only for actual Python scripts.
{review_branch_reviewer_note}

If anything is weak, output:

HANDOFF_TO_FIXER
REPO: ...
WORKDIR: ...
BRANCH: ...
ISSUE: ...
REVIEW_FEEDBACK: <specific fixes still required>

If publication quality is reached, output:

APPROVED_FOR_PUBLICATION
REPO: ...
WORKDIR: ...
BRANCH: ...
ISSUE: ...
MERGE_CONFIDENCE: low|medium|high
REVIEW_NOTES: <why this should be acceptable>
TEST_EVIDENCE: <what passed>
PR_TITLE: <clear PR title under 72 chars>
PR_BODY: |
  ## What
  <what was broken or requested>

  ## Fix
  <what changed>

  ## Validation
  <tests and smoke checks>

  Fixes #<ISSUE>

  ---
  Automated fix prepared by AgentSpan.
""",
        local_code_execution=True,
        allowed_languages=["python", "bash", "javascript", "typescript"],
        allowed_commands=code_commands,
        include_contents="none",
        max_turns=8 if is_review_branch_only() else 18,
        max_tokens=stage_max_tokens(10000),
        timeout_seconds=240 if is_review_branch_only() else stage_timeout_seconds(1800, 600),
    )

    coding_review_loop = Agent(
        name="coding_review_loop",
        model=model,
        instructions=f"""\
Run the implementation/review loop.

Rules:
1. Start with fixer.
2. HANDOFF_TO_REVIEWER sends control to reviewer.
3. HANDOFF_TO_FIXER sends control back to fixer.
4. APPROVED_FOR_PUBLICATION ends the loop.
5. Maximum 3 review rounds.
6. If quality never reaches publication level, stop without opening a PR.
7. When stopping without approval, preserve the latest handoff content verbatim so downstream review-branch mode still has WORKDIR and BRANCH.
{review_branch_loop_note}
""",
        agents=[fixer, reviewer],
        strategy=Strategy.SWARM,
        handoffs=[
            OnTextMention(text="HANDOFF_TO_REVIEWER", target="reviewer"),
            OnTextMention(text="HANDOFF_TO_FIXER", target="fixer"),
        ],
        max_turns=16 if is_review_branch_only() else 50,
        max_tokens=stage_max_tokens(12000),
        timeout_seconds=420 if is_review_branch_only() else stage_timeout_seconds(3600, 900),
    )

    publisher = Agent(
        name="publisher",
        model=model,
        instructions=f"""\
You publish the approved fix to GitHub.{dry_run_note}{review_branch_note}

Publication requirements:
1. In normal mode, only proceed if reviewer emitted APPROVED_FOR_PUBLICATION.
2. In review-branch mode, always call push_review_branch first, even if REPO, WORKDIR, BRANCH, or ISSUE are missing from the handoff.
3. In review-branch mode, do not open a PR and do not comment on the issue. Push the branch for manual inspection instead.
4. In review-branch mode, skip approve_publication entirely.
5. Rebase the issue branch onto the latest upstream default branch.
6. Pause on approve_publication so a human reviews the final tested diff before anything is sent.
7. Configure git identity so commits clearly show AgentSpan in history.
8. Commit only the issue-relevant changes.
9. In normal mode, use create_pull_request so the PR is opened from the authenticated GitHub fork.
10. In normal mode, use comment_on_issue to leave a brief comment with the PR link.
11. In review-branch mode, use push_review_branch and stop after reporting the branch URL.

Important:
- PR and issue comment authorship comes from the stored GITHUB_TOKEN credential.
- In live mode that token must belong to `{expected_github_login()}`.
- Commit author defaults come from AGENTSPAN_GIT_USER / AGENTSPAN_GIT_EMAIL.
- The human approval step must review the tested change summary, PR title/body, and validation evidence.
- Treat WORKDIR from the approved handoff as the source of truth.
- Never use placeholder paths like /path/to/repo.
- Never ask the user for the repo path.
- Never ask the user for REPO, WORKDIR, BRANCH, ISSUE, or any other review-branch metadata.
- Never answer conversationally or thank the user.
- In review-branch mode, prefer push_review_branch directly. That tool can recover missing repo/workdir/branch details from the latest cloned workspace.
- In review-branch mode, do not ask follow-up questions. Either push the recovered branch or return PUBLICATION_BLOCKED with the tool failure summary.

If review-branch mode is OFF and the input does NOT contain APPROVED_FOR_PUBLICATION, do not call any tools. Output EXACTLY:
PUBLICATION_BLOCKED
REASON: reviewer did not approve publication-ready changes

If review-branch mode is ON and push_review_branch still cannot recover enough context, output EXACTLY:
PUBLICATION_BLOCKED
REASON: review-branch mode could not recover a reviewable branch from the latest workspace

If review-branch mode is ON and you successfully push the branch, output EXACTLY:
REVIEW_BRANCH_PUSHED
BRANCH: <branch name>
BRANCH_URL: <url or dry-run summary>
COMMIT_SHA: <full sha>
COMMIT_URL: <url>
REVIEW_STATUS: approved|blocked
REASON: <approved for publication or concise reviewer feedback summary>

If any publication tool returns an error, output EXACTLY:
PUBLICATION_BLOCKED
REASON: <tool error summary>

Issue comment template:
AgentSpan opened PR <PR_URL> for this issue.
Summary: <one sentence>

Final output:
PUBLISHED
PR_URL: <url or dry-run summary>
ISSUE_COMMENT: <status>
""",
        tools=[
            sync_branch_with_base,
            approve_publication,
            configure_git_identity,
            push_review_branch,
            create_pull_request,
            comment_on_issue,
        ],
        local_code_execution=True,
        allowed_languages=["bash"],
        allowed_commands=["bash", "sh", "git", "ls", "cat"],
        required_tools=["push_review_branch"] if is_review_branch_only() else [],
        max_turns=18,
        max_tokens=stage_max_tokens(8000),
        timeout_seconds=stage_timeout_seconds(1200, 300),
    )

    if is_review_branch_only():
        return repo_intake >> issue_scout >> repo_analyst >> fixer >> publisher

    return repo_intake >> issue_scout >> repo_analyst >> coding_review_loop >> publisher


def parse_args() -> tuple[str, int, str, int]:
    parser = argparse.ArgumentParser(
        description="GitHub repo URL -> issue -> PR agent (AgentSpan)",
        epilog=(
            "Example: python repo_url_issue_pr_agent.py "
            "https://github.com/pytest-dev/pytest-asyncio --issue 1334 "
            '--guidance "Prefer a pure test-backed fix."'
        ),
    )
    parser.add_argument("repo_url", help="GitHub repository URL or owner/name")
    parser.add_argument(
        "--issue", type=int, default=0, help="Optional issue number to force"
    )
    parser.add_argument(
        "--guidance",
        default="",
        help="Extra issue-selection guidance for issue choice or implementation approach",
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="Skip PR and issue publication"
    )
    parser.add_argument(
        "--review-branch",
        "--private-branch",
        action="store_true",
        dest="review_branch",
        help="Push a fork branch for manual review instead of opening a PR/comment",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=0,
        help="Overall runtime timeout in seconds (default: shorter in --dry-run, longer in live mode)",
    )
    args = parser.parse_args()
    if args.dry_run:
        os.environ["AGENTSPAN_DRY_RUN"] = "true"
    if args.review_branch:
        os.environ["AGENTSPAN_REVIEW_BRANCH_ONLY"] = "true"
    if args.timeout and args.timeout > 0:
        os.environ["AGENTSPAN_AGENT_TIMEOUT"] = str(args.timeout)
    return args.repo_url, args.issue, args.guidance.strip(), runtime_timeout_seconds()


def main() -> None:
    repo_url, issue_number, guidance, timeout_seconds = parse_args()
    pipeline = build_pipeline(repo_url, issue_number, guidance)

    print(f"[{'DRY RUN' if is_dry_run() else 'LIVE'}] Repo URL issue solver")
    print(f"  Repo URL: {repo_url}")
    print(f"  Expected GitHub token owner: {expected_github_login()}")
    print(f"  Draft PR: {is_draft_pr()}")
    print(f"  Publication mode: {publication_mode_label()}")
    print()

    forced_issue = (
        f"Target issue #{issue_number}."
        if issue_number
        else "Select the best candidate issue."
    )
    with AgentRuntime(server_url=get_server_url()) as runtime:
        result = runtime.run(
            pipeline,
            (
                f"Repository URL: {repo_url}\n"
                f"{forced_issue}\n"
                "Deeply analyze the codebase and tests, choose the most maintainable open issue, "
                "implement a high-quality fix, validate it locally, and publish a PR plus issue comment "
                "if the reviewer approves."
            ),
            timeout=timeout_seconds,
        )
        result.print_result()


if __name__ == "__main__":
    main()
