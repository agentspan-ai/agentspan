"""Tests for RUNNING-backlog bucketing. Real numbers from two live clusters.

Both clusters raise the same alert but need opposite responses, which is the whole
point of bucketing instead of quoting a total:
  auditboard-postprd  1,651 RUNNING, oldest 2024-12-17, 94% FAILED  -> rotten cluster
  one-staging        ~16,555 RUNNING, oldest 2026-03-17, 0.66% FAILED -> two leaky defs
"""
from oncall_agent.running_backlog import plan_shard_query, build_backlog_report


def test_small_fleet_is_read_exactly_not_sampled():
    plan = plan_shard_query([{"relname": "workflow_archive_shard_00", "n_live_tup": 500000},
                             {"relname": "workflow_archive_shard_01", "n_live_tup": 223000}])
    assert plan["mode"] == "exact" and plan["scale"] == 1
    assert len(plan["shards"]) == 2


def test_large_fleet_samples_one_shard_and_scales():
    shards = [{"relname": f"workflow_archive_shard_{i}", "n_live_tup": 510000} for i in range(301)]
    shards[176]["n_live_tup"] = 511285          # the biggest, chosen deterministically
    plan = plan_shard_query(shards)
    assert plan["mode"] == "sampled"
    assert plan["scale"] == 301
    assert plan["shards"] == ["workflow_archive_shard_176"]


def test_empty_shards_are_not_sampled():
    assert plan_shard_query([{"relname": "s", "n_live_tup": 0}])["mode"] == "none"


def test_one_staging_leak_is_named_and_scaled():
    plan = {"mode": "sampled", "shards": ["workflow_archive_shard_176"],
            "shard_count": 301, "scale": 301}
    rep = build_backlog_report(
        plan,
        [{"status": "COMPLETED", "n": 507832}, {"status": "FAILED", "n": 3388},
         {"status": "RUNNING", "n": 55}],
        [{"workflow_name": "COM_Account_Creation_Request", "running": 27, "oldest": 1773740814940},
         {"workflow_name": "COM_Notification_Email_Workflow", "running": 24, "oldest": 1773676221792},
         {"workflow_name": "MOM_Agreement_Approval", "running": 3, "oldest": 1773714947867}])
    assert rep["estimated"] is True
    assert rep["running_total"] == 55 * 301 == 16555
    assert rep["buckets"][0]["workflow_name"] == "COM_Account_Creation_Request"
    assert rep["buckets"][0]["oldest"] == "2026-03-17"
    assert "LEAK in specific definitions" in rep["verdict"]
    assert "COM_Account_Creation_Request" in rep["verdict"]
    assert "ESTIMATED" in rep["verdict"], "must not present a scaled figure as exact"


def test_auditboard_high_failure_rate_is_surfaced_separately():
    """94% FAILED is its own finding and must not be buried under the backlog story."""
    plan = {"mode": "exact", "shards": ["s0"], "shard_count": 2, "scale": 1}
    rep = build_backlog_report(
        plan,
        [{"status": "FAILED", "n": 464026}, {"status": "COMPLETED", "n": 26811},
         {"status": "RUNNING", "n": 1645}],
        [{"workflow_name": "_Test_And_Review", "running": 333, "oldest": 1734387171756}])
    assert rep["failure_rate_pct"] > 90
    assert "SEPARATELY" in rep["verdict"] and "FAILED" in rep["verdict"]
    assert rep["buckets"][0]["oldest"] == "2024-12-17"
    assert "ESTIMATED" not in rep["verdict"], "exact mode must not claim estimation"


def test_no_running_workflows_clears_the_backlog_theory():
    rep = build_backlog_report({"mode": "exact", "shards": ["s"], "shard_count": 1, "scale": 1},
                               [{"status": "COMPLETED", "n": 10}], [])
    assert "not the problem" in rep["verdict"]


def test_fleet_size_comes_from_the_count_not_the_fetched_rows():
    """one-staging has 301 shards; listing them all blows the ~8KB result cap and comes
    back EMPTY. The caller LIMITs the listing, so the scale factor must come from a
    separate count(*) — otherwise a 301-shard fleet scales by 4 and under-reports 75x."""
    fetched = [{"relname": f"workflow_archive_shard_{i}", "n_live_tup": 510000} for i in range(4)]
    plan = plan_shard_query(fetched, total_populated=301)
    assert plan["mode"] == "sampled"
    assert plan["scale"] == 301, "must scale by the true fleet size, not the fetched rows"
    assert plan["shard_count"] == 301
