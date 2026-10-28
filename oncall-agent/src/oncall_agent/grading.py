"""Grade a triage answer against a ground-truth eval case, one dimension at a time.

Deterministic string checks only — no LLM judges anything (the human still scores
usefulness in the report). Each dimension returns its failures, so a regression shows
WHERE an answer got worse, not just that it did:

* format    — the mandated three lines (*Cause*, *Action*, *Evidence*) and nothing more
* cause     — the Cause line names the known root cause (``cause_any``), and the whole
              answer still carries the older whole-text checks (``must_mention_any``)
* action    — the Action line says the right thing to do (``action_any``)
* evidence  — the Evidence line cites something concrete (a time or a number)
* forbidden — none of ``must_not_mention`` (wrong causes, unsafe advice)

``*_any`` fields are lists of groups; each group passes when ANY of its terms appears.
"""
from __future__ import annotations

import re

SECTIONS = ("cause", "action", "evidence")
MAX_LINES = 3
MAX_CHARS = 1200
_HEAD = re.compile(r"^\s*\*(cause|action|evidence)\*\s*:\s*", re.I)


def sections(summary: str) -> dict[str, str]:
    """The text of each ``*Cause*: / *Action*: / *Evidence*:`` section (continuation lines included)."""
    found: dict[str, str] = {}
    current = None
    for line in summary.splitlines():
        m = _HEAD.match(line)
        if m:
            current = m.group(1).lower()
            found[current] = line[m.end():].strip()
        elif current and line.strip():
            found[current] += " " + line.strip()
    return found


def _missing(groups: list[list[str]], text: str) -> list[str]:
    text = text.lower()
    return [f"mentions none of {g}" for g in groups if not any(t.lower() in text for t in g)]


def grade(case: dict, summary: str) -> dict[str, list[str]]:
    """Failures per dimension (empty lists everywhere = pass)."""
    parts = sections(summary)
    lines = [l for l in summary.splitlines() if l.strip()]
    fmt = [f"no *{s.capitalize()}* line" for s in SECTIONS if not parts.get(s)]
    if len(lines) > MAX_LINES:
        fmt.append(f"{len(lines)} lines (max {MAX_LINES})")
    if len(summary) > MAX_CHARS:
        fmt.append(f"{len(summary)} chars (max {MAX_CHARS})")
    evidence = parts.get("evidence", "")
    return {
        "format": fmt,
        "cause": _missing(case.get("cause_any", []), parts.get("cause", ""))
                 + _missing(case.get("must_mention_any", []), summary),
        "action": _missing(case.get("action_any", []), parts.get("action", "")),
        "evidence": [] if not evidence or re.search(r"\d", evidence) else ["cites no time or number"],
        "forbidden": [f"says '{t}'" for t in case.get("must_not_mention", []) if t.lower() in summary.lower()],
    }


def passed(result: dict[str, list[str]]) -> bool:
    return not any(result.values())


def describe(result: dict[str, list[str]]) -> str:
    bad = [f"{dim}: {'; '.join(f)}" for dim, f in result.items() if f]
    return "PASS" if not bad else "FAIL — " + " | ".join(bad)
