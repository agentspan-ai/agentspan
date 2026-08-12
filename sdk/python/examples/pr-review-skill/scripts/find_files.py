#!/usr/bin/env python3
"""Find files matching a glob pattern within the repository.

Usage: find_files.py <repo_path> <glob_pattern>

repo_path:    path to the repo root on disk (e.g. "." or "/tmp/myrepo")
glob_pattern: pattern relative to repo_path (e.g. "src/providers/**/*.py")

Returns a newline-separated list of matching paths (relative to repo_path).
Returns an empty string if no files match.
"""
import glob
import os
import sys
from pathlib import Path

MAX_RESULTS = 200


def main(repo_path: str, pattern: str) -> str:
    repo_abs = Path(repo_path).expanduser().resolve()
    if not repo_abs.is_dir():
        return f"ERROR: repo_path not found: {repo_path}"
    if os.path.isabs(pattern) or ".." in Path(pattern).parts:
        return "ERROR: pattern must stay inside the repository"

    matches = []
    for match in glob.glob(pattern, root_dir=repo_abs, recursive=True):
        file_abs = (repo_abs / match).resolve()
        try:
            relative = file_abs.relative_to(repo_abs)
        except ValueError:
            continue
        if file_abs.is_file():
            matches.append(str(relative))
    matches = sorted(matches)[:MAX_RESULTS]

    if not matches:
        return f"No files found matching: {pattern}"
    return "\n".join(matches)


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("ERROR: usage: find_files.py <repo_path> <glob_pattern>", file=sys.stderr)
        sys.exit(1)
    print(main(sys.argv[1], sys.argv[2]))
