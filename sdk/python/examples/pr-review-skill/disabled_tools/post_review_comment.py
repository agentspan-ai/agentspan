#!/usr/bin/env python3
"""Post a review comment on a GitHub pull request.

Usage: post_review_comment.py <repo> <pr_number> <comment>

repo:       GitHub repo in owner/repo format
pr_number:  Pull request number
comment:    Review text (quoted if it contains spaces or newlines)

Prints "OK: comment posted." on success, "ERROR: ..." on failure.
"""
import subprocess
import sys


def main(repo: str, pr_number: str, comment: str) -> str:
    if not comment.strip():
        return "ERROR: comment is empty"

    result = subprocess.run(
        ["gh", "pr", "comment", pr_number, "--repo", repo, "--body", comment],
        capture_output=True,
        text=True,
        timeout=30,
    )
    if result.returncode != 0:
        return f"ERROR: {result.stderr.strip() or 'gh pr comment failed'}"
    return "OK: comment posted."


if __name__ == "__main__":
    if len(sys.argv) < 4:
        print("ERROR: usage: post_review_comment.py <repo> <pr_number> <comment>", file=sys.stderr)
        sys.exit(1)
    # argv[3:] joined to allow unquoted multi-word comments from CLI
    comment = " ".join(sys.argv[3:])
    print(main(sys.argv[1], sys.argv[2], comment))
