# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""Slack Auto-Fix Agent — monitors a Slack channel and auto-creates PRs for bug reports.

Monitors a Slack channel for bug reports. When a message describes something
broken, the agent:
  1. Reads the Slack channel for new bug reports
  2. Investigates the relevant code in the repo
  3. Applies a fix
  4. Creates a branch, commits, pushes, and opens a GitHub PR

Architecture:
    slack_monitor (SEQUENTIAL)
    ├── issue_reader      — reads Slack, extracts bug description
    ├── code_investigator — finds relevant files, understands root cause
    ├── code_fixer        — applies the fix
    └── pr_creator        — creates branch + commit + PR

Requirements:
    - AGENTSPAN_SERVER_URL=http://localhost:6767/api
    - AGENTSPAN_LLM_MODEL=anthropic/claude-opus-4-6 (or gpt-4o)
    - SLACK_BOT_TOKEN=xoxb-...     (Bot token with channels:read, channels:history)
    - SLACK_CHANNEL_ID=C...        (Channel to monitor)
    - GITHUB_TOKEN=ghp_...         (Token with repo write access)
    - REPO_PATH=/path/to/repo      (Local path to the codebase)
    - GITHUB_REPO=owner/repo       (e.g. agentspan-ai/agentspan)

Usage:
    # Run once — picks up latest unprocessed bug report
    python 91_slack_autofix_agent.py

    # Run on a loop (e.g. via cron every 5 minutes)
    python 91_slack_autofix_agent.py --loop

    # Dry-run — investigate and plan fix, but don't push or create PR
    python 91_slack_autofix_agent.py --dry-run
