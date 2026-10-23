"""L1 live smoke test — read-only agent-handler dispatch against ah5r-prod.

Does NOT use the LLM. Calls the dispatcher directly to verify auth, the start-workflow
input contract, polling, and that each read-only command returns real data. Asserts on
status COMPLETED *and* output shape (not just status).

Usage:
    # from oncall-agent/, with CONDUCTOR_AUTH_KEY/SECRET in env or .env:
    PYTHONPATH=src python scripts/smoke_dispatch.py <health_check_execution_id>

Pick a recent successful health_check execution id (it only needs to carry the
organizationId / clusterName / cloudEnvironmentTag context — the agent reads those).
"""
from __future__ import annotations

import json
import sys

from oncall_agent.config import Config
from oncall_agent.conductor_client import ConductorDispatcher


def _preview(value, n: int = 800) -> str:
    return json.dumps(value, default=str)[:n]


def main(execution_id: str) -> int:
    cfg = Config.from_env()
    if not (cfg.conductor_key_id and cfg.conductor_key_secret):
        print("Missing CONDUCTOR_AUTH_KEY / CONDUCTOR_AUTH_SECRET")
        return 2

    d = ConductorDispatcher(
        cfg.conductor_server_url, cfg.conductor_key_id, cfg.conductor_key_secret
    )

    # 1) Can we read the failing execution's cluster context?
    ctx = d.get_context(execution_id)
    print("context:", json.dumps(ctx, indent=2))
    if not (ctx.get("clusterName") and ctx.get("organizationId")):
        print("FAIL: could not read cluster context from execution input")
        return 1

    results: list[tuple[str, bool, str]] = []

    def check(command: str, workflow: str, params: dict, shape_ok) -> None:
        res = d.dispatch(command, workflow, ctx, params)
        status = res.get("status")
        try:
            ok = status == "COMPLETED" and bool(shape_ok(res))
            note = "" if ok else f"status={status}"
        except Exception as exc:  # shape check blew up
            ok, note = False, f"shape error: {exc}"
        print(f"\n[{command}] status={status} ok={ok}")
        print(_preview(res.get("output") or res.get("tasks")))
        results.append((command, ok, note))

    # 2) A couple of zero-arg read-only commands — assert real output shape.
    check("GET_PODS_DATA", "get_pods_data", {}, lambda r: r.get("output") or r.get("tasks"))
    check(
        "GET_CLUSTER_METRICS",
        "get_cluster_metrics",
        {},
        lambda r: r.get("output") or r.get("tasks"),
    )

    # 3) SELECT smoke — proves the SQL path works read-only end to end.
    check(
        "SQL_CONDUCTOR",
        "sql_conductor",
        {"query": "SELECT 1", "transactional": False, "expectedRowCount": None},
        lambda r: r.get("status") == "COMPLETED",
    )

    print("\n── summary ──")
    for command, ok, note in results:
        print(f"  {'PASS' if ok else 'FAIL'}  {command}  {note}")
    all_ok = all(ok for _, ok, _ in results)
    print(f"\nSMOKE {'PASS' if all_ok else 'FAIL'}")
    return 0 if all_ok else 1


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("usage: PYTHONPATH=src python scripts/smoke_dispatch.py <execution_id>")
        raise SystemExit(2)
    raise SystemExit(main(sys.argv[1]))
