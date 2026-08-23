"""Is the sweeper doing necessary work, or spinning on workflows that can never advance?

Derived from OrkesWorkflowSweeper.sweep(), which only ever DRAINS the decider queue in
two places — when the workflow is null, or when its status is terminal. Anything else
stays queued and is swept again on the next cycle, forever.

The wasted case is explicitly instrumented. After decide(), the sweeper compares the
task list before and after:

    if (tasks.equals(tasksAfterDecide)) {          // decide() changed NOTHING
        log.warn("Going to repair the task {} / {}, with status {}, workflow = {}, "
                 "timeout = {}, now-wait = {}", ...);
        Monitors.getCounter("queue_message_repushed", "taskType", ..., "namespace", orgId)

So every "Going to repair" line is one sweep that advanced nothing and merely re-pushed
a task message. Counting those against "Running sweeper for workflow" in the SAME log
window gives a waste ratio, and the line itself names the task, its status, the owning
workflow and how long it has been waiting — which is the actionable part.

Pure text in, dict out. No network, no LLM.
"""
from __future__ import annotations

import re
from collections import Counter

_SWEEP = re.compile(r"Running sweeper for workflow\s+(\S+)")
# "Going to repair the task <id> / <ref>, with status <ST>, workflow = <wid>,
#  timeout = <n>, now-wait = <n>"
_REPAIR = re.compile(
    r"Going to repair the task\s+(?P<task>\S+?)\s*/\s*(?P<ref>[^,]+?),"
    r"\s*with status\s+(?P<status>\w+),"
    r"\s*workflow\s*=\s*(?P<wf>\S+?),"
    r"\s*timeout\s*=\s*(?P<timeout>-?\d+),"
    r"\s*now-wait\s*=\s*(?P<waited>-?\d+)"
)
_LOCK_FAIL = re.compile(r"Couldn't acquire lock to sweep workflow\s+(\S+)")


def summarize_sweeper_waste(log_text: str, top: int = 5) -> dict:
    """Quantify wasted sweeps from ONE log window.

    Both counts must come from the same window or the ratio is meaningless —
    separate greps return different slices.
    """
    swept = _SWEEP.findall(log_text)
    lock_failures = _LOCK_FAIL.findall(log_text)
    repairs = [m.groupdict() for m in _REPAIR.finditer(log_text)]

    by_ref = Counter(r["ref"].strip() for r in repairs)
    by_status = Counter(r["status"] for r in repairs)
    repeat_wf = Counter(r["wf"] for r in repairs)

    # A workflow re-appearing in one short window is being re-swept with no progress.
    persistent = [{"workflow": wf, "sweeps_in_window": n}
                  for wf, n in repeat_wf.most_common(top) if n > 1]

    longest = sorted(repairs, key=lambda r: int(r["waited"]), reverse=True)[:top]
    stuck = [{"task": r["task"], "ref": r["ref"].strip(), "status": r["status"],
              "workflow": r["wf"], "waited_ms": int(r["waited"])} for r in longest]

    total, wasted = len(swept), len(repairs)
    ratio = round(wasted / total, 2) if total else None

    return {
        "sweeps_in_window": total,
        "wasted_sweeps": wasted,
        "waste_ratio": ratio,
        "lock_acquire_failures": len(lock_failures),
        "wasted_by_task_ref": by_ref.most_common(top),
        "wasted_by_task_status": by_status.most_common(top),
        "workflows_reswept_in_window": persistent,
        "longest_waiting_tasks": stuck,
        "verdict": _verdict(total, wasted, ratio, by_ref, len(lock_failures)),
        "metric_hint": ("`queue_message_repushed` (tagged taskType, namespace) is the same "
                        "signal as a Prometheus counter — use it for the trend over time."),
    }


def _verdict(total: int, wasted: int, ratio: float | None, by_ref: Counter, lock_fails: int) -> str:
    if total == 0:
        return ("No sweeper activity in this log window — the sweeper is NOT the CPU "
                "consumer. Do not attribute CPU to a workflow backlog.")
    if lock_fails and wasted == 0:
        return (f"{lock_fails} lock-acquire failures and no repairs: threads are contending "
                "on the workflow lock, not doing sweeper work. Check thread state, not backlog.")
    if ratio is not None and ratio >= 0.5:
        worst = by_ref.most_common(1)[0] if by_ref else ("?", 0)
        return (f"WASTED WORK: {wasted} of {total} sweeps ({int(ratio * 100)}%) advanced nothing "
                f"— decide() left the task list unchanged and only re-pushed queue messages. "
                f"Dominant stuck task ref: '{worst[0]}' ({worst[1]}x). These workflows cannot "
                "reach terminal, so the sweeper will re-sweep them forever. Fix the workflows "
                "(timeout policy / never-arriving event / poison pill), not the CPU limit.")
    return (f"{wasted} of {total} sweeps re-pushed a task; the rest advanced workflow state. "
            "Sweeper load looks like genuine work — attribute CPU elsewhere.")