"""

import argparse
import json
import os
import subprocess
import time
from pathlib import Path

from agentspan.agents import Agent, AgentRuntime, Strategy, tool
from settings import settings

REPO_PATH = Path(os.environ.get("REPO_PATH", "."))
GITHUB_REPO = os.environ.get("GITHUB_REPO", "")
SLACK_BOT_TOKEN = os.environ.get("SLACK_BOT_TOKEN", "")
SLACK_CHANNEL_ID = os.environ.get("SLACK_CHANNEL_ID", "")
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN", "")
DRY_RUN = False

# ── State file — tracks last processed Slack message ───────────────────────

STATE_FILE = Path("/tmp/agentspan_autofix_state.json")


def _load_state() -> dict:
    if STATE_FILE.exists():
        return json.loads(STATE_FILE.read_text())
    return {"last_ts": None, "processed": []}


def _save_state(state: dict) -> None:
    STATE_FILE.write_text(json.dumps(state, indent=2))


# ── Tools ───────────────────────────────────────────────────────────────────


@tool
def fetch_slack_bug_reports(limit: int = 10) -> str:
    """Fetch recent messages from the Slack bug report channel.

    Returns a JSON list of messages with ts (timestamp), user, and text.
    Filters to only messages not yet processed.
    """
    try:
        import requests
    except ImportError:
        return json.dumps({"error": "requests not installed — run: uv add requests"})

    state = _load_state()
    oldest = state.get("last_ts") or "0"

    resp = requests.get(
        "https://slack.com/api/conversations.history",
        headers={"Authorization": f"Bearer {SLACK_BOT_TOKEN}"},
        params={"channel": SLACK_CHANNEL_ID, "oldest": oldest, "limit": limit},
    )
    data = resp.json()
    if not data.get("ok"):
        return json.dumps({"error": data.get("error", "Unknown Slack API error")})

    messages = [
        {"ts": m["ts"], "user": m.get("user", "unknown"), "text": m.get("text", "")}
        for m in data.get("messages", [])
        if m.get("type") == "message"
        and m["ts"] not in state.get("processed", [])
    ]
    return json.dumps({"messages": messages, "count": len(messages)})


@tool
def search_codebase(query: str, path: str = "", file_pattern: str = "*.py") -> str:
    """Search the codebase for files or code matching the query.

    Args:
        query:        Text or regex to search for
        path:         Subdirectory to search in (relative to repo root)
        file_pattern: Glob pattern to filter files (e.g. '*.py', '*.java')
    """
    search_path = REPO_PATH / path if path else REPO_PATH
    result = subprocess.run(
        ["grep", "-rn", "--include", file_pattern, query, str(search_path)],
        capture_output=True, text=True,
    )
    output = result.stdout.strip()
    if not output:
        return f"No matches for '{query}' in {search_path}"
    lines = output.split("\n")
    if len(lines) > 50:
        lines = lines[:50]
        lines.append(f"... ({len(output.split(chr(10))) - 50} more lines truncated)")
    return "\n".join(lines)


@tool
def read_file(file_path: str) -> str:
    """Read the contents of a file in the repository.

    Args:
        file_path: Path relative to repo root
    """
    full_path = REPO_PATH / file_path
    if not full_path.exists():
        return f"File not found: {file_path}"
    content = full_path.read_text()
    if len(content) > 10_000:
        return content[:10_000] + f"\n... (truncated, {len(content)} total chars)"
    return content


@tool
def write_file(file_path: str, content: str) -> str:
    """Write or overwrite a file in the repository.

    Args:
        file_path: Path relative to repo root
        content:   Full file content to write
    """
    if DRY_RUN:
        return f"[DRY RUN] Would write {len(content)} chars to {file_path}"
    full_path = REPO_PATH / file_path
    full_path.parent.mkdir(parents=True, exist_ok=True)
    full_path.write_text(content)
    return f"Written: {file_path} ({len(content)} chars)"


@tool
def run_git_command(args: str) -> str:
    """Run a git command in the repository.

    Args:
        args: git subcommand and arguments (e.g. 'status', 'diff --staged')
    """
    result = subprocess.run(
        ["git"] + args.split(),
        capture_output=True, text=True, cwd=str(REPO_PATH),
    )
    output = (result.stdout + result.stderr).strip()
    return output[:3000] if len(output) > 3000 else output


@tool
def create_branch_and_commit(branch_name: str, commit_message: str, files: str) -> str:
    """Create a new git branch, stage specified files, and commit.

    Args:
        branch_name:    Name for the new branch (e.g. 'fix/null-pointer-auth')
        commit_message: Commit message
        files:          Space-separated list of files to stage (relative to repo root)
    """
    if DRY_RUN:
        return f"[DRY RUN] Would create branch '{branch_name}' and commit: {commit_message}"

    # Create branch
    r = subprocess.run(
        ["git", "checkout", "-b", branch_name],
        capture_output=True, text=True, cwd=str(REPO_PATH),
    )
    if r.returncode != 0:
        return f"Failed to create branch: {r.stderr}"

    # Stage files
    for f in files.split():
        subprocess.run(["git", "add", f], cwd=str(REPO_PATH))

    # Commit
    r = subprocess.run(
        ["git", "commit", "--no-verify", "-m", commit_message],
        capture_output=True, text=True, cwd=str(REPO_PATH),
    )
    if r.returncode != 0:
        return f"Commit failed: {r.stderr}"

    return f"Created branch '{branch_name}' and committed: {commit_message}"


@tool
def push_branch(branch_name: str) -> str:
    """Push a branch to the remote origin.

    Args:
        branch_name: Name of the branch to push
    """
    if DRY_RUN:
        return f"[DRY RUN] Would push branch '{branch_name}'"

    r = subprocess.run(
        ["git", "push", "-u", "origin", branch_name],
        capture_output=True, text=True, cwd=str(REPO_PATH),
    )
    output = (r.stdout + r.stderr).strip()
    return output


@tool
def create_github_pr(title: str, body: str, branch: str, base: str = "main") -> str:
    """Create a GitHub Pull Request.

    Args:
        title:  PR title
        body:   PR description (markdown supported)
        branch: Source branch name
        base:   Target branch (default: main)
    """
    if DRY_RUN:
        return f"[DRY RUN] Would create PR: '{title}' ({branch} → {base})"

    r = subprocess.run(
        ["gh", "pr", "create",
         "--repo", GITHUB_REPO,
         "--title", title,
         "--body", body,
         "--head", branch,
         "--base", base],
        capture_output=True, text=True, cwd=str(REPO_PATH),
        env={**os.environ, "GITHUB_TOKEN": GITHUB_TOKEN},
    )
    output = (r.stdout + r.stderr).strip()
    return output


@tool
def mark_message_processed(slack_ts: str) -> str:
    """Mark a Slack message as processed so it won't be picked up again.

    Args:
        slack_ts: Slack message timestamp (ts field)
    """
    state = _load_state()
    state.setdefault("processed", []).append(slack_ts)
    state["last_ts"] = slack_ts
    _save_state(state)
    return f"Marked message {slack_ts} as processed"


@tool
def post_slack_reply(channel: str, thread_ts: str, message: str) -> str:
    """Post a reply to a Slack message thread.

    Args:
        channel:   Slack channel ID
        thread_ts: Timestamp of the parent message to reply to
        message:   Reply text (markdown supported)
    """
    try:
        import requests
    except ImportError:
        return "requests not installed"

    resp = requests.post(
        "https://slack.com/api/chat.postMessage",
        headers={
            "Authorization": f"Bearer {SLACK_BOT_TOKEN}",
            "Content-Type": "application/json",
        },
        json={"channel": channel, "thread_ts": thread_ts, "text": message},
    )
    data = resp.json()
    return "Reply posted" if data.get("ok") else f"Failed: {data.get('error')}"


# ── Agents ──────────────────────────────────────────────────────────────────

issue_reader = Agent(
    name="issue_reader",
    model=settings.llm_model,
    tools=[fetch_slack_bug_reports],
    instructions="""
You read Slack bug reports and extract actionable bug descriptions.

