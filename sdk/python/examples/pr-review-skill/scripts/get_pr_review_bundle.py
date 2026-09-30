#!/usr/bin/env python3
"""Fetch a token-bounded PR review bundle.

Usage: get_pr_review_bundle.py <repo> <pr_number>

Returns PR metadata, the changed-file list, and compact diffs for the highest-risk files.
This is the primary evidence-gathering tool for the PR reviewer skill.
"""
import json
import os
import subprocess
import sys
from typing import Any

MAX_BODY_CHARS = 1_200
MAX_CHANGED_FILES = 80
MAX_SELECTED_FILES = 4
MAX_FILE_DIFF_CHARS = 4_000
MAX_TOTAL_DIFF_CHARS = 16_000
CONTEXT_FILE = ".agentspan/pr-review-context.md"
MAX_CONTEXT_CHARS = 3_000

SOURCE_EXTENSIONS = {
    ".java", ".py", ".go", ".ts", ".tsx", ".js", ".jsx", ".kt", ".kts",
    ".scala", ".rb", ".rs", ".cs", ".cpp", ".c", ".h", ".hpp", ".sql",
    ".yaml", ".yml", ".json", ".xml", ".gradle", ".properties",
}
LOW_VALUE_PARTS = {
    "test", "tests", "__tests__", "spec", "specs", "fixtures", "fixture",
    "docs", "doc", "examples", "generated", "vendor", "dist", "build",
}


def _run_gh(args: list[str], timeout: int = 60) -> str:
    result = subprocess.run(
        ["gh", *args],
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or f"gh {' '.join(args)} failed")
    return result.stdout


def _file_path(file_info: dict[str, Any]) -> str:
    return str(file_info.get("path") or file_info.get("filename") or file_info.get("name") or "")


def _extension(path: str) -> str:
    lowered = path.lower()
    if lowered.endswith(".gradle"):
        return ".gradle"
    dot = lowered.rfind(".")
    return lowered[dot:] if dot >= 0 else ""


def _is_low_value(path: str) -> bool:
    parts = {part.lower() for part in path.replace("\\", "/").split("/")}
    lowered = path.lower()
    return bool(parts & LOW_VALUE_PARTS) or lowered.endswith(
        (".md", ".lock", ".png", ".jpg", ".jpeg", ".gif", ".svg", ".snap")
    )


def _score_file(file_info: dict[str, Any]) -> tuple[int, str]:
    path = _file_path(file_info)
    changes = int(file_info.get("additions") or 0) + int(file_info.get("deletions") or 0)
    ext = _extension(path)
    score = min(changes, 300)
    reasons = []

    if ext in SOURCE_EXTENSIONS:
        score += 200
        reasons.append("source/config")
    if _is_low_value(path):
        score -= 150
        reasons.append("lower-priority path")
    if changes == 0:
        score -= 50
    return score, ", ".join(reasons) or "changed file"


def _extract_diff_sections(diff: str) -> dict[str, str]:
    sections: dict[str, str] = {}
    chunks = diff.split("\ndiff --git ")
    for index, chunk in enumerate(chunks):
        section = chunk if index == 0 else "diff --git " + chunk
        lines = section.splitlines()
        if not lines:
            continue
        header_parts = lines[0].split()
        if len(header_parts) < 4 or header_parts[0:2] != ["diff", "--git"]:
            continue
        for raw_path in (header_parts[2], header_parts[3]):
            if raw_path.startswith(("a/", "b/")):
                sections[raw_path[2:]] = section
    return sections


def _compact_diff(section: str) -> str:
    compact_lines = []
    context_after_hunk = 0
    for line in section.splitlines():
        if line.startswith(("diff --git", "index ", "--- ", "+++ ", "@@")):
            compact_lines.append(line)
            context_after_hunk = 2 if line.startswith("@@") else 0
            continue
        if line.startswith(("+", "-")):
            compact_lines.append(line)
            continue
        if context_after_hunk > 0 and line.startswith(" "):
            compact_lines.append(line)
            context_after_hunk -= 1
    compact = "\n".join(compact_lines)
    if len(compact) > MAX_FILE_DIFF_CHARS:
        compact = compact[:MAX_FILE_DIFF_CHARS] + f"\n[... compact file diff truncated at {MAX_FILE_DIFF_CHARS} chars ...]"
    return compact


def _format_file(file_info: dict[str, Any]) -> str:
    path = _file_path(file_info)
    status = file_info.get("status") or file_info.get("changeType") or "changed"
    additions = file_info.get("additions", 0)
    deletions = file_info.get("deletions", 0)
    return f"- {path} ({status}, +{additions}/-{deletions})"


