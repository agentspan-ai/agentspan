#!/usr/bin/env python3
"""Fetch the full unified diff for a pull request.

Usage: get_pr_diff.py <repo> <pr_number>

Returns the diff as a string. Truncated to 30000 chars if very large.
"""
import subprocess
import sys

MAX_DIFF_CHARS = 30_000   # ~7.5k tokens — enough for most PRs without blowing the context window


def main(repo: str, pr_number: str) -> str:
    result = subprocess.run(
        ["gh", "pr", "diff", pr_number, "--repo", repo],
        capture_output=True,
        text=True,
        timeout=60,
    )
    if result.returncode != 0:
        return f"ERROR: {result.stderr.strip() or 'gh pr diff failed'}"

    diff = result.stdout
    if len(diff) > MAX_DIFF_CHARS:
        diff = diff[:MAX_DIFF_CHARS] + f"\n\n[... diff truncated at {MAX_DIFF_CHARS} chars ...]"
    return diff


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("ERROR: usage: get_pr_diff.py <repo> <pr_number>", file=sys.stderr)
        sys.exit(1)
    print(main(sys.argv[1], sys.argv[2]))
