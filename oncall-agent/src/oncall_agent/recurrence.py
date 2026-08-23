"""Alert recurrence classification.

The on-call agent's biggest blind spot was treating every alert as a fresh
incident. A human on-call asks first: *is this new, or has it been firing for a
while?* — because a one-off spike is an incident, but an alert that fires on a
third of recent health-checks is a tolerated/standing capacity problem, and the
response is completely different.

This module holds the PURE classifier: given the recent health_check runs for a
single cluster (already filtered upstream by the unique clusterId) plus a short
signature identifying the alert TYPE, decide NEW vs RECURRING and quantify it.

Deliberately count-based over a bounded, recent window — no LLM, no network here,
so it is trivially testable. Two hard truths this encodes (both learned the hard
way): Conductor's search index is retention-bound (a few days), so the window is a
*ceiling* and the true first-fire may predate it — say so, and route onset
questions to Slack/metrics rather than under-reporting it.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime

# Fired on >= this fraction of the recent window => a standing/chronic condition,
# not an intermittent blip. 0.2 == "one in five recent checks or more".
_CHRONIC_FRACTION = 0.2
_MS_PER_HOUR = 3_600_000.0


def _to_ms(value) -> int | None:
    """Coerce a start_time to epoch ms. The Conductor search summary returns it as
    an ISO-8601 string (e.g. ``2026-07-03T07:02:03.661Z``), but callers/tests may
    pass epoch ms directly — accept both."""
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return int(value)
    s = str(value).strip()
    if not s:
        return None
    if s.isdigit():
        return int(s)
    try:
        return int(datetime.fromisoformat(s.replace("Z", "+00:00")).timestamp() * 1000)
    except ValueError:
        return None


@dataclass
class RecurrenceReport:
    verdict: str  # "NEW" | "RECURRING" | "NO_PRIOR_MATCH"
    chronic: bool
    matched_count: int
    sample_size: int
    failing_count: int  # runs in the window that failed with ANY alert
    fraction: float  # matched / sample_size
    fraction_of_failing: float  # matched / failing_count — the on-call ratio
    first_seen_ms: int | None  # earliest matched start_time IN THE WINDOW
    last_seen_ms: int | None
    span_hours: float  # last_seen - first_seen, in hours
    caveat: str
    summary: str = field(default="")

    def as_dict(self) -> dict:
        return {
            "verdict": self.verdict,
            "chronic": self.chronic,
            "matchedCount": self.matched_count,
            "sampleSize": self.sample_size,
            "failingCount": self.failing_count,
            "firedFraction": round(self.fraction, 3),
            "fractionOfFailingChecks": round(self.fraction_of_failing, 3),
            "firstSeenMsInWindow": self.first_seen_ms,
            "lastSeenMsInWindow": self.last_seen_ms,
            "spanHours": round(self.span_hours, 1),
            "caveat": self.caveat,
            "summary": self.summary,
        }


def _tokens(text: str) -> set[str]:
    """Lowercase word tokens, with pure numbers dropped (they vary per firing)."""
    words = re.split(r"[^a-z0-9.]+", text.lower())
    return {w for w in words if w and not re.fullmatch(r"[\d.]+%?", w)}


def summarize_recurrence(runs: list[dict], alert_signature: str) -> RecurrenceReport:
    """Classify how often ``alert_signature`` appears across recent cluster runs.

    Args:
        runs: recent health_check runs for ONE cluster, each a dict with
            ``reason`` (the alert text / reasonForIncompletion, may be None) and
            ``start_time`` (epoch ms, may be None). Order does not matter.
        alert_signature: a short, stable phrase identifying the alert TYPE — e.g.
            "Conductor Server CPU usage", "Redis instance is at", "Pod Failed".

    Matching is TOKEN-based, not substring: a run matches when every significant
    word of the signature appears as a word in its reason, in any position.
    Substring matching failed live (2026-07-22): the signature "Pod Failed" never
    matched "Pod orkes-agent-…-shldc Failed" because the pod name sits between
    the words, so a 6×/day flapper was reported as first-seen/NEW. Numbers are
    ignored on both sides — percentages and counts vary per firing.
    """
    sig_tokens = _tokens(alert_signature or "")
    sig = bool(sig_tokens)
    sample_size = len(runs)

    matched = [
        r
        for r in runs
        if sig and sig_tokens <= _tokens(str(r.get("reason") or ""))
    ]
    matched_count = len(matched)
    fraction = (matched_count / sample_size) if sample_size else 0.0
    failing_count = sum(1 for r in runs if str(r.get("reason") or "").strip())
    fraction_of_failing = (matched_count / failing_count) if failing_count else 0.0

    stamps = [ms for r in matched if (ms := _to_ms(r.get("start_time"))) is not None]
    first_seen = min(stamps) if stamps else None
    last_seen = max(stamps) if stamps else None
    span_hours = (
        (last_seen - first_seen) / _MS_PER_HOUR
        if first_seen is not None and last_seen is not None
        else 0.0
    )

    if not sig or matched_count == 0:
        verdict = "NO_PRIOR_MATCH"
    elif matched_count <= 1:
        # Only the current firing itself shows up in the window.
        verdict = "NEW"
    else:
        verdict = "RECURRING"

    chronic = verdict == "RECURRING" and fraction >= _CHRONIC_FRACTION

    caveat = (
        "Window is bounded by Conductor's search retention (a few days); the true "
        "first-fire may predate it. Confirm real onset via the Slack alert channel "
        "or Prometheus, not this count."
    )

    if verdict == "NEW":
        summary = (
            f"NEW: this alert type appears in only {matched_count} of the last "
            f"{sample_size} health-checks for this cluster — treat as a fresh incident."
        )
    elif verdict == "RECURRING":
        kind = "CHRONIC/standing" if chronic else "recurring/intermittent"
        summary = (
            f"{kind.upper()}: fired on {matched_count} of the last {sample_size} "
            f"health-checks — and {matched_count} of the {failing_count} failing "
            f"checks ({fraction_of_failing:.0%} of failures) — spanning "
            f"~{span_hours:.0f}h within the search window. NOT a fresh incident."
        )
    else:
        summary = (
            f"No prior firings of this alert signature found in the last {sample_size} "
            f"checks (signature may be too specific, or genuinely first-seen)."
        )

    return RecurrenceReport(
        verdict=verdict,
        chronic=chronic,
        matched_count=matched_count,
        sample_size=sample_size,
        failing_count=failing_count,
        fraction=fraction,
        fraction_of_failing=fraction_of_failing,
        first_seen_ms=first_seen,
        last_seen_ms=last_seen,
        span_hours=span_hours,
        caveat=caveat,
        summary=summary,
    )
