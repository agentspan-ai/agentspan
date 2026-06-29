"""Read-only investigation tools the agent can call.

Each tool maps to a read-only agent-handler command. The LLM only ever passes the
incident ``execution_id`` (which it gets from the alert); the org / cluster /
cloudEnvironmentTag are derived once from that execution and cached, so the model
can't get the cluster wrong and nothing sensitive is threaded through tool args.

Tools run as Agentspan workers (separate processes), so the dispatcher and context
cache are module-level singletons built lazily from the environment.
"""
from __future__ import annotations

from agentspan.agents import tool

from .conductor_client import ConductorDispatcher
from .config import Config
from .sql_guard import NotReadOnlySQLError, ensure_select

_dispatcher: ConductorDispatcher | None = None
_ctx_cache: dict[str, dict] = {}

# Generous timeout: a dispatched command starts a workflow and we poll it to completion.
_T = 240


def _disp() -> ConductorDispatcher:
    global _dispatcher
    if _dispatcher is None:
        cfg = Config.from_env()
        _dispatcher = ConductorDispatcher(
            cfg.conductor_server_url, cfg.conductor_key_id, cfg.conductor_key_secret
        )
    return _dispatcher


def _context(execution_id: str) -> dict:
    if execution_id not in _ctx_cache:
        _ctx_cache[execution_id] = _disp().get_context(execution_id)
    return _ctx_cache[execution_id]


@tool(timeout_seconds=_T)
def get_incident_details(execution_id: str) -> dict:
    """Fetch the failing health_check execution: the detected issues (with severity),
    the per-component health results, and the cluster/organization context. ALWAYS
    call this FIRST, using the execution id from the alert URL (.../execution/<id>).

    Args:
        execution_id: Conductor workflow execution id from the alert.
    """
    wf = _disp().get_execution(execution_id)
    issues = None
    cluster_data = None
    component_health: dict = {}
    for t in wf.get("tasks", []):
        ref, ttype = t.get("ref"), str(t.get("type") or "")
        if ref == "issues":
            issues = t.get("output")
        elif ref == "parse_conductor_cluster_data_ref":
            # The load-bearing summary: redis.usage, redis.decider_queue_size
            # (= running workflows), redis.indexer_queue_size, heap_memory, cpu, postgres.
            out = t.get("output") or {}
            cluster_data = out.get("result", out)
        elif ttype.endswith("health_check"):
            out = t.get("output")
            component_health[ref] = {
                "healthy": out.get("healthy") if isinstance(out, dict) else None,
                "status": t.get("status"),
            }
    return {
        "executionId": execution_id,
        "status": wf.get("status"),
        "context": _context(execution_id),
        "issues": issues,
        # redis usage + queue sizes + heap/cpu/postgres — almost all you need, no SQL.
        "clusterData": cluster_data,
        "componentHealth": component_health,
    }


@tool(timeout_seconds=_T)
def get_cluster_metrics(execution_id: str) -> dict:
    """Current cluster metrics: CPU, heap, Redis usage, decider/indexer queue sizes,
    DB size. Read-only. Use for Redis/CPU/heap/queue issues."""
    return _disp().dispatch("GET_CLUSTER_METRICS", "get_cluster_metrics", _context(execution_id))


@tool(timeout_seconds=_T)
def get_infrastructure_metrics(execution_id: str) -> dict:
    """Cloud + Kubernetes infra metrics (node/pod CPU & memory). Read-only."""
    return _disp().dispatch(
        "GET_INFRASTRUCTURE_METRICS", "get_infrastructure_metrics", _context(execution_id)
    )


@tool(timeout_seconds=_T)
def get_pods_data(execution_id: str) -> dict:
    """List pods with status and restart counts. Read-only. Use this to find pod names."""
    return _disp().dispatch("GET_PODS_DATA", "get_pods_data", _context(execution_id))


@tool(timeout_seconds=_T)
def get_deployments_info(execution_id: str) -> dict:
    """Deployment metadata and replica readiness. Read-only."""
    return _disp().dispatch("GET_DEPLOYMENTS_INFO", "get_deployments_info", _context(execution_id))


@tool(timeout_seconds=_T)
def get_pod_events(execution_id: str, pod_name: str) -> dict:
    """Kubernetes events for a pod (OOMKills, restarts, scheduling/image failures). Read-only.

    Args:
        execution_id: incident execution id.
        pod_name: pod to inspect (from get_pods_data).
    """
    return _disp().dispatch(
        "GET_POD_EVENTS", "get_pod_events", _context(execution_id), {"podName": pod_name}
    )


@tool(timeout_seconds=_T)
def get_top_output(execution_id: str, pod_name: str = "") -> dict:
    """Live CPU/memory usage (kubectl top) for a pod, or all pods if pod_name is empty. Read-only.

    Args:
        execution_id: incident execution id.
        pod_name: optional pod name; empty means all pods.
    """
    params = {"podName": pod_name} if pod_name else {}
    return _disp().dispatch(
        "GET_TOP_OUTPUT_FROM_POD", "get_top_output_from_pod", _context(execution_id), params
    )


@tool(timeout_seconds=_T)
def pull_pod_logs(execution_id: str, pod_name: str, grep: str = "", lines: int = 200) -> dict:
    """Pull recent log lines from a pod, optionally filtered by a grep pattern. Read-only.

    Args:
        execution_id: incident execution id.
        pod_name: pod to pull logs from (from get_pods_data).
        grep: optional pattern to filter lines (e.g. "ERROR", "Exception", "OutOfMemory").
        lines: trailing lines to fetch (default 200, capped at 1000).
    """
    params = {"podName": pod_name, "lines": min(max(int(lines), 1), 1000), "fetchOption": "TAIL"}
    if grep:
        params["grep"] = grep
    return _disp().dispatch("PULL_LOGS", "pull_logs", _context(execution_id), params)


@tool(timeout_seconds=_T)
def get_ingress_info(execution_id: str) -> dict:
    """Ingress controller hostname + external address (LB) for the cluster. Read-only.

    Use for DNS / domain-resolution / domain-reachability alerts: if the ingress has
    no external address, the load balancer isn't provisioned (a concrete cause to
    cite). If it DOES have an address, the failure is external (DNS record, cert, or
    network path) and not visible from inside the cluster — say so and escalate to infra.
    """
    return _disp().dispatch("GET_INGRESS_INFO", "get_ingress_info", _context(execution_id))


@tool(timeout_seconds=_T)
def run_sql_select(execution_id: str, query: str) -> dict:
    """Run a READ-ONLY SQL SELECT against the cluster's Conductor DB to inspect
    workflow/task/queue state. Only SELECT/WITH/EXPLAIN/SHOW are permitted; any
    attempt to modify data is rejected BEFORE it reaches the database.

    Args:
        execution_id: incident execution id.
        query: a single read-only SQL statement.
    """
    try:
        safe = ensure_select(query)
    except NotReadOnlySQLError as exc:
        return {"error": "rejected_non_readonly_sql", "detail": str(exc), "query": query}
    return _disp().dispatch(
        "SQL_CONDUCTOR",
        "sql_conductor",
        _context(execution_id),
        {"query": safe, "transactional": False, "expectedRowCount": None},
    )


ALL_TOOLS = [
    get_incident_details,
    get_cluster_metrics,
    get_infrastructure_metrics,
    get_pods_data,
    get_deployments_info,
    get_pod_events,
    get_top_output,
    pull_pod_logs,
    get_ingress_info,
    run_sql_select,
]
