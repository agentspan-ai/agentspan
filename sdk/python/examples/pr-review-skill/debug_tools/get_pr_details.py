#!/usr/bin/env python3
"""Fetch pull request metadata from GitHub.

Usage: get_pr_details.py <repo> <pr_number>

Returns JSON with title, body, changed files, additions, deletions, author, branches.
"""
import json
import subprocess
import sys


def main(repo: str, pr_number: str) -> str:
    result = subprocess.run(
        [
            "gh", "pr", "view", pr_number,
            "--repo", repo,
            "--json", "number,title,body,files,additions,deletions,author,baseRefName,headRefName,state",
        ],
        capture_output=True,
        text=True,
        timeout=30,
    )
    if result.returncode != 0:
        return f"ERROR: {result.stderr.strip() or 'gh pr view failed'}"
    return result.stdout.strip()


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("ERROR: usage: get_pr_details.py <repo> <pr_number>", file=sys.stderr)
        sys.exit(1)
    print(main(sys.argv[1], sys.argv[2]))
