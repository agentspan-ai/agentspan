"""The agent must reach these conclusions WITHOUT a human recognising the pattern.

Both multi-hour incidents this month were already fixed upstream weeks earlier; nobody
linked the running version to the merged PR, so each was re-diagnosed from scratch.
Real versions from the fleet are used throughout.
"""
from oncall_agent.known_issues import parse_version, match_known_issues


def test_branch_tags_fail_closed_not_open():
    """`fix-archive-feature-async-reconcile-latest` is deployed in this fleet. Parsing
    it as a version would tell a vulnerable cluster it is safe."""
    assert parse_version("orkes-conductor-server:fix-archive-feature-async-reconcile-latest") is None
    r = match_known_issues("orkes-conductor-server:fix-archive-feature-async-reconcile-latest",
                           repushed_task_types={"WAIT"}, waste_ratio=0.9)
    assert r["version_parsed"] is False
    assert r["matched"] == [], "must not claim a match it cannot substantiate"
    assert "UNKNOWN" in r["verdict"]


def test_semver_parsing():
    assert parse_version("orkes-conductor-server:5.4.3") == (5, 4, 3)
    assert parse_version("v5.2.97") == (5, 2, 97)
    assert parse_version("5.5.0-rc1") == (5, 5, 0)


def test_one_staging_wait_resweep_is_identified_unaided():
    """5.4.3 + WAIT tasks being repushed + high waste == PR #3754/#3775."""
    r = match_known_issues("orkes-conductor-server:5.4.3",
                           repushed_task_types={"WAIT"}, waste_ratio=0.95)
    ids = [m["id"] for m in r["matched"]]
    assert "wait-human-resweep-cadence" in ids
    assert any("#3775" in p for m in r["matched"] for p in m["prs"])
    assert "upgrading is the fix" in r["verdict"]


def test_auditboard_carrier_pin_is_identified_from_thread_names():
    """5.2.97 + decider vthreads on the pool == PR #3796, no human needed."""
    r = match_known_issues("orkes-conductor-server:5.2.97",
                           thread_names={"decider-executor-vthread-7"},
                           frames={"org.apache.commons.pool2.impl.GenericObjectPool.borrowObject"})
    ids = [m["id"] for m in r["matched"]]
    assert "jdk21-carrier-pin" in ids
    assert any("#3796" in p for m in r["matched"] for p in m["prs"])


def test_exposed_but_symptoms_do_not_match_is_not_a_diagnosis():
    """Being on an old version is not evidence. Don't pin an unrelated alert on it."""
    r = match_known_issues("orkes-conductor-server:5.4.3")
    assert r["matched"] == []
    assert "EXPOSED" in r["verdict"] and "do not assume" in r["verdict"]


def test_fixed_version_clears_both():
    r = match_known_issues("orkes-conductor-server:5.5.0",
                           repushed_task_types={"WAIT"}, waste_ratio=0.99,
                           thread_names={"decider-executor-vthread-1"})
    assert r["exposed_to"] == [] and r["matched"] == []
    assert "post-dates all known issues" in r["verdict"]


def test_low_waste_does_not_trigger_the_wait_match():
    """WAIT tasks alone aren't enough — the waste ratio has to be there too."""
    r = match_known_issues("orkes-conductor-server:5.4.3",
                           repushed_task_types={"WAIT"}, waste_ratio=0.05)
    assert [m["id"] for m in r["matched"]] == []


def test_verdict_renders_the_fixed_version_readably():
    """It was leaking the raw tuple '(5, 5, 0)' into a Slack-facing summary."""
    r = match_known_issues("orkes-conductor-server:5.4.3",
                           repushed_task_types={"WAIT"}, waste_ratio=0.95)
    assert "in 5.5.0;" in r["verdict"]
    assert "(5, 5, 0)" not in r["verdict"]
