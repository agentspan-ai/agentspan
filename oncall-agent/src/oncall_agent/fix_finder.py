"""General: given code the agent OBSERVED, find fixes the running version is missing.

known_issues.py is a curated table — it only recognises bugs a human already wrote down.
This is the general mechanism, and it needs no prior knowledge of the bug at all:

    observed frame/class  ->  source file  ->  git log <running-tag>..main -- <file>

Everything the agent sees already contains code identifiers: hot RUNNABLE frames, the
class in a log line, the exception in a stack. Resolve one to a path and git answers
"what have we fixed in this code that you do not have", including the PR numbers from
the merge commits.

Worked end to end for the sweeper case knowing only the frame name `OrkesWorkflowSweeper`
and the tag `v5.4.3` — it surfaced the WAIT/EVENT defer work and PR #3775 unaided.

Pure parsing/ranking here; the git calls live in the tool.
"""
from __future__ import annotations

import re

_PR = re.compile(r"Merge pull request #(\d+)")
# Conventional-commit prefixes that indicate a corrective change, best first.
_FIX_RANK = ("fix(", "fix:", "perf(", "perf:", "refactor(", "revert(")
_TICKET = re.compile(r"\b([A-Z]{2,}-\d+)\b")


def parse_log(lines: list[str]) -> list[dict]:
    """`git log --oneline` lines -> [{sha, subject, pr, ticket, is_fix}]."""
    out = []
    for raw in lines:
        raw = raw.strip()
        if not raw:
            continue
        sha, _, subject = raw.partition(" ")
        if not subject:
            continue
        pr = _PR.search(subject)
        ticket = _TICKET.search(subject)
        out.append({
            "sha": sha,
            "subject": subject,
            "pr": f"#{pr.group(1)}" if pr else None,
            "ticket": ticket.group(1) if ticket else None,
            "is_fix": subject.lower().startswith(_FIX_RANK),
        })
    return out


def rank_candidates(commits: list[dict], top: int = 8) -> list[dict]:
    """Fix-shaped commits first, then anything with a PR or ticket reference."""
    def score(c: dict) -> tuple:
        return (0 if c["is_fix"] else 1, 0 if (c["pr"] or c["ticket"]) else 1)
    return sorted(commits, key=score)[:top]


def build_report(symbol: str, paths: list[str], version: str | None,
                 commits: list[dict], merges: list[dict], top: int = 8) -> dict:
    ranked = rank_candidates(commits, top=top)
    prs = sorted({m["pr"] for m in merges if m["pr"]},
                 key=lambda p: -int(p.lstrip("#")))
    fixes = [c for c in commits if c["is_fix"]]
    return {
        "symbol": symbol,
        "resolved_paths": paths,
        "running_version": version,
        "commits_missing": len(commits),
        "fix_commits_missing": len(fixes),
        "pull_requests": prs[:top],
        "candidates": ranked,
        "verdict": _verdict(symbol, version, commits, fixes, prs),
    }


def _verdict(symbol: str, version: str | None, commits: list[dict],
             fixes: list[dict], prs: list[str]) -> str:
    if version is None:
        return (f"Running version could not be determined, so 'missing fixes' for {symbol} "
                "cannot be computed. Do not treat that as 'up to date'.")
    if not commits:
        return (f"No commits touching {symbol} exist upstream that {version} lacks — this code "
                "is current. The cause is NOT a known-and-fixed bug here; diagnose it fresh.")
    head = fixes[0]["subject"] if fixes else commits[0]["subject"]
    pr_txt = f" ({', '.join(prs[:3])})" if prs else ""
    return (f"{len(commits)} upstream commit(s) touch {symbol} that {version} does NOT have, "
            f"{len(fixes)} of them fix-shaped{pr_txt}. Most relevant: \"{head}\". "
            "Read these before diagnosing from scratch — the bug may already be fixed.")
