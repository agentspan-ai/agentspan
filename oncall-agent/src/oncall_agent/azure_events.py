"""What did Azure itself report for this cluster's Redis and Postgres around a failure?

Managed services fail in ways the cluster cannot see: Azure Cache for Redis refusing
writes while its AOF persistence stalls ("MISCONF ... AOF"), a Redis failover during
patching, a Postgres Flexible Server restart for maintenance. Azure records all of
these, so read them instead of inferring them from pod restarts.

Resources are resolved from the saas DB replica in BigQuery (cluster -> Azure Redis /
Postgres name, resource group, subscription); metrics and the activity log come from
the Azure CLI, which must be logged in with read access to the subscription.
"""
from __future__ import annotations

import json
import subprocess
from datetime import datetime, timedelta, timezone

_BQ_PROJECT = "data-bi-474617"
_SAAS = f"{_BQ_PROJECT}.prod_saas_raw"


def _run(args: list[str], timeout: int = 120) -> str:
    p = subprocess.run(args, capture_output=True, text=True, timeout=timeout)
    if p.returncode:
        raise RuntimeError((p.stderr or p.stdout).strip()[:300])
    return p.stdout


def resolve(cluster_id: str) -> dict:
    """Azure Redis and Postgres (name, resource group, subscription) for a cluster id."""
    sql = f"""
    WITH c AS (SELECT azure_redis_instance_id rid, azure_db_instance_id did FROM `{_SAAS}.clusters`
               WHERE snapshot_date >= DATE_SUB(CURRENT_DATE(), INTERVAL 3 DAY) AND id = @cluster
               QUALIFY ROW_NUMBER() OVER (ORDER BY snapshot_date DESC) = 1)
    SELECT 'redis' kind, r.name, r.resource_group, r.subscription_id FROM `{_SAAS}.azure_redis_instances` r, c
      WHERE r.snapshot_date >= DATE_SUB(CURRENT_DATE(), INTERVAL 3 DAY) AND r.id = c.rid
    UNION ALL
    SELECT 'postgres', d.name, d.resource_group, d.subscription_id FROM `{_SAAS}.azure_db_instances` d, c
      WHERE d.snapshot_date >= DATE_SUB(CURRENT_DATE(), INTERVAL 3 DAY) AND d.id = c.did"""
    out = _run(["bq", f"--project_id={_BQ_PROJECT}", "query", "--use_legacy_sql=false", "--format=json",
                f"--parameter=cluster::{cluster_id}", sql])
    found = {}
    for row in json.loads(out or "[]"):
        found.setdefault(row["kind"], row)
    return found


def _rid(r: dict) -> str:
    provider = "Microsoft.Cache/Redis" if r["kind"] == "redis" else "Microsoft.DBforPostgreSQL/flexibleServers"
    return (f"/subscriptions/{r['subscription_id']}/resourceGroups/{r['resource_group']}"
            f"/providers/{provider}/{r['name']}")


def _metric(rid: str, metric: str, agg: str, start: str, end: str, split: str | None = None) -> list:
    args = ["az", "monitor", "metrics", "list", "--resource", rid, "--metric", metric, "--aggregation", agg,
            "--interval", "PT5M", "--start-time", start, "--end-time", end, "-o", "json"]
    if split:
        args += ["--filter", f"{split} eq '*'"]
    return json.loads(_run(args))["value"][0]["timeseries"]


def summarize_redis_errors(timeseries: list) -> list[dict]:
    """Non-zero Errors windows as [{time, type, count}], oldest first."""
    hits = []
    for ts in timeseries:
        etype = ts["metadatavalues"][0]["value"] if ts.get("metadatavalues") else "?"
        for p in ts["data"]:
            if (p.get("total") or 0) > 0:
                hits.append({"time": p["timeStamp"], "type": etype, "count": int(p["total"])})
    return sorted(hits, key=lambda h: h["time"])


def summarize_db_alive(timeseries: list) -> list[str]:
    """5-minute windows where Postgres reported not alive (is_db_alive minimum 0)."""
    return [p["timeStamp"] for ts in timeseries for p in ts["data"]
            if p.get("minimum") is not None and p["minimum"] < 1]


def activity(rid: str, start: str, end: str) -> list[dict]:
    rows = json.loads(_run(["az", "monitor", "activity-log", "list", "--resource-id", rid,
                            "--start-time", start, "--end-time", end, "-o", "json"]) or "[]")
    return [{"time": r.get("eventTimestamp"), "category": (r.get("category") or {}).get("value"),
             "operation": (r.get("operationName") or {}).get("localizedValue"),
             "status": (r.get("status") or {}).get("value"),
             "caller": r.get("caller")} for r in rows][:20]


def azure_events(cluster_id: str, onset_ms: int, before_min: int = 60, after_min: int = 30) -> dict:
    """Redis errors, Postgres liveness and activity-log events around the failure onset."""
    onset = datetime.fromtimestamp(onset_ms / 1000, tz=timezone.utc)
    start = (onset - timedelta(minutes=before_min)).strftime("%Y-%m-%dT%H:%M:%SZ")
    end = (onset + timedelta(minutes=after_min)).strftime("%Y-%m-%dT%H:%M:%SZ")
    res = resolve(cluster_id)
    if not res:
        return {"error": "not_azure_or_unresolved",
                "detail": f"no Azure Redis/Postgres found for cluster {cluster_id} in the saas DB replica"}
    out: dict = {"window": [start, end], "failureOnset": onset.isoformat()}
    for kind, r in res.items():
        r = {**r, "kind": kind}
        rid = _rid(r)
        entry: dict = {"name": r["name"], "resourceGroup": r["resource_group"], "subscription": r["subscription_id"]}
        try:
            if kind == "redis":
                entry["errors"] = summarize_redis_errors(_metric(rid, "Errors", "Total", start, end, "ErrorType"))
            else:
                entry["notAliveWindows"] = summarize_db_alive(_metric(rid, "is_db_alive", "Minimum", start, end))
            entry["activityLog"] = activity(rid, start, end)
        except Exception as exc:  # report, never guess
            entry["error"] = str(exc)
        out[kind] = entry
    findings = []
    for e in out.get("redis", {}).get("errors", []):
        findings.append(f"Azure Redis {out['redis']['name']}: {e['count']} {e['type']} error(s) at {e['time']}"
                        + (" — AOF persistence write failed; Redis refuses writes with MISCONF until it clears"
                           if e["type"] == "AOF" else " — Redis failover (patching/maintenance)" if e["type"] == "Failover" else ""))
    for t in out.get("postgres", {}).get("notAliveWindows", []):
        findings.append(f"Azure Postgres {out['postgres']['name']}: not alive in the 5 min from {t} (restart/failover)")
    for kind in ("redis", "postgres"):
        if out.get(kind, {}).get("error"):
            findings.append(f"Azure {kind} lookup FAILED ({out[kind]['error'][:120]}) — "
                            f"nothing is known about {out[kind]['name']}; do not read this as healthy")
    out["findings"] = findings or ["Azure reported no Redis errors, no Postgres downtime in the window"]
    return out
