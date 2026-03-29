# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""GitHub Coding Agent — pick an issue, code the fix, create a PR.

Demonstrates:
    - Swarm orchestration with 3 specialist agents + team coordinator
    - GitHub integration via gh CLI tools (list issues, create PRs)
    - Git operations (clone, branch, commit, push)
    - Code execution for writing and testing code
    - End-to-end autonomous workflow: issue → code → test → PR

Architecture:
    coding_team (swarm coordinator)
        ├── github_agent — picks issues, clones repo, commits, pushes, creates PRs
        ├── coder — implements the fix in the cloned repo
        └── qa_tester — reviews code, runs tests, reports bugs or approval

    Flow:
        1. coding_team triages → transfers to github_agent
        2. github_agent picks issue, clones repo → transfers to coder
        3. coder implements → transfers to qa_tester
        4. qa_tester tests → if bugs: transfers to coder (loop)
                            → if pass: transfers to github_agent
        5. github_agent commits, pushes, creates PR → done

Requirements:
    - Conductor server running
    - AGENTSPAN_SERVER_URL=http://localhost:8080/api in .env or environment
    - gh CLI authenticated (gh auth status)
    - Git configured with push access to the repo
"""

import os
import subprocess
import uuid

from agentspan.agents import Agent, AgentRuntime, Strategy
from agentspan.agents.handoff import OnTextMention
from agentspan.agents.tool import tool

REPO = "agentspan/codingexamples"
WORK_DIR = f"/tmp/codingexamples-{uuid.uuid4().hex[:8]}"


# ── GitHub & Git tools ───────────────────────────────────────────────


@tool
def list_github_issues(state: str = "open", limit: int = 10) -> str:
    """List GitHub issues from the repository.

    Args:
        state: Issue state filter — 'open', 'closed', or 'all'.
        limit: Maximum number of issues to return.

    Returns:
        The list of issues as text.
    """
    result = subprocess.run(
        ["gh", "issue", "list", "--repo", REPO, "--state", state,
         "--limit", str(limit), "--json", "number,title,body,labels"],
        capture_output=True, text=True, timeout=30,
    )
    if result.returncode != 0:
        return f"Error listing issues: {result.stderr}"
    return result.stdout


@tool
def get_github_issue(issue_number: int) -> str:
    """Get details of a specific GitHub issue.

    Args:
        issue_number: The issue number to fetch.

    Returns:
        The issue details as JSON.
    """
    result = subprocess.run(
        ["gh", "issue", "view", str(issue_number), "--repo", REPO,
         "--json", "number,title,body,labels,comments"],
        capture_output=True, text=True, timeout=30,
    )
    if result.returncode != 0:
        return f"Error getting issue: {result.stderr}"
    return result.stdout


@tool
def clone_repo() -> str:
    """Clone the GitHub repository to a unique /tmp directory for working on it.

    Returns:
        Success or error message.
    """
    result = subprocess.run(
        ["gh", "repo", "clone", REPO, WORK_DIR],
        capture_output=True, text=True, timeout=60,
    )
    if result.returncode != 0:
        return f"Error cloning: {result.stderr}"
    return f"Cloned {REPO} to {WORK_DIR}"


@tool
def git_create_branch(branch_name: str) -> str:
    """Create and checkout a new git branch.

    Args:
        branch_name: Name for the new branch.

    Returns:
        Success or error message.
    """
    result = subprocess.run(
        ["git", "checkout", "-b", branch_name],
        capture_output=True, text=True, timeout=10, cwd=WORK_DIR,
    )
    if result.returncode != 0:
        return f"Error creating branch: {result.stderr}"
    return f"Created and checked out branch: {branch_name}"


@tool
def write_file(path: str, content: str) -> str:
    """Write content to a file in the cloned repo.

    Args:
        path: Relative path within the repo (e.g. 'src/utils.py').
        content: The file content to write.

    Returns:
        Success or error message.
    """
    full_path = os.path.join(WORK_DIR, path)
    os.makedirs(os.path.dirname(full_path), exist_ok=True)
    with open(full_path, "w") as f:
        f.write(content)
    return f"Wrote {len(content)} bytes to {path}"


@tool
def read_file(path: str) -> str:
    """Read a file from the cloned repo.

    Args:
        path: Relative path within the repo (e.g. 'src/utils.py').

    Returns:
        The file content or error message.
    """
    full_path = os.path.join(WORK_DIR, path)
    if not os.path.exists(full_path):
        return f"File not found: {path}"
    with open(full_path) as f:
        return f.read()


@tool
def list_files(path: str = ".") -> str:
    """List files in a directory of the cloned repo.

    Args:
        path: Relative directory path (default: repo root).

    Returns:
        The directory listing.
    """
    full_path = os.path.join(WORK_DIR, path)
    if not os.path.isdir(full_path):
        return f"Not a directory: {path}"
    result = subprocess.run(
        ["find", ".", "-type", "f", "-not", "-path", "./.git/*"],
        capture_output=True, text=True, timeout=10, cwd=full_path,
    )
    return result.stdout or "Empty directory"


@tool
def git_commit_and_push(message: str) -> str:
    """Stage all changes, commit, and push to the remote.

    Args:
        message: The commit message.

    Returns:
        Success or error message.
    """
    result = subprocess.run(
        ["git", "add", "-A"],
        capture_output=True, text=True, timeout=10, cwd=WORK_DIR,
    )
    if result.returncode != 0:
        return f"Error staging: {result.stderr}"

    result = subprocess.run(
        ["git", "commit", "-m", message],
        capture_output=True, text=True, timeout=10, cwd=WORK_DIR,
    )
    if result.returncode != 0:
        return f"Error committing: {result.stderr}"

    result = subprocess.run(
        ["git", "push", "-u", "origin", "HEAD"],
        capture_output=True, text=True, timeout=30, cwd=WORK_DIR,
    )
    if result.returncode != 0:
        return f"Error pushing: {result.stderr}"
    return f"Committed and pushed: {message}"


@tool
def create_pull_request(title: str, body: str, issue_number: int = 0) -> str:
    """Create a GitHub pull request.

    Args:
        title: PR title.
        body: PR description/body in markdown.
        issue_number: Issue number to link (0 to skip).

    Returns:
        The PR URL or error message.
    """
    if issue_number > 0:
        body = f"{body}\n\nCloses #{issue_number}"
    result = subprocess.run(
        ["gh", "pr", "create", "--repo", REPO, "--title", title, "--body", body],
        capture_output=True, text=True, timeout=30, cwd=WORK_DIR,
    )
    if result.returncode != 0:
        return f"Error creating PR: {result.stderr}"
    return result.stdout.strip()


# ── Tool sets per agent ──────────────────────────────────────────────

github_tools = [
    list_github_issues, get_github_issue, clone_repo,
    git_create_branch, git_commit_and_push, create_pull_request,
]

coding_tools = [
    write_file, read_file, list_files,
]

qa_tools = [
    read_file, list_files,
]

# ── GitHub Agent: handles all git/gh operations ──────────────────────

github_agent = Agent(
    name="github_agent",
    model="anthropic/claude-sonnet-4-20250514",
    instructions=(
        "You are a GitHub operations specialist. You handle all git and "
        "GitHub CLI interactions.\n\n"
        "IMPORTANT: Read the conversation history carefully. If the "
        "conversation already contains messages from [coder] and "
        "[qa_tester] (especially 'ALL TESTS PASSED' or similar), then "
        "the code is already implemented and tested — you are in PHASE 2. "
        "Skip directly to step 6 below.\n\n"
        "PHASE 1 — SETUP (only if no [coder]/[qa_tester] messages exist):\n"
        "1. Use list_github_issues to see open issues\n"
        "2. Use get_github_issue to read the full details\n"
        "3. Use clone_repo to clone the repository\n"
        "4. Use git_create_branch to create a feature branch "
        "(e.g. 'feature/issue-N-short-description')\n"
        "5. Call transfer_to_coder with the issue details and what needs "
        "to be implemented.\n\n"
        "PHASE 2 — PR CREATION (conversation contains QA approval):\n"
        "6. Use git_commit_and_push to commit and push the changes\n"
        "7. Use create_pull_request to create the PR (include issue_number "
        "to auto-close)\n"
        "8. Output the PR URL as your final response. Do NOT call any "
        "transfer tool after this — the workflow ends automatically."
    ),
    tools=github_tools,
    thinking_budget_tokens=4096,
    max_tokens=16384,
)

# ── Coder: implements the fix ────────────────────────────────────────

coder = Agent(
    name="coder",
    model="anthropic/claude-sonnet-4-20250514",
    instructions=(
        "You are an expert developer. Write clean, well-structured code.\n\n"
        "WHEN YOU RECEIVE A TASK:\n"
        "1. Use list_files to understand the repo structure\n"
        "2. Write your code using write_file\n"
        "3. Execute your code to verify it works\n"
        "4. Call transfer_to_qa_tester for review\n\n"
        "IF QA REPORTS BUGS:\n"
        "5. Use read_file to review the current code\n"
        "6. Fix the issues using write_file\n"
        "7. Re-test\n"
        "8. Call transfer_to_qa_tester again\n\n"
        "IMPORTANT: You can ONLY use transfer_to_qa_tester. Do NOT call "
        "transfer_to_coding_team or transfer_to_github_agent.\n\n"
        "Always include ALL necessary code in each execution — every code "
        "block runs in an isolated environment. "
        f"The repo is cloned to {WORK_DIR}."
    ),
    tools=coding_tools,
    local_code_execution=True,
    thinking_budget_tokens=4096,
    max_tokens=16384,
)

# ── QA Tester: reviews code and runs tests ───────────────────────────

qa_tester = Agent(
    name="qa_tester",
    model="anthropic/claude-sonnet-4-20250514",
    instructions=(
        "You are a meticulous QA engineer. Review the code written by the "
        "coder for correctness, edge cases, and bugs.\n\n"
        "1. Use read_file to read the code that was written\n"
        "2. Execute test cases covering: normal inputs, edge cases (empty "
        "input, zero, negative numbers, None), and boundary conditions\n"
        "3. If you find ANY bugs:\n"
        "   → Call transfer_to_coder and describe the bugs clearly.\n"
        "4. If ALL tests pass:\n"
        "   → Call transfer_to_github_agent with a short QA approval "
        "summary so it can commit and create the PR.\n\n"
        "Always include ALL necessary code (imports, function definitions) "
        "in each execution — every code block runs in isolation.\n\n"
        "TRANSFER RULES (you MUST follow these exactly):\n"
        "  If you find bugs → call transfer_to_coder\n"
        "  If all tests pass → call transfer_to_github_agent\n"
        "  NEVER call transfer_to_coding_team (it will be rejected)"
    ),
    tools=qa_tools,
    local_code_execution=True,
    thinking_budget_tokens=4096,
    max_tokens=16384,
)

# ── Coding Team: swarm coordinator ───────────────────────────────────

coding_team = Agent(
    name="coding_team",
    model="anthropic/claude-sonnet-4-20250514",
    instructions=(
        "You are a coding team coordinator. Delegate the incoming request "
        "to github_agent to get started — it will pick an issue and set "
        "up the repo. Call transfer_to_github_agent now."
    ),
    agents=[github_agent, coder, qa_tester],
    strategy=Strategy.SWARM,
    handoffs=[
        OnTextMention(text="transfer_to_github_agent", target="github_agent"),
        OnTextMention(text="transfer_to_coder", target="coder"),
        OnTextMention(text="transfer_to_qa_tester", target="qa_tester"),
    ],
    allowed_transitions={
        "coding_team": ["github_agent"],
        "github_agent": ["coder"],
        "coder": ["qa_tester"],
        "qa_tester": ["coder", "github_agent"],
    },
    max_turns=30,
    timeout_seconds=900,
)

# ── Run ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    prompt = (
        "Pick an open issue from the GitHub repository, implement the "
        "feature or fix the bug, get it reviewed by QA, and create a PR."
    )

    print("=" * 60)
    print("  GitHub Coding Agent + QA Tester")
    print(f"  Repo: {REPO}")
    print(f"  Work dir: {WORK_DIR}")
    print("  coding_team → github_agent ↔ coder ↔ qa_tester (swarm)")
    print("=" * 60)
    print(f"\nPrompt: {prompt}\n")


    with AgentRuntime() as runtime:
        # Deploy to server. CLI alternative (recommended for CI/CD):
        #   agentspan deploy examples.60_github_coding_agent
        runtime.deploy(coding_team)
        runtime.serve(coding_team)

        # Quick test: uncomment below (and comment out serve) to run directly.
        # result = runtime.run(coding_team, prompt)

        # # Display output
        # output = result.output
        # skip_keys = {"finishReason", "rejectionReason", "is_transfer", "transfer_to"}
        # if isinstance(output, dict):
        #     for key, text in output.items():
        #         if key in skip_keys or not text:
        #             continue
        #         print(f"\n{'─' * 60}")
        #         print(f"  [{key}]")
        #         print(f"{'─' * 60}")
        #         print(text)
        # else:
        #     print(output)

        # print(f"\nFinish reason: {result.finish_reason}")
        # print(f"Workflow ID: {result.workflow_id}")

