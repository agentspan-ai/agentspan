"""Guard against the failure that produced 26+ dead triages over 2.1 days.

Individual SDK worker threads died while the process stayed alive. Tool tasks were
scheduled onto queues nobody polled, the JOIN waited out the 30-minute deadline, and
the tasks show CANCELED having never started. Real observed ages below.
"""
import time
import pytest
from oncall_agent.worker_health import (evaluate, reset_seen_healthy,
                                        CRITICAL_TASK_TYPES, STALE_AFTER_S)
from oncall_agent import slack_app


def test_healthy_workers_allow_triage():
    reset_seen_healthy()
    r = evaluate({"get_incident_details": 0.1, "get_alert_recurrence": 0.1})
    assert r["ok"] is True
    assert set(r["healthy"]) == set(CRITICAL_TASK_TYPES)


def test_the_real_incident_is_caught():
    """Observed 2026-08-10: both critical workers last polled ~2.1 days earlier
    while pull_pod_logs in the same process kept polling."""
    reset_seen_healthy()
    evaluate({t: 0.1 for t in CRITICAL_TASK_TYPES})  # seen healthy first
    r = evaluate({"get_incident_details": 3071 * 60, "get_alert_recurrence": 3052 * 60})
    assert r["ok"] is False
    assert len(r["stale"]) == 2
    assert "min ago" in r["reason"] and "Restart the agent" in r["reason"]


def test_missing_poller_is_distinct_from_stale_poller():
    """'never registered' and 'registered then died' are different faults."""
    reset_seen_healthy()
    evaluate({t: 0.1 for t in CRITICAL_TASK_TYPES})
    r = evaluate({"get_incident_details": None, "get_alert_recurrence": 5.0})
    assert r["no_poller"] == ["get_incident_details"]
    assert r["stale"] == []
    assert "no poller registered" in r["reason"]


def test_absent_key_counts_as_no_poller_not_healthy():
    reset_seen_healthy()
    evaluate({t: 0.1 for t in CRITICAL_TASK_TYPES})
    r = evaluate({})
    assert r["ok"] is False
    assert set(r["no_poller"]) == set(CRITICAL_TASK_TYPES)


def test_boundary_just_under_threshold_is_still_ok():
    reset_seen_healthy()
    r = evaluate({t: STALE_AFTER_S - 1 for t in CRITICAL_TASK_TYPES})
    assert r["ok"] is True


def test_probe_failure_must_not_report_dead(monkeypatch):
    """A transient HTTP error must not block triage — that would be a worse outage
    than the one this guards against."""
    class Boom:
        def get(self, *a, **k): raise RuntimeError("network down")
    monkeypatch.setattr(slack_app, "requests", Boom())
    ages = slack_app._poll_ages("http://x/api", CRITICAL_TASK_TYPES)
    assert evaluate(ages)["ok"] is True, "probe failure must fail OPEN, not block triage"


def test_poll_ages_reads_lastPollTime(monkeypatch):
    now_ms = int(time.time() * 1000)
    class Resp:
        ok = True
        def json(self): return [{"lastPollTime": now_ms - 600_000, "workerId": "w"}]
    class Sess:
        def get(self, *a, **k): return Resp()
    monkeypatch.setattr(slack_app, "requests", Sess())
    ages = slack_app._poll_ages("http://x/api", ("get_incident_details",))
    assert 590 < ages["get_incident_details"] < 610
    assert evaluate(ages)["ok"] is False, "10 min stale must be caught"


# ── cold start must not deadlock ─────────────────────────────────────────
# Workers are spawned lazily by runtime.run() -> _prepare_workers. On a freshly
# started process they have never polled, and polldata still carries the PREVIOUS
# process's timestamps. The first version of this guard blocked on that and posted
# "tool workers are not polling / last polled 23 min ago" to Slack for every alert —
# preventing the very call that starts the workers. Self-defeating.

def test_cold_start_does_not_block_even_though_polldata_is_stale():
    reset_seen_healthy()
    # exactly what was observed in Slack: 23 min stale, fresh process
    r = evaluate({t: 23 * 60 for t in CRITICAL_TASK_TYPES})
    assert r["ok"] is True, "cold start must let the triage through to spawn workers"
    assert set(r["warming_up"]) == set(CRITICAL_TASK_TYPES)
    assert r["stale"] == [] and r["no_poller"] == []


def test_death_after_a_healthy_reading_is_still_caught():
    """The real fault must still be detected — a healthy -> stale transition."""
    reset_seen_healthy()
    assert evaluate({t: 0.1 for t in CRITICAL_TASK_TYPES})["ok"] is True
    r = evaluate({t: 3071 * 60 for t in CRITICAL_TASK_TYPES})
    assert r["ok"] is False
    assert len(r["stale"]) == 2 and "Restart the agent" in r["reason"]


def test_partial_death_is_caught_per_task_type():
    reset_seen_healthy()
    evaluate({t: 0.1 for t in CRITICAL_TASK_TYPES})          # both seen healthy
    r = evaluate({"get_incident_details": 0.1, "get_alert_recurrence": 9999.0})
    assert r["ok"] is False
    assert [s["task_type"] for s in r["stale"]] == ["get_alert_recurrence"]
