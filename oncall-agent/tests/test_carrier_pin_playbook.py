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


# ── CPU alerts must be grounded in thread state ──────────────────────────
# Every CPU alert used to come back as "sweeper churn / N RUNNING workflows"
# because (a) download_thread_dump returns only an S3 path the model cannot read
# and (b) the playbook literally told it to grep logs for "sweeper churn".
# Confirmation bias, encoded in the prompt.


def test_cpu_rule_demands_thread_state_first():
    assert "get_thread_summary" in I, "CPU rule must route to the thread summariser"
    assert "threads first" in I, "thread evidence must be ordered FIRST, not last"
    assert "runnable" in I, "must reason about RUNNABLE threads specifically"


def test_backlog_narrative_is_banned_without_evidence():
    """The canned answer must be explicitly forbidden, not merely discouraged."""
    assert "banned without thread evidence" in I
    for phrase in ["sweeper churn", "decider backlog"]:
        assert phrase in I, f"the banned phrase {phrase!r} must be named to be banned"
    assert "cause not established" in I, "must have a no-evidence escape hatch"


def test_sweeper_path_requires_bucketing_and_sampling():
    """If the sweeper IS hot, don't stop at a total — name which workflows and why."""
    assert "workflow_running" in I, "must bucket the backlog by workflow, not quote a total"
    assert "sample" in I, "must sample concrete workflow ids from the sweeper log lines"
    assert "alert_only" in I, "must establish WHY the workflows never terminate"


def test_thread_summary_tool_is_registered():
    from oncall_agent.tools import ALL_TOOLS
    names = {getattr(t, "__name__", getattr(t, "name", "")) for t in ALL_TOOLS}
    assert "get_thread_summary" in names, "the tool must be callable, not just documented"


def test_playbook_routes_to_known_issue_matching():
    """A bug already fixed upstream must be recognised without a human spotting it."""
    assert "check_known_issues" in I
    assert "already fixed" in I
    assert "never read that as" in I, "UNKNOWN version must not be treated as safe"