Steps:
1. Fetch recent messages from the Slack channel
2. Identify messages that describe bugs, errors, or broken behaviour
3. Ignore: questions, feature requests, general discussion
4. For each bug, extract:
   - A clear one-line bug title
   - The component/area likely affected (e.g. "router strategy", "MANUAL selection")
   - Key symptoms or error messages quoted from the report
   - The Slack message ts (timestamp) — needed for deduplication

Output a JSON object:
{
  "bug_found": true/false,
  "slack_ts": "...",
  "title": "...",
  "component": "...",
  "description": "..."
}

If no actionable bug is found, set bug_found=false.
""",
)

code_investigator = Agent(
    name="code_investigator",
    model=settings.llm_model,
    tools=[search_codebase, read_file, run_git_command],
    instructions="""
You are a senior engineer investigating a bug in the Agentspan codebase.

Given a bug description, you:
1. Search the codebase to find the relevant files
2. Read the relevant code sections
3. Identify the exact root cause
4. Determine which file(s) need to be changed and how

Output a JSON object:
{
  "root_cause": "...",
  "files_to_change": ["path/to/file.py"],
  "fix_description": "...",
  "branch_name": "fix/short-kebab-case-description"
}
""",
)

code_fixer = Agent(
    name="code_fixer",
    model=settings.llm_model,
    tools=[read_file, write_file, run_git_command],
    instructions="""
You are a senior engineer applying a bug fix.

Given a root cause analysis and the files to change:
1. Read the current file content carefully
2. Apply the minimal fix — change only what is necessary
3. Do not reformat, refactor, or change unrelated code
4. Write the fixed file back

Output a summary of what you changed and why.
""",
)

pr_creator = Agent(
    name="pr_creator",
    model=settings.llm_model,
    tools=[
        create_branch_and_commit,
        push_branch,
        create_github_pr,
        mark_message_processed,
        post_slack_reply,
    ],
    instructions="""
You create a clean GitHub PR for a bug fix and notify the Slack channel.

Steps:
1. Create a new branch and commit the changed files
2. Push the branch to origin
3. Create a GitHub PR with:
   - Clear title: "fix(<component>): <what was broken>"
   - Body describing the bug, root cause, and fix
4. Mark the Slack message as processed
5. Reply in the Slack thread with the PR link

Branch naming: fix/short-kebab-case (e.g. fix/router-dual-role)
Commit message: conventional commits format
""",
)

# ── Pipeline ────────────────────────────────────────────────────────────────

autofix_pipeline = Agent(
    name="slack_autofix_pipeline",
    model=settings.llm_model,
    agents=[issue_reader, code_investigator, code_fixer, pr_creator],
    strategy=Strategy.SEQUENTIAL,
    instructions="""
You are an autonomous engineering agent that fixes bugs reported in Slack.

Run the full pipeline:
1. issue_reader   — read Slack, find the bug report
2. code_investigator — locate root cause in the codebase
3. code_fixer     — apply the fix
4. pr_creator     — create branch, commit, push, open PR, reply in Slack

If issue_reader finds no actionable bug (bug_found=false), stop — do not
run the remaining agents.
""",
)


# ── Entry point ──────────────────────────────────────────────────────────────

def run_once() -> None:
    with AgentRuntime() as runtime:
        result = runtime.run(
            autofix_pipeline,
            "Check the Slack bug report channel and fix any new issues found.",
        )
        result.print_result()


def run_loop(interval_seconds: int = 300) -> None:
    """Poll Slack every interval_seconds and fix any new bugs found."""
    print(f"Starting autofix loop — polling every {interval_seconds}s. Ctrl+C to stop.")
    while True:
        print(f"\n[{time.strftime('%H:%M:%S')}] Checking for new bug reports...")
        run_once()
        print(f"Sleeping {interval_seconds}s...")
        time.sleep(interval_seconds)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Slack Auto-Fix Agent")
    parser.add_argument("--loop", action="store_true",
                        help="Poll continuously (every 5 min)")
    parser.add_argument("--interval", type=int, default=300,
                        help="Poll interval in seconds (default: 300)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Investigate and plan fix but don't write files or create PR")
    args = parser.parse_args()

    if args.dry_run:
        DRY_RUN = True
        print("[DRY RUN] Will investigate but not write files or create PR")

    # Validate required env vars
    missing = []
    if not SLACK_BOT_TOKEN:
        missing.append("SLACK_BOT_TOKEN")
    if not SLACK_CHANNEL_ID:
        missing.append("SLACK_CHANNEL_ID")
    if not GITHUB_REPO:
        missing.append("GITHUB_REPO")
    if not DRY_RUN and not GITHUB_TOKEN:
        missing.append("GITHUB_TOKEN")
    if missing:
        print(f"Missing required env vars: {', '.join(missing)}")
        print("Set them and retry. See the docstring at the top of this file.")
        exit(1)

    if args.loop:
        run_loop(args.interval)
    else:
        run_once()
