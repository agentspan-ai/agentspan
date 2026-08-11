"""Guard against the failure that produced 26+ dead triages over 2.1 days.

Individual SDK worker threads died while the process stayed alive. Tool tasks were
scheduled onto queues nobody polled, the JOIN waited out the 30-minute deadline, and
the tasks show CANCELED having never started. Real observed ages below.
"""
import time
import pytest
from oncall_agent.worker_health import evaluate, CRITICAL_TASK_TYPES, STALE_AFTER_S
from oncall_agent import slack_app


def test_healthy_workers_allow_triage():
    r = evaluate({"get_incident_details": 0.1, "get_alert_recurrence": 0.1})
    assert r["ok"] is True
    assert set(r["healthy"]) == set(CRITICAL_TASK_TYPES)


def test_the_real_incident_is_caught():
    """Observed 2026-08-10: both critical workers last polled ~2.1 days earlier
    while pull_pod_logs in the same process kept polling."""
    r = evaluate({"get_incident_details": 3071 * 60, "get_alert_recurrence": 3052 * 60})
    assert r["ok"] is False
    assert len(r["stale"]) == 2
    assert "min ago" in r["reason"] and "Restart the agent" in r["reason"]


def test_missing_poller_is_distinct_from_stale_poller():
    """'never registered' and 'registered then died' are different faults."""
    r = evaluate({"get_incident_details": None, "get_alert_recurrence": 5.0})
    assert r["no_poller"] == ["get_incident_details"]
    assert r["stale"] == []
    assert "no poller registered" in r["reason"]


def test_absent_key_counts_as_no_poller_not_healthy():
    r = evaluate({})
    assert r["ok"] is False
    assert set(r["no_poller"]) == set(CRITICAL_TASK_TYPES)


def test_boundary_just_under_threshold_is_still_ok():
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
