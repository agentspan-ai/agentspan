#!/usr/bin/env python3
"""Search for a pattern inside a file and return matching lines with context.

Usage: grep_in_file.py <repo_path> <file_path> <search_term> [context_lines]

repo_path:     path to the repo root on disk (e.g. "." or "/tmp/myrepo")
file_path:     path to the file relative to repo_path
search_term:   string to search for (case-insensitive)
context_lines: number of lines before/after each match to include (default: 10)

Returns matching lines with surrounding context, prefixed by line numbers.
Returns "No matches found" if the term is not in the file.
Useful for reading only the relevant part of a large file instead of the whole thing.
"""
import sys
from pathlib import Path

DEFAULT_CONTEXT = 8    # tighter default — enough to see a method signature + body
MAX_OUTPUT_CHARS = 6_000   # ~1.5k tokens per grep call


def main(repo_path: str, file_path: str, search_term: str, context_lines: int = DEFAULT_CONTEXT) -> str:
    repo_abs = Path(repo_path).expanduser().resolve()
    file_abs = (repo_abs / file_path).resolve()

    try:
        file_abs.relative_to(repo_abs)
    except ValueError:
        return f"ERROR: path '{file_path}' is outside the repository"
    if not file_abs.is_file():
        return f"ERROR: file not found: {file_path}"

    try:
        lines = file_abs.read_text(encoding="utf-8", errors="replace").splitlines(keepends=True)
    except OSError as e:
        return f"ERROR: could not read file: {e}"

    # Support "|" as OR between multiple terms (e.g. "foo|bar|baz")
    # Also strip shell escape sequences like \\ that agents sometimes add
    raw_terms = search_term.replace("\\|", "|").split("|")
    terms = [t.strip().lower() for t in raw_terms if t.strip()]

    if not terms:
        return "ERROR: search_term is empty"

    # Find all line indices that match ANY of the terms
    def line_matches(line: str) -> bool:
        line_lower = line.lower()
        return any(t in line_lower for t in terms)

    match_indices = [i for i, line in enumerate(lines) if line_matches(line)]

    if not match_indices:
        return f"No matches found for '{search_term}' in {file_path}"

    # Expand each match to include context lines, then merge overlapping ranges
    ranges = []
    for idx in match_indices:
        start = max(0, idx - context_lines)
        end = min(len(lines) - 1, idx + context_lines)
        if ranges and start <= ranges[-1][1] + 1:
            ranges[-1] = (ranges[-1][0], end)  # merge
        else:
            ranges.append((start, end))

    # Build output
    chunks = []
    for start, end in ranges:
        chunk_lines = []
        for i in range(start, end + 1):
            prefix = ">>>" if line_matches(lines[i]) else "   "
            chunk_lines.append(f"{prefix} {i + 1:4d}: {lines[i].rstrip()}")
        chunks.append("\n".join(chunk_lines))

    output = f"\n--- {file_path} (matches for '{search_term}') ---\n\n"
    output += "\n...\n".join(chunks)
    terms_display = " | ".join(terms)
    output += f"\n\n({len(match_indices)} match(es) for '{terms_display}' in {len(lines)} lines total)"

    if len(output) > MAX_OUTPUT_CHARS:
        output = output[:MAX_OUTPUT_CHARS] + "\n\n[... output truncated ...]"

    return output


if __name__ == "__main__":
    if len(sys.argv) < 4:
        print("ERROR: usage: grep_in_file.py <repo_path> <file_path> <search_term> [context_lines]", file=sys.stderr)
        sys.exit(1)
    ctx = int(sys.argv[4]) if len(sys.argv) > 4 else DEFAULT_CONTEXT
    print(main(sys.argv[1], sys.argv[2], sys.argv[3], ctx))
