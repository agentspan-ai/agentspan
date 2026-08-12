#!/usr/bin/env python3
"""Read the content of a file from the checked-out repository.

Usage: get_file_content.py <repo_path> <relative_file_path>

repo_path:          path to the repo root on disk (e.g. "." or "/tmp/myrepo")
relative_file_path: path to the file relative to repo_path (e.g. "src/core/provider.py")

Returns the file content. Truncated to 8000 chars if very large.
"""
import sys
from pathlib import Path

MAX_FILE_CHARS = 8_000   # ~2k tokens — use grep_in_file for surgical reads instead


def main(repo_path: str, file_path: str) -> str:
    repo_abs = Path(repo_path).expanduser().resolve()
    file_abs = (repo_abs / file_path).resolve()

    try:
        file_abs.relative_to(repo_abs)
    except ValueError:
        return f"ERROR: path '{file_path}' is outside the repository"

    if not file_abs.is_file():
        return f"ERROR: file not found: {file_path}"

    try:
        content = file_abs.read_text(encoding="utf-8", errors="replace")
    except OSError as e:
        return f"ERROR: could not read file: {e}"

    if len(content) > MAX_FILE_CHARS:
        content = content[:MAX_FILE_CHARS] + f"\n\n[... file truncated at {MAX_FILE_CHARS} chars ...]"
    return content


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("ERROR: usage: get_file_content.py <repo_path> <file_path>", file=sys.stderr)
        sys.exit(1)
    print(main(sys.argv[1], sys.argv[2]))
