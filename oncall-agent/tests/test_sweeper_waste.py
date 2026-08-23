"""Deterministic tests for sweeper waste analysis — no cluster, no LLM.

Grounded in OrkesWorkflowSweeper.sweep(): the queue is drained only when a workflow is
null or terminal, so anything else is re-swept forever. The "Going to repair the task"
WARN fires exactly when decide() changed nothing — i.e. a sweep that advanced nothing.
"""
from oncall_agent.sweeper_waste import summarize_sweeper_waste

SWEEP = "INFO  [sweeper-thread-1] OrkesWorkflowSweeper: Running sweeper for workflow {wf}"
REPAIR = ("WARN  [sweeper-thread-1] OrkesWorkflowSweeper: Going to repair the task {t} / {ref}, "
          "with status {st}, workflow = {wf}, timeout = 0, now-wait = {w}")


def _log(sweeps, repairs):
    lines = [SWEEP.format(wf=w) for w in sweeps]
    lines += [REPAIR.format(**r) for r in repairs]
    return "\n".join(lines)


def test_high_waste_is_called_out_with_the_dominant_task():
    log = _log(["wf-a", "wf-b", "wf-c", "wf-d"],
               [dict(t=f"t{i}", ref="wait_for_webhook", st="IN_PROGRESS", wf="wf-a", w=99000)
                for i in range(3)])
    s = summarize_sweeper_waste(log)
    assert s["sweeps_in_window"] == 4 and s["wasted_sweeps"] == 3
    assert s["waste_ratio"] == 0.75
    assert "WASTED WORK" in s["verdict"]
    assert "wait_for_webhook" in s["verdict"], "must name the dominant stuck task ref"
    assert s["wasted_by_task_ref"][0] == ("wait_for_webhook", 3)


def test_repeatedly_reswept_workflow_is_surfaced():
    log = _log(["wf-a"] * 3,
               [dict(t="t1", ref="r", st="SCHEDULED", wf="wf-a", w=10) for _ in range(3)])
    s = summarize_sweeper_waste(log)
    assert s["workflows_reswept_in_window"][0] == {"workflow": "wf-a", "sweeps_in_window": 3}


def test_longest_waiting_task_is_ranked_first():
    log = _log(["w"], [dict(t="short", ref="a", st="IN_PROGRESS", wf="w", w=5),
                       dict(t="long", ref="b", st="IN_PROGRESS", wf="w", w=900000)])
    s = summarize_sweeper_waste(log)
    assert s["longest_waiting_tasks"][0]["task"] == "long"
    assert s["longest_waiting_tasks"][0]["waited_ms"] == 900000


def test_no_sweeper_activity_forbids_blaming_the_backlog():
    s = summarize_sweeper_waste("INFO nothing to see here")
    assert s["sweeps_in_window"] == 0
    assert "NOT the CPU consumer" in s["verdict"]
    assert "Do not attribute CPU to a workflow backlog" in s["verdict"]


def test_lock_contention_is_distinguished_from_sweeper_work():
    """The wedge signature: threads fighting for the lock, doing no sweeping."""
    log = "\n".join("ERROR OrkesWorkflowSweeper: Couldn't acquire lock to sweep workflow wf-%d" % i
                    for i in range(9)) + "\n" + _log(["wf-x"], [])
    s = summarize_sweeper_waste(log)
    assert s["lock_acquire_failures"] == 9
    assert s["wasted_sweeps"] == 0
    assert "contending" in s["verdict"] and "not backlog" in s["verdict"].lower()


def test_healthy_sweeper_is_not_maligned():
    s = summarize_sweeper_waste(_log([f"wf-{i}" for i in range(10)],
                                     [dict(t="t", ref="r", st="SCHEDULED", wf="wf-0", w=1)]))
    assert s["waste_ratio"] == 0.1
    assert "genuine work" in s["verdict"]
