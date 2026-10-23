"""Tests for the pure eval-batch incident selector (no network, no LLM)."""
from __future__ import annotations

from oncall_agent.eval_select import select_eval_incidents

POD = (
    "*`[MAJOR]`* The health-checking has FAILED for the _Collective's_ prod "
    "*`collective-staging`* cluster with the following issue:\n"
    "*MAJOR:* Pod orkes-agent-deployment-84594b48f8-shldc Failed"
)
CPU = (
    "*`[MAJOR]`* The health-checking has FAILED for the _WVUF's_ prod "
    "*`orkes-wvuf-prod`* cluster with the following issue:\n"
    "*MAJOR:* Conductor Server CPU usage is at %s%% and exceeded the threshold of 95.0%%"
)
HEAP = (
    "*`[MAJOR]`* The health-checking has FAILED for the _At-Bay's_ prod "
    "*`atbay-production`* cluster with the following issue:\n"
    "*MAJOR:* Conductor Server Heap usage is at 91.2% and exceeded the threshold of 90.0%"
)


def _run(wf_id: str, reason: str, start: str) -> dict:
    return {"workflow_id": wf_id, "reason": reason, "start_time": start}


def test_flapper_collapses_to_one_incident():
    # The same (cluster, alert-type) firing 50 times is ONE incident — newest kept.
    rows = [_run(f"w{i}", POD, f"2026-07-22T{10 + i // 60:02d}:{i % 60:02d}:00Z") for i in range(50)]
    picked = select_eval_incidents(rows, limit=30)
    assert len(picked) == 1
    assert picked[0]["workflow_id"] == "w49"  # newest firing wins


def test_varying_numbers_do_not_split_an_incident():
    # CPU at 96.1% vs 99.7% on the same cluster = the same incident.
    rows = [
        _run("a", CPU % "96.1", "2026-07-22T10:00:00Z"),
        _run("b", CPU % "99.7", "2026-07-22T11:00:00Z"),
    ]
    assert len(select_eval_incidents(rows, limit=30)) == 1


def test_distinct_incidents_kept_and_capped():
    rows = [
        _run("a", POD, "2026-07-22T10:00:00Z"),
        _run("b", CPU % "99.7", "2026-07-22T11:00:00Z"),
        _run("c", HEAP, "2026-07-22T12:00:00Z"),
    ]
    assert len(select_eval_incidents(rows, limit=30)) == 3
    assert len(select_eval_incidents(rows, limit=2)) == 2
    # Cap keeps the newest incidents.
    capped = select_eval_incidents(rows, limit=2)
    assert {r["workflow_id"] for r in capped} == {"b", "c"}


def test_non_alerting_and_empty_reasons_are_skipped():
    rows = [
        _run("a", "", "2026-07-22T10:00:00Z"),
        _run("b", None, "2026-07-22T11:00:00Z"),
        _run("c", "Task poll timed out after 20 seconds. Poll timeout configured as 10 seconds. Timeout policy configured to RETRY", "2026-07-22T12:00:00Z"),
        _run("d", POD, "2026-07-22T13:00:00Z"),
    ]
    picked = select_eval_incidents(rows, limit=30)
    # Only real health-check alerts qualify; poll-timeout noise is excluded.
    assert [r["workflow_id"] for r in picked] == ["d"]
