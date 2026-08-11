"""Are this agent's own tool workers still polling?

Twice now the process stayed alive while individual SDK worker threads silently died.
Their task queues stopped being polled, so every triage forked its tool calls into a
black hole: the LLM ran, the FORK scheduled `get_incident_details` and
`get_alert_recurrence`, nothing ever claimed them, and the JOIN sat there until the
30-minute deadline killed the whole triage. The tasks show CANCELED having never
started. Observed gap: 2.1 days, 26+ consecutive dead triages, while `pull_pod_logs`
in the same process kept polling normally.

A guard inside the tool function cannot help — the tool never executes. It has to run
BEFORE the triage starts.

`lastPollTime` from /tasks/queue/polldata is the signal. Workers poll every 100ms, so
anything beyond a couple of minutes is unambiguous: nothing is home.
"""
from __future__ import annotations

# Workers poll at 100ms. A minute of silence is already thousands of missed polls;
# 120s leaves generous room for GC pauses and scheduler noise without being sloppy.
STALE_AFTER_S = 120

# The tools every triage calls first. If these are dead the triage cannot produce
# anything, so it is better not to start than to burn the deadline.
CRITICAL_TASK_TYPES = ("get_incident_details", "get_alert_recurrence")


def evaluate(poll_ages_s: dict[str, float | None], *, stale_after_s: int = STALE_AFTER_S,
             required: tuple[str, ...] = CRITICAL_TASK_TYPES) -> dict:
    """Decide whether a triage can usefully run.

    ``poll_ages_s`` maps task type -> seconds since last poll, or None when the server
    reports no poller at all. Distinguishing those two is the point: "never registered"
    and "registered but died" are different faults, and both differ from healthy.
    """
    dead, stale, healthy = [], [], []
    for task_type in required:
        age = poll_ages_s.get(task_type, "missing")
        if age == "missing" or age is None:
            dead.append(task_type)
        elif age > stale_after_s:
            stale.append({"task_type": task_type, "age_s": round(float(age))})
        else:
            healthy.append(task_type)

    ok = not dead and not stale
    return {
        "ok": ok,
        "healthy": healthy,
        "no_poller": dead,
        "stale": stale,
        "reason": _reason(ok, dead, stale, stale_after_s),
    }


def _reason(ok: bool, dead: list[str], stale: list[dict], stale_after_s: int) -> str:
    if ok:
        return "all required tool workers are polling"
    parts = []
    if dead:
        parts.append(f"no poller registered for {', '.join(dead)}")
    if stale:
        worst = max(stale, key=lambda s: s["age_s"])
        mins = worst["age_s"] / 60
        names = ", ".join(s["task_type"] for s in stale)
        parts.append(
            f"{names} last polled {mins:.0f} min ago (stale beyond {stale_after_s}s)"
        )
    return (
        "; ".join(parts)
        + ". The SDK worker thread(s) have died while the process stayed alive — tool "
          "tasks would be scheduled and never claimed, so the triage would time out "
          "having produced nothing. Restart the agent process to respawn the workers."
    )
