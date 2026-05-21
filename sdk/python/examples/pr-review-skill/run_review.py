#!/usr/bin/env python3
# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""PR Review Skill — entry point.

Loads the pr-reviewer skill and runs it against a pull request.
The agent reads the PR diff + navigates the checked-out repo to understand
existing patterns before producing a structured review.

Usage:
    python run_review.py <pr_number> <repo>

    pr_number:  GitHub PR number (e.g. 42)
    repo:       GitHub repo in owner/repo format (e.g. orkes-saas/orkes-saas)

Environment:
    AGENTSPAN_SERVER_URL   AgentSpan server URL (default: http://localhost:6767)
    AGENTSPAN_LLM_MODEL    Model override (default: anthropic/claude-sonnet-4-6)
    GH_TOKEN               GitHub token — must also be stored via:
                           agentspan credentials set GH_TOKEN <token>

Examples:
    python run_review.py 42 orkes-saas/orkes-saas
    AGENTSPAN_LLM_MODEL=openai/gpt-4o python run_review.py 42 orkes-saas/orkes-saas

GitHub Actions:
    See .github/workflows/pr-review.yml for the CI integration.
"""

import os
import sys
from pathlib import Path

from agentspan.agents import AgentRuntime, skill

SKILL_DIR = Path(__file__).parent
DEFAULT_MODEL = os.environ.get("AGENTSPAN_LLM_MODEL", "anthropic/claude-sonnet-4-6")
TIMEOUT_MS = 300_000  # 5 minutes
REVIEW_MAX_TURNS = int(os.environ.get("AGENTSPAN_REVIEW_MAX_TURNS", "6"))
REVIEW_MAX_TOKENS = int(os.environ.get("AGENTSPAN_REVIEW_MAX_TOKENS", "3000"))


def run_review(pr_number: int, repo: str, repo_path: str = ".") -> int:
    """Run the PR review skill.

    Returns 0 on success, 1 on failure.
    """
    print(f"Reviewing PR #{pr_number} in {repo}")
    print(f"Model:     {DEFAULT_MODEL}")
    print(f"Repo path: {os.path.realpath(repo_path)}")
    print(f"Limits:    {REVIEW_MAX_TURNS} turns, {REVIEW_MAX_TOKENS} completion tokens")
    print()

    reviewer = skill(
        SKILL_DIR,
        model=DEFAULT_MODEL,
        params={
            "repo": repo,
            "repo_path": os.path.realpath(repo_path),
        },
    )
    reviewer.credentials = ["GH_TOKEN"]
    reviewer.timeout_seconds = TIMEOUT_MS // 1000
    reviewer.max_turns = REVIEW_MAX_TURNS
    reviewer.max_tokens = REVIEW_MAX_TOKENS

    with AgentRuntime() as rt:
        result = rt.run(
            reviewer,
            (
                f"Review PR #{pr_number} in {repo}. "
                f"The repository is checked out at: {os.path.realpath(repo_path)}"
            ),
            timeout=TIMEOUT_MS,
        )

    result.print_result()

    if result.is_failed:
        print(f"\nReview failed: {result.error}", file=sys.stderr)
        return 1

    return 0


def main() -> None:
    if len(sys.argv) < 3:
        print("Usage: run_review.py <pr_number> <repo>", file=sys.stderr)
        print("       e.g. run_review.py 42 orkes-saas/orkes-saas", file=sys.stderr)
        sys.exit(1)

    try:
        pr_number = int(sys.argv[1])
    except ValueError:
        print(f"ERROR: pr_number must be an integer, got: {sys.argv[1]}", file=sys.stderr)
        sys.exit(1)

    repo = sys.argv[2]
    # repo_path defaults to CWD — in GHA the repo is checked out there
    repo_path = sys.argv[3] if len(sys.argv) > 3 else "."

    sys.exit(run_review(pr_number, repo, repo_path))


if __name__ == "__main__":
    main()
