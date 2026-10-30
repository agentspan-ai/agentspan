"""Build/refresh the release index: releases from orkes-conductor git, fleet versions from health checks.

    PYTHONPATH=src .venv/bin/python scripts/build_release_index.py [--repo PATH] [--hours 1]
Run daily (the weekly job runs it too). Reads ah5r workflow data only — never a cluster.
"""
from __future__ import annotations

import argparse
import os
import re
import subprocess
import time
from concurrent.futures import ThreadPoolExecutor

from oncall_agent import release_index as ri
from oncall_agent.conductor_client import ConductorDispatcher
from oncall_agent.config import Config


def _ms(v) -> int:
    from oncall_agent.conductor_client import _epoch_ms
    return _epoch_ms(v) or 0


def fleet_versions(disp: ConductorDispatcher, hours: int) -> list[dict]:
    """Latest COMPLETED health check per cluster -> the Conductor version it reported."""
    since = int((time.time() - hours * 3600) * 1000)
    latest: dict[str, tuple[int, str]] = {}  # cluster -> (start time, newest health check id)
    for page in range(80):
        res = disp._call(lambda: disp._wf.search(start=page * 100, size=100,
                                                   query=f"workflowType IN (health_check) AND status IN (COMPLETED) AND startTime>{since}"))
        rows = getattr(res, "results", None) or []
        for r in rows:
            m = re.search(r"clusterName['\"]?\s*[:=]\s*['\"]?([\w.-]+)", str(getattr(r, "input", "") or ""))
            started = _ms(getattr(r, "start_time", None))
            if m and (m[1] not in latest or started > latest[m[1]][0]):
                latest[m[1]] = (started, r.workflow_id)
        if len(rows) < 100:
            break
    latest_ids = [wid for _, wid in latest.values()]

    def one(wid: str) -> dict | None:
        try:
            wf = disp.get_execution(wid)
        except Exception:
            return None
        cluster = (wf.get("input") or {}).get("clusterName") or \
            ((wf.get("input") or {}).get("agentHandlerRequest") or {}).get("clusterName")
        for t in wf.get("tasks", []):
            if t.get("ref") == "conductor":
                v = ((t.get("output") or {}).get("response") or {}).get("version")
                if cluster and v:
                    return {"cluster": cluster, "version": str(v), "org": (wf.get("input") or {}).get("organizationId"),
                            "seen_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
        return None

    with ThreadPoolExecutor(6) as ex:
        found = [r for r in ex.map(one, latest_ids) if r]
    by_cluster = {}
    for r in found:
        by_cluster.setdefault(r["cluster"], r)
    return list(by_cluster.values())


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", default=os.environ.get("ORKES_CONDUCTOR_REPO", os.path.expanduser("~/Orkes/orkes-conductor")))
    ap.add_argument("--hours", type=int, default=1, help="health checks from the last N hours")
    ap.add_argument("--skip-fleet", action="store_true")
    a = ap.parse_args()
    subprocess.run(["git", "-C", a.repo, "fetch", "-q", "--tags", "origin"], timeout=600)
    db = ri.connect()
    print("releases added:", ri.index_releases(a.repo, db))
    if not a.skip_fleet:
        cfg = Config.from_env()
        disp = ConductorDispatcher(cfg.conductor_server_url, cfg.conductor_key_id, cfg.conductor_key_secret)
        print("clusters with a version:", ri.record_fleet(db, fleet_versions(disp, a.hours)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
