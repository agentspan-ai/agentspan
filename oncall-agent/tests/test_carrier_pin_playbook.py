"""Coverage guard: the JDK-21 carrier-pin deadlock scenario must stay in the playbook.

This is the confirmed root cause of three multi-hour AuditBoard outages
(auditboard-prod 2026-07-30 8h29m, auditboard-postprd 2026-08-03 8h20m and
2026-08-05). It took ~8 hours per incident to re-derive each time because the
evidence is actively misleading: CPU sits at ~0.1% (reads as "no load"), all pods
report Running/Ready, and jstack shows hundreds of threads waiting on a lock with
NO owner listed. Each fact below is load-bearing for recognising it on sight, so
each is pinned here. No LLM involved — a plain substring guard.
"""
from oncall_agent.agent import INSTRUCTIONS

I = INSTRUCTIONS.lower()


def test_fingerprint_anchors_present():
    """The symptom cluster that identifies the wedge before any thread dump."""
    for anchor in [
        "task poll timed out",          # the health_check task is starved, not failing
        "0.1%",                         # CPU is confirmatory, not contradictory
        "decider-executor-vthread",     # thread name == vulnerable code path
    ]:
        assert anchor in I, f"lost fingerprint anchor: {anchor!r}"


def test_thread_dump_confirmation_present():
    """What to look for in the dump, including why the lock looks ownerless."""
    for anchor in ["genericobjectpool", "linkedblockingdeque", "locked ownable synchronizers"]:
        assert anchor in I, f"lost thread-dump anchor: {anchor!r}"
    # The non-obvious part: an unowned lock is a reporting gap, not a paradox.
    assert "virtual" in I and "aqs" in I, "lost the explanation for the missing lock owner"


def test_version_gate_present():
    """Without the version window the agent cannot say whether a cluster is exposed."""
    for anchor in ["#2943", "#3796", "v5.5.0-rc1"]:
        assert anchor in I, f"lost version-gate anchor: {anchor!r}"


def test_anti_patterns_present():
    """The three wrong turns that cost hours on 07-30, 08-03 and 08-05."""
    # low CPU must not be read as "cluster is fine"
    assert "confirmatory" in I, "lost the 'low CPU is confirmatory' guidance"
    # the one-line disproof of the Kubernetes/ingress theory
    assert "curl localhost:8080" in I, "lost the localhost app-vs-network disproof"
    # restart is a remedy, not a fix
    assert "restart restores service" in I, "lost the remedy-vs-fix distinction"


def test_capture_before_restart():
    """Restarts destroyed the evidence twice; the agent must say capture first."""
    assert "before the restart" in I, "lost the capture-before-restart instruction"
