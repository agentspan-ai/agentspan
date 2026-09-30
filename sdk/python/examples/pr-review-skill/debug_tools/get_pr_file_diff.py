#!/usr/bin/env python3
"""Fetch the unified diff section for one file in a pull request.

Usage: get_pr_file_diff.py <repo> <pr_number> <file_path>

Returns only the requested file's diff. Truncated to 12000 chars if very large.
"""
import subprocess
import sys

MAX_FILE_DIFF_CHARS = 12_000


def _section_matches(header: str, file_path: str) -> bool:
    target_a = f"a/{file_path}"
    target_b = f"b/{file_path}"
    parts = header.split()
    if len(parts) < 4 or parts[0:2] != ["diff", "--git"]:
        return False
    return parts[2] == target_a or parts[3] == target_b


def main(repo: str, pr_number: str, file_path: str) -> str:
    if file_path.startswith("/") or ".." in file_path.split("/"):
        return "ERROR: file_path must be a repository-relative path"

    result = subprocess.run(
        ["gh", "pr", "diff", pr_number, "--repo", repo],
        capture_output=True,
        text=True,
        timeout=60,
    )
    if result.returncode != 0:
        return f"ERROR: {result.stderr.strip() or 'gh pr diff failed'}"

    sections = result.stdout.split("\ndiff --git ")
    for index, section in enumerate(sections):
        normalized = section if index == 0 else "diff --git " + section
        first_line = normalized.splitlines()[0] if normalized.splitlines() else ""
        if _section_matches(first_line, file_path):
            if len(normalized) > MAX_FILE_DIFF_CHARS:
                normalized = (
                    normalized[:MAX_FILE_DIFF_CHARS]
                    + f"\n\n[... file diff truncated at {MAX_FILE_DIFF_CHARS} chars ...]"
                )
            return normalized

    return f"ERROR: no diff found for file: {file_path}"


if __name__ == "__main__":
    if len(sys.argv) < 4:
        print("ERROR: usage: get_pr_file_diff.py <repo> <pr_number> <file_path>", file=sys.stderr)
        sys.exit(1)
    print(main(sys.argv[1], sys.argv[2], sys.argv[3]))
