"""Bucket the RUNNING workflow backlog by definition, instead of quoting a bare total.

"698K RUNNING workflows" names nothing actionable. "two definitions account for 93% of
the backlog and both start on 17 March" names the bug. This turns the former into the
latter.

Shape of the data, learned the hard way against two live clusters:

* The parent ``workflow_archive`` table returns NOTHING — it is not a routing partition
  parent. Shards must be queried directly.
* Shard fleets vary enormously: auditboard-postprd has 2 shards, one-staging has 301
  holding 150.7M rows.
* Sharding is by HASH, not time — on one-staging every shard held 510K rows within 0.3%
  of each other. So there is no "latest" shard, and any single shard is a representative
  1/N sample. That is what makes extrapolation sound on big fleets and unnecessary on
  small ones.
* ``json_data`` is empty for RUNNING rows (live state lives in Redis until terminal), so
  this can say WHICH definitions are stuck and how old, but not which task is stuck.
  Pair it with analyze_sweeper_waste for the task-level reason.

Pure functions: no network, no LLM.
"""
from __future__ import annotations

import datetime

# Above this many shards, querying them all is too expensive — sample one and scale.
SAMPLE_THRESHOLD = 4


def plan_shard_query(shards: list[dict], total_populated: int | None = None) -> dict:
    """Decide whether to read every populated shard or sample one and extrapolate.

    ``shards`` is [{"relname": ..., "n_live_tup": ...}, ...] from pg_stat_user_tables,
    which the caller must LIMIT — one-staging has 301 shards and the full listing blows
    the agent-handler's ~8KB result cap, silently returning nothing. ``total_populated``
    carries the true fleet size from a separate count(*) so the scale factor stays right
    even though only a few rows were fetched.
    """
    populated = [s for s in shards if int(s.get("n_live_tup") or 0) > 0]
    if not populated:
        return {"mode": "none", "shards": [], "shard_count": 0, "scale": 0}
    fleet = total_populated if total_populated is not None else len(populated)
    if fleet <= SAMPLE_THRESHOLD:
        return {"mode": "exact", "shards": [s["relname"] for s in populated],
                "shard_count": fleet, "scale": 1}
    # Hash-distributed and uniform, so the biggest shard is as representative as any;
    # picking it deterministically keeps repeat runs comparable.
    biggest = max(populated, key=lambda s: int(s["n_live_tup"]))
    return {"mode": "sampled", "shards": [biggest["relname"]],
            "shard_count": fleet, "scale": fleet}


def _as_date(epoch_ms) -> str | None:
    try:
        return datetime.datetime.fromtimestamp(int(epoch_ms) / 1000).strftime("%Y-%m-%d")
    except Exception:
        return None


def build_backlog_report(plan: dict, status_rows: list[dict], bucket_rows: list[dict],
                         top: int = 8) -> dict:
    """Scale the sampled counts and name the dominant definitions."""
    scale = plan.get("scale", 1)
    estimated = plan.get("mode") == "sampled"

    statuses = {r["status"]: int(r["n"]) * scale for r in status_rows if r.get("status")}
    total_all = sum(statuses.values())
    running = statuses.get("RUNNING", 0)
    failed = statuses.get("FAILED", 0)

    buckets = []
    for r in bucket_rows[:top]:
        n = int(r.get("running") or 0) * scale
        buckets.append({
            "workflow_name": r.get("workflow_name"),
            "running": n,
            "share_pct": round(100 * n / running, 1) if running else None,
            "oldest": _as_date(r.get("oldest")),
        })

    top2 = sum(b["running"] for b in buckets[:2])
    return {
        "mode": plan.get("mode"),
        "estimated": estimated,
        "shards_total": plan.get("shard_count"),
        "shard_sampled": plan["shards"][0] if estimated and plan.get("shards") else None,
        "running_total": running,
        "failed_total": failed,
        "failure_rate_pct": round(100 * failed / total_all, 2) if total_all else None,
        "buckets": buckets,
        "verdict": _verdict(running, failed, total_all, buckets, top2, estimated),
    }


def _verdict(running: int, failed: int, total_all: int, buckets: list[dict],
             top2: int, estimated: bool) -> str:
    if running == 0:
        return "No RUNNING workflows in the archive — the backlog is not the problem."
    prefix = "ESTIMATED (one shard scaled by the fleet size): " if estimated else ""
    parts = []
    if buckets and running and top2 / running >= 0.6:
        names = " and ".join(f"`{b['workflow_name']}`" for b in buckets[:2])
        oldest = min((b["oldest"] for b in buckets[:2] if b["oldest"]), default=None)
        parts.append(
            f"{running:,} RUNNING, and {names} alone account for "
            f"{round(100 * top2 / running)}% of it"
            + (f", oldest dating to {oldest}" if oldest else "")
            + ". This is a LEAK in specific definitions, not a capacity problem — "
              "investigate those definitions, not the CPU limit."
        )
    else:
        parts.append(f"{running:,} RUNNING, spread across definitions with no dominant one.")
    rate = round(100 * failed / total_all, 1) if total_all else 0
    if rate >= 50:
        parts.append(
            f"SEPARATELY: {rate}% of all archived workflows are FAILED — that is a broken "
            "cluster in its own right, independent of the backlog."
        )
    return prefix + " ".join(parts)