def main(repo: str, pr_number: str, repo_path: str = ".") -> str:
    try:
        details_raw = _run_gh([
            "pr", "view", pr_number,
            "--repo", repo,
            "--json", "number,title,body,files,additions,deletions,author,baseRefName,headRefName,state",
        ], timeout=30)
        details = json.loads(details_raw)
        diff = _run_gh(["pr", "diff", pr_number, "--repo", repo], timeout=60)
    except Exception as exc:
        return f"ERROR: {exc}"

    files = details.get("files") or []
    scored = sorted(files, key=lambda item: _score_file(item)[0], reverse=True)
    selected = scored[:MAX_SELECTED_FILES]
    sections = _extract_diff_sections(diff)

    body = (details.get("body") or "").strip()
    if len(body) > MAX_BODY_CHARS:
        body = body[:MAX_BODY_CHARS] + f"\n[... PR body truncated at {MAX_BODY_CHARS} chars ...]"

    lines = [
        "# PR Review Bundle",
        "",
        f"Repo: {repo}",
        f"PR: #{details.get('number', pr_number)} - {details.get('title', '')}",
        f"State: {details.get('state', '')}",
        f"Author: {(details.get('author') or {}).get('login', '')}",
        f"Branch: {details.get('headRefName', '')} -> {details.get('baseRefName', '')}",
        f"Totals: {len(files)} files, +{details.get('additions', 0)}/-{details.get('deletions', 0)}",
        "",
        "## PR Body",
        body or "(empty)",
        "",
        "## Changed Files",
    ]

    for file_info in files[:MAX_CHANGED_FILES]:
        lines.append(_format_file(file_info))
    if len(files) > MAX_CHANGED_FILES:
        lines.append(f"- ... {len(files) - MAX_CHANGED_FILES} more files omitted from list")

    lines.extend([
        "",
        "## Selected Compact Diffs",
        (
            "These are the highest-risk changed files selected automatically. "
            "Review from this evidence; do not fetch more diffs unless this section is empty."
        ),
    ])

    total_diff_chars = 0
    for file_info in selected:
        path = _file_path(file_info)
        status = (file_info.get("status") or file_info.get("changeType") or "").lower()
        is_added = status in ("added", "a")
        score, reason = _score_file(file_info)
        section = sections.get(path)
        if not section:
            continue
        compact = _compact_diff(section)
        remaining = MAX_TOTAL_DIFF_CHARS - total_diff_chars
        if remaining <= 0:
            lines.append("\n[... total diff budget exhausted ...]")
            break
        if len(compact) > remaining:
            compact = compact[:remaining] + f"\n[... total diff budget exhausted at {MAX_TOTAL_DIFF_CHARS} chars ...]"
        total_diff_chars += len(compact)
        header = [
            "",
            f"### {path}",
            f"Selection reason: {reason}; score={score}",
        ]
        if is_added:
            header.append(
                "⚠️  ADDED FILE — this file is brand-new and does NOT exist in the "
                "checked-out repo. Do NOT call grep_in_file on it; the diff below is "
                "its complete content."
            )
        lines.extend(header + ["```diff", compact, "```"])

    if total_diff_chars == 0:
        lines.append("No textual diff sections were available in the selected files.")

    context_path = os.path.join(repo_path, CONTEXT_FILE)
    if os.path.isfile(context_path):
        try:
            ctx = open(context_path, encoding="utf-8", errors="replace").read().strip()
            if len(ctx) > MAX_CONTEXT_CHARS:
                ctx = ctx[:MAX_CONTEXT_CHARS] + f"\n[... context truncated at {MAX_CONTEXT_CHARS} chars ...]"
            lines.extend(["", "## Repo Context", ctx])
        except OSError:
            pass

    lines.extend([
        "",
        "## Reviewer Instruction",
        "Write the review from this bundle. Use at most one grep_in_file call only to verify "
        "a CRITICAL finding on a MODIFIED file. Never call grep_in_file on any file marked "
        "⚠️ ADDED FILE above — those files do not exist on disk.",
    ])
    return "\n".join(lines)


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("ERROR: usage: get_pr_review_bundle.py <repo> <pr_number> [repo_path]", file=sys.stderr)
        sys.exit(1)
    _repo_path = sys.argv[3] if len(sys.argv) > 3 else "."
    print(main(sys.argv[1], sys.argv[2], _repo_path))
