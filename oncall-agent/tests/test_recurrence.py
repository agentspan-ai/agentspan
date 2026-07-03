"""Tests for the pure alert-recurrence classifier (no network, no LLM)."""
from __future__ import annotations

from oncall_agent.recurrence import summarize_recurrence

CPU = "Conductor Server CPU usage is at %s%% and exceeded the threshold of 95.0%%"
REDIS = "Redis instance is at 88%"

_H = 3_600_000  # ms per hour


def _run(reason: str, start_ms: int) -> dict:
    return {"reason": reason, "start_time": start_ms}


def test_chronic_recurring_cpu_alert():
    # 30 of 100 recent checks fired the CPU alert, spread over 10h.
    runs = []
    for i in range(100):
        if i % 10 < 3:  # 3 in every 10 -> 30 total
            runs.append(_run(CPU % (95 + i % 5), i * _H // 10))
        else:
            runs.append(_run("", i * _H // 10))  # clean check
    rep = summarize_recurrence(runs, "Conductor Server CPU usage")
    assert rep.verdict == "RECURRING"
    assert rep.chronic is True  # 30% >= 20% chronic threshold
    assert rep.matched_count == 30
    assert rep.sample_size == 100
    assert abs(rep.fraction - 0.30) < 1e-9
    # first/last matched span within the window
    assert rep.first_seen_ms is not None and rep.last_seen_ms is not None
    assert rep.last_seen_ms > rep.first_seen_ms
    assert "NOT a fresh incident" in rep.summary


def test_new_alert_single_firing():
    # Only the current firing matches; everything else is clean or a different alert.
    runs = [_run(REDIS, i * _H) for i in range(20)]
    runs.append(_run(CPU % 97, 21 * _H))  # the one CPU firing
    rep = summarize_recurrence(runs, "Conductor Server CPU usage")
    assert rep.verdict == "NEW"
    assert rep.chronic is False
    assert rep.matched_count == 1
    assert "fresh incident" in rep.summary


def test_recurring_but_not_chronic():
    # Fired 3 of 100 (3%) -> recurring but below the 20% chronic bar.
    runs = [_run("", i * _H) for i in range(97)]
    runs += [_run(CPU % 96, (100 + i) * _H) for i in range(3)]
    rep = summarize_recurrence(runs, "Conductor Server CPU usage")
    assert rep.verdict == "RECURRING"
    assert rep.chronic is False
    assert rep.matched_count == 3


def test_signature_matches_type_not_numbers():
    # Same alert type, different percentages/pods each time -> all must match on
    # the stable signature (proves we don't match the varying numbers).
    runs = [_run(CPU % pct, i * _H) for i, pct in enumerate([96, 97, 98, 99, 95])]
    rep = summarize_recurrence(runs, "Conductor Server CPU usage")
    assert rep.matched_count == 5
    assert rep.verdict == "RECURRING"


def test_no_prior_match_when_signature_absent():
    runs = [_run(REDIS, i * _H) for i in range(10)]
    rep = summarize_recurrence(runs, "Conductor Server CPU usage")
    assert rep.verdict == "NO_PRIOR_MATCH"
    assert rep.matched_count == 0


def test_empty_signature_is_no_match():
    runs = [_run(CPU % 97, 0)]
    rep = summarize_recurrence(runs, "")
    assert rep.verdict == "NO_PRIOR_MATCH"
    assert rep.matched_count == 0


def test_iso8601_start_times_are_parsed():
    # Conductor's search summary returns start_time as an ISO-8601 string, not
    # epoch ms. The classifier must parse it and still compute a real span.
    runs = [
        _run(CPU % 96, "2026-07-01T00:00:00.000Z"),
        _run(CPU % 97, "2026-07-01T10:00:00.000Z"),
        _run("clean", "2026-07-01T05:00:00.000Z"),
    ]
    rep = summarize_recurrence(runs, "Conductor Server CPU usage")
    assert rep.matched_count == 2
    assert rep.first_seen_ms is not None and rep.last_seen_ms is not None
    assert abs(rep.span_hours - 10.0) < 0.01  # 00:00 -> 10:00 == 10h
