"""Read-only investigation tools the agent can call.

Each tool maps to a read-only agent-handler command. The LLM only ever passes the
incident ``execution_id`` (which it gets from the alert); the org / cluster /
cloudEnvironmentTag are derived once from that execution and cached, so the model
can't get the cluster wrong and nothing sensitive is threaded through tool args.

Tools run as Agentspan workers (separate processes), so the dispatcher and context
cache are module-level singletons built lazily from the environment.
"""
from __future__ import annotations

import os
import re
from collections import Counter
from pathlib import Path

from conductor.ai.agents import tool

from .conductor_client import ConductorDispatcher
from .config import Config
from .recurrence import summarize_recurrence
from .kubectl_guard import NotReadOnlyKubectlError, ensure_readonly_kubectl
from .azure_events import azure_events
from .ingress_check import check_ingresses, served_certificate
from .node_churn import summarize_node_churn
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


def _azure_findings(cluster_id: str | None, onset_ms: int) -> list[str] | None:
    """Azure findings for an Azure cluster, None for other clouds or when unavailable."""
    if not cluster_id or not onset_ms:
        return None
    try:
        res = azure_events(cluster_id, onset_ms)
    except Exception as exc:
        return [f"Azure lookup failed: {str(exc)[:150]}"]
    return None if res.get("error") == "not_azure_or_unresolved" else res.get("findings")


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
            if isinstance(out, dict):
                # Why it failed: the service-level reason and every pod that failed its probe
                # ("Pod IP is invalid: N/A" = the pod was still being scheduled).
                if out.get("fallbackReason"):
                    component_health[ref]["reason"] = out["fallbackReason"]
                pods = out.get("pods") if isinstance(out.get("pods"), dict) else {}
                failed = {name: p.get("fallbackReason") or p.get("httpStatus")
                          for name, p in pods.items() if isinstance(p, dict) and p.get("healthy") is False}
                if failed:
                    component_health[ref]["failedPods"] = failed
    from datetime import datetime, timezone
    ctx = _context(execution_id)
    info = _disp().alert_info(execution_id)
    utc = lambda ms: datetime.fromtimestamp(ms / 1000, tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%SZ") if ms else None
    onset = _disp().failing_since(ctx.get("clusterId"), info["alert_ms"], info["issues"]) if info["alert_ms"] else 0
    after = _disp().runs_after(ctx.get("clusterId"), info["alert_ms"]) if info["alert_ms"] and ctx.get("clusterId") else []
    return {
        "executionId": execution_id,
        "status": wf.get("status"),
        # When it happened and what came after — judge everything against these, not "now".
        "alertTimeUtc": utc(info["alert_ms"]),
        "failingSinceUtc": utc(onset),
        "runsAfterAlert": after,
        "recoveredAfterAlert": (None if not after else
                                next((r["startTime"] for r in after if not r["failing"]), False)),
        # Managed Redis/Postgres events at the onset, always included: the model skipped the
        # separate tool on exactly the incidents it explains (eval 2026-10-27).
        "azureEvents": _azure_findings(ctx.get("clusterId"), onset or info["alert_ms"]),
        "context": ctx,
        "issues": issues,
        # redis usage + queue sizes + heap/cpu/postgres — almost all you need, no SQL.
        "clusterData": cluster_data,
        "componentHealth": component_health,
    }


def _kubectl_text(execution_id: str, command: str) -> str:
    out = run_kubectl_read.__wrapped__(execution_id, command) \
        if hasattr(run_kubectl_read, "__wrapped__") else run_kubectl_read(execution_id, command)
    for t in (out.get("tasks") or []) if isinstance(out, dict) else []:
        o = t.get("output")
        if isinstance(o, dict) and isinstance(o.get("result"), str):
            return o["result"]
    return ""


@tool(timeout_seconds=_T)
def get_node_churn(execution_id: str) -> dict:
    """Were the cluster's NODES replaced around the alert (node-pool upgrade, auto-repair,
    autoscaler scale-down)? Call this EARLY for any "has failed", "is down", pod-not-Running
    or restart alert: a node rollout moves every pod, and single-replica Grafana/workers or a
    conductor pod that has no IP yet make the health check fail while nothing is broken.

    Measured against when the failures STARTED (the first failed run of the current streak),
    not this firing and not now. Verdict NODE_CHURN = the nodes changed at the
    alert, which explains the failure; NO_CHURN = rule node movement out; UNKNOWN = the nodes
    were replaced again since, so the cluster no longer shows it.

    Args:
        execution_id: incident execution id.
    """
    info = _disp().alert_info(execution_id)
    alert_ms = info["alert_ms"]
    if not alert_ms:
        return {"verdict": "UNKNOWN", "detail": "alert time not found on the execution"}
    # A standing alert started when the failures began, not at this firing.
    onset_ms = _disp().failing_since(_context(execution_id).get("clusterId"), alert_ms, info["issues"])
    nodes = _kubectl_text(execution_id, "get nodes -o custom-columns=NAME:.metadata.name,"
                          "CREATED:.metadata.creationTimestamp,VERSION:.status.nodeInfo.kubeletVersion")
    events = _kubectl_text(execution_id, "get events -A --field-selector involvedObject.kind=Node "
                           "-o custom-columns=TIME:.lastTimestamp,REASON:.reason,NODE:.involvedObject.name")
    report = summarize_node_churn(nodes, events, onset_ms)
    report["judgedAt"] = "failure onset" if onset_ms < alert_ms else "this alert"
    report["failingSinceMs"] = onset_ms
    if not nodes:
        report["detail"] += " (kubectl get nodes returned nothing — possibly Forbidden for this agent)"
    return report


@tool(timeout_seconds=_T)
def get_alert_recurrence(execution_id: str, alert_signature: str) -> dict:
    """Is this alert NEW or has it been firing for a while? Call this EARLY (right
    after get_incident_details) — it's the first question a human on-call asks, and
    it changes everything: a one-off spike is an incident, but an alert firing on a
    third of recent health-checks is a standing capacity problem, not a fresh page.

    Looks back over this cluster's recent health_check runs and reports how often
    this alert TYPE fired. Cheap (one search, no deep dive). If the verdict is
    CHRONIC/RECURRING, say so up front and keep the investigation light — you're
    confirming a known condition, not discovering a new one.

    Args:
        execution_id: incident execution id (used to resolve the cluster).
        alert_signature: a SHORT, STABLE phrase identifying the alert TYPE — e.g.
            "Conductor Server CPU usage", "Redis instance is at", "Conductor has failed",
            "Prometheus is down". Do NOT include the varying numbers (percentages,
            pod ids) — that would defeat the match. Take it from the issues text.
    """
    ctx = _context(execution_id)
    cluster_id = ctx.get("clusterId")
    if not cluster_id:
        return {"error": "no_cluster_id", "detail": "cannot resolve clusterId for recurrence check"}
    runs = _disp().recent_health_checks(cluster_id, size=100)
    report = summarize_recurrence(runs, alert_signature)
    out = report.as_dict()
    out["clusterId"] = cluster_id
    out["alertSignature"] = alert_signature
    return out


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
def run_kubectl_read(execution_id: str, command: str) -> dict:
    """Run a READ-ONLY kubectl command inside the cluster (get / describe / logs /
    top / events / rollout history|status / explain / auth can-i). Any mutating
    verb (delete, apply, scale, exec, patch, rollout restart, ...) and any shell
    metacharacter is rejected BEFORE it reaches the cluster.

    Use when a dedicated tool doesn't cover the read you need — e.g.
    `describe pod X -n NS` for the OOMKill/eviction reason, `rollout history
    deployment/X` to date a rollout, or reading the ingress-nginx namespace.

    Cluster-wide reads (`get nodes`, `-A`) work on the clusters checked so far; if one
    comes back Forbidden, retry with the cluster's namespace (-n <ns>), which is visible
    in get_pods_data output / pod events.

    Args:
        execution_id: incident execution id.
        command: the kubectl command, without the leading "kubectl" (tolerated).
    """
    try:
        safe = ensure_readonly_kubectl(command)
    except NotReadOnlyKubectlError as exc:
        return {"error": "rejected_non_readonly_kubectl", "detail": str(exc), "command": command}
    return _disp().dispatch(
        "KUBECTL_UNRESTRICTED",
        "kubectl_unrestricted",
        _context(execution_id),
        {"unrestrictedCommand": safe},
    )


@tool(timeout_seconds=_T)
def download_heap_dump(execution_id: str, pod_name: str) -> dict:
    """Capture a JVM heap dump from ONE pod via ah5r-prod and return where it was
    stored (``paths``) — the engineer analyzes it (Eclipse MAT) against recent changes.

    HEAVY: jmap pauses the JVM (stop-the-world) for seconds on a multi-GB heap.
    Use ONLY when the alert itself is heap/memory pressure, on ONLY the single
    highest-heap pod, at most once per incident. Never dump more than one pod.

    Args:
        execution_id: incident execution id.
        pod_name: the ONE highest-heap conductor/worker pod (from get_top_output).
    """
    return _disp().dispatch(
        "DOWNLOAD_HEAP_DUMP", "download_heap_dump", _context(execution_id), {"podName": pod_name}
    )


@tool(timeout_seconds=_T)
def download_thread_dump(execution_id: str, pod_name: str) -> dict:
    """Capture a JVM thread dump (jstack) from a pod via ah5r-prod and return where
    it was stored (``paths``). Cheap and near-instant — the go-to evidence for CPU
    saturation, hot loops, stuck sweeper threads, and deadlocks.

    Use on the hottest pod when a CPU alert has no obvious cause in the logs;
    the dump names the busy threads. Prefer this over a heap dump for CPU issues.

    Args:
        execution_id: incident execution id.
        pod_name: the CPU-hot pod (from get_top_output / the alert text).
    """
    return _disp().dispatch(
        "DOWNLOAD_THREAD_DUMP", "download_thread_dump", _context(execution_id), {"podName": pod_name}
    )


_POD_RE = re.compile(r"^[a-z0-9]([-a-z0-9]*[a-z0-9])?$")


def _exec(ctx: dict, pod: str, argv: str) -> str:
    """Run ONE read-only command inside a pod and return stdout as text.

    Uses the unrestricted kubectl channel because `exec` is not in the read-only
    verb allowlist, but the caller may only pass jcmd/grep invocations that read —
    nothing here mutates cluster or JVM state (a thread dump is a read).
    """
    r = _disp().dispatch(
        "KUBECTL_UNRESTRICTED", "kubectl_unrestricted", ctx,
        {"unrestrictedCommand": f"exec {pod} -- {argv}"},
    )
    if not isinstance(r, dict):
        return ""
    out = r.get("output")
    out = out.get("result") if isinstance(out, dict) else out
    return str(out or "").replace("\\n", "\n")


@tool(timeout_seconds=_T)
def get_thread_summary(execution_id: str, pod_name: str) -> dict:
    """What the JVM's threads are ACTUALLY doing — states, the RUNNABLE frames
    burning CPU, and any lock pileup. Use this for EVERY CPU or heap alert.

    Unlike download_thread_dump (which only uploads the file and hands back an S3
    path you cannot read), this returns the analysed facts inline. A CPU diagnosis
    must rest on these numbers, never on a workflow backlog count alone: a large
    RUNNING backlog with ZERO runnable application threads means the JVM is WEDGED,
    not busy, and the backlog is a symptom.

    Args:
        execution_id: incident execution id.
        pod_name: the CPU-hot / suspect pod (from get_top_output or the alert text).
    """
    if not _POD_RE.match(pod_name or ""):
        return {"error": "invalid_pod_name", "pod_name": pod_name}
    ctx = _context(execution_id)

    listing = _exec(ctx, pod_name, "jcmd -l")
    pid = next((ln.split()[0] for ln in listing.splitlines()
                if ln.strip() and ln.split()[0].isdigit() and "jcmd" not in ln), None)
    if not pid:
        return {"error": "jvm_pid_not_found", "detail": listing[:200],
                "hint": "the JVM is often PID 14, not PID 1"}

    # The remote side splits the command on whitespace, so every grep PATTERN below must
    # be a single token — no spaces, and no filename containing one either.
    dump = "/tmp/oncall-threads.txt"
    written = _exec(ctx, pod_name, f"jcmd {pid} Thread.dump_to_file -overwrite -format=plain {dump}")
    if "Created" not in written:
        return {"error": "thread_dump_failed", "pod": pod_name, "jvm_pid": pid,
                "detail": written[:200]}

    # The dump is ~700KB and the agent-handler truncates results at ~8KB, so the whole
    # file cannot come back. `-format=plain` also carries no Thread.State: line and no
    # lock addresses — only `#id "name"` headers and frames. What DOES fit is a counter
    # per diagnostic frame: one small `grep -c` each. These are the magnitudes that
    # separate "wedged" from "genuinely busy", which is the question a CPU alert asks.
    def count(pattern: str) -> int:
        raw = _exec(ctx, pod_name, f"grep -c -e {pattern} {dump}").strip()
        # grep exits 1 on zero matches and the handler returns empty for a non-zero
        # exit — that is a legitimate 0, not a failure. total_threads proves the
        # file and grep both work, so treat empty as absent-frame.
        return int(raw) if raw.isdigit() else 0

    total = count("^#")
    # Every way a thread waits without burning CPU — not just Unsafe.park. Counting only
    # park left Object.wait / sleep / epoll / accept / unmounted virtual threads as
    # "active", so the WEDGE verdict could never fire.
    parked = sum(count(p) for p in ("Unsafe.park", "Object.wait", "Thread.sleep",
                                    "EPoll.wait", "KQueue.poll", "Net.accept",
                                    "VirtualThread.park", "Continuation.yield"))
    counts = {
        "redis_pool_borrow": count("GenericObjectPool.borrowObject"),
        "lock_acquire": count("ReentrantLock.lock"),
        "sweeper": count("OrkesWorkflowSweeper"),
        "decider": count("OrkesWorkflowExecutor.decide"),
        "jdbc_read": count("PgStatement.execute"),
        "socket_read": count("NioSocketImpl.read"),
    }
    active = max(total - parked, 0) if total >= 0 and parked >= 0 else -1
    blocked_on_pool = counts["redis_pool_borrow"]

    if total > 0 and active == 0:
        verdict = (f"WEDGE, not load: {total} threads, {parked} parked, ZERO active. "
                   "CPU is near-zero because parked threads consume none.")
    elif blocked_on_pool >= 20 and active <= 2:
        verdict = (f"WEDGE, not load: {blocked_on_pool} threads blocked borrowing a Redis "
                   f"connection and only {active} active. Not a backlog problem.")
    elif active > 0:
        verdict = (f"{active} of {total} threads are active — attribute CPU to the "
                   "non-zero frame counters below, not to a workflow backlog count.")
    else:
        verdict = "inconclusive — could not read thread counts"

    return {
        "pod": pod_name, "jvm_pid": pid, "dump_bytes_on_pod": dump,
        "total_threads": total, "parked_threads": parked, "active_threads": active,
        "frame_counts": counts, "verdict": verdict,
        "note": ("counter-based: -format=plain has no thread states or lock addresses, and "
                 "the full dump exceeds the result cap. For lock OWNERSHIP capture "
                 f"`jcmd {pid} Thread.print -l` on the pod manually."),
    }


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
def check_ingress_config(execution_id: str) -> dict:
    """Is every ingress actually served, and with a valid certificate? Call this for ANY
    "domain X is down" / DNS / certificate alert, BEFORE concluding "load balancer" or
    "external network". Reads every ingress (class, hosts, TLS secret, address), the
    IngressClasses that exist, cert-manager Certificates, and fetches the certificate each
    host REALLY serves from outside. Flags: an ingress whose class no controller owns (it
    was disabled or mis-set — nothing serves the host, and it gets no address), nginx's
    FAKE default certificate, an expired/untrusted cert, a Certificate that is not Ready.

    Args:
        execution_id: incident execution id.
    """
    ingress = _kubectl_text(execution_id, "get ingress -A -o custom-columns=NS:.metadata.namespace,"
                            "NAME:.metadata.name,CLASS:.spec.ingressClassName,HOSTS:.spec.rules[*].host,"
                            "TLS:.spec.tls[*].secretName,ADDR:.status.loadBalancer.ingress[*].ip")
    classes = _kubectl_text(execution_id, "get ingressclass -o custom-columns=NAME:.metadata.name")
    certs = _kubectl_text(execution_id, "get certificate -A -o custom-columns=NS:.metadata.namespace,"
                          "NAME:.metadata.name,READY:.status.conditions[0].status,"
                          "MESSAGE:.status.conditions[0].message")
    hosts = {h for line in ingress.splitlines()[1:] if len(line.split()) > 3
             for h in line.split()[3].split(",") if "." in h}
    report = check_ingresses(ingress, classes, certs, {h: served_certificate(h) for h in sorted(hosts)})
    if not ingress:
        report["problems"].append("kubectl get ingress returned nothing — possibly Forbidden for this agent")
    # Who changed an ingress nothing serves, and when: managers include "kubectl-edit" for hand edits.
    for ing in report["ingresses"]:
        if ing["class"] != "<none>" and ing["class"] not in report["ingressClasses"]:
            ing["changedBy"] = _kubectl_text(execution_id, f"get ingress {ing['name']} -n {ing['namespace']} "
                                             "-o custom-columns=MANAGER:.metadata.managedFields[*].manager,"
                                             "TIME:.metadata.managedFields[*].time")
    return report


@tool(timeout_seconds=_T)
def get_azure_events(execution_id: str) -> dict:
    """For AZURE clusters: what Azure itself reported for this cluster's managed Redis and
    Postgres around when the failures STARTED — Redis `Errors` by type (AOF = persistence
    write failed and Redis refused writes with MISCONF; Failover = patching/maintenance),
    Postgres not-alive windows (restart/failover), and activity-log events (maintenance,
    scaling, config changes, with who did it). Call it whenever /health shows redis or
    postgres BAD, or conductor pods were killed together, on an Azure cluster — it answers
    "was it the managed service?" directly instead of inferring it from pod restarts.

    Args:
        execution_id: incident execution id.
    """
    ctx = _context(execution_id)
    info = _disp().alert_info(execution_id)
    if not info["alert_ms"]:
        return {"error": "alert time not found on the execution"}
    onset_ms = _disp().failing_since(ctx.get("clusterId"), info["alert_ms"], info["issues"])
    try:
        return azure_events(ctx.get("clusterId"), onset_ms)
    except Exception as exc:
        return {"error": "azure_lookup_failed", "detail": str(exc)[:300]}


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



@tool(timeout_seconds=_T)
def analyze_sweeper_waste(execution_id: str, pod_name: str, lines: int = 300) -> dict:
    """Is the sweeper doing NECESSARY work, or re-sweeping workflows that can never
    advance? Call this whenever the sweeper shows up as a hot frame — a backlog COUNT
    alone never answers it.

    OrkesWorkflowSweeper.sweep() drains the decider queue only when a workflow is null
    or terminal; everything else is swept again forever. When decide() changes nothing
    it logs "Going to repair the task ..." and bumps `queue_message_repushed`. This
    counts those against "Running sweeper for workflow" and names the stuck tasks.

    Args:
        execution_id: incident execution id.
        pod_name: a conductor pod (from get_pods_data).
        lines: log window size; larger sees more but costs more.
    """
    import json as _json
    from .sweeper_waste import summarize_sweeper_waste
    raw = pull_pod_logs.__wrapped__(execution_id, pod_name, grep="OrkesWorkflowSweeper", lines=lines) \
        if hasattr(pull_pod_logs, "__wrapped__") else pull_pod_logs(execution_id, pod_name,
                                                                    grep="OrkesWorkflowSweeper",
                                                                    lines=lines)
    if isinstance(raw, dict) and raw.get("error"):
        return {"error": "sweeper_log_read_failed", "detail": raw.get("error"),
                "verdict": "unknown — could not read the sweeper log; this says NOTHING about the sweeper"}
    out = summarize_sweeper_waste(_json.dumps(raw, default=str).replace("\\n", "\n"))
    out["pod"] = pod_name
    out["window_lines"] = lines
    out["caveat"] = ("counts come from one grepped window; if wasted_sweeps is 0 but the "
                     "sweeper is hot, widen `lines` before concluding the work is genuine.")
    return out



def _sql_rows(execution_id: str, sql: str) -> list[dict]:
    """run_sql_select, unwrapped to plain rows. The handler double-encodes: the
    `result` field is itself a JSON string."""
    import json as _json
    r = run_sql_select.__wrapped__(execution_id, sql) if hasattr(run_sql_select, "__wrapped__") \
        else run_sql_select(execution_id, sql)
    if isinstance(r, dict) and r.get("error"):
        raise RuntimeError(f"SQL lookup failed: {r.get('error')} {str(r.get('detail') or '')[:150]}")
    out = r.get("output") if isinstance(r, dict) else None
    res = (out or {}).get("result") if isinstance(out, dict) else out
    if isinstance(res, str):
        try:
            res = _json.loads(res).get("result", res)
        except Exception:
            raise RuntimeError(f"SQL lookup returned unparseable output: {res[:150]}")
    if not isinstance(res, list):
        raise RuntimeError(f"SQL lookup returned no rows field: {str(res)[:150]}")
    return res


@tool(timeout_seconds=_T)
def get_running_backlog_buckets(execution_id: str, top: int = 8) -> dict:
    """WHICH workflow definitions make up the RUNNING backlog, and how old they are.

    Use this instead of ever quoting a bare RUNNING count. "16,555 RUNNING" is not
    actionable; "two definitions are 93% of it, both starting 17 March" is.

    Queries the workflow_archive_shard_* tables directly — the parent workflow_archive
    returns nothing (it does not route). Small fleets are read exactly; large ones are
    hash-distributed and uniform, so one shard is sampled and scaled, flagged as
    ESTIMATED. Also surfaces the overall failure rate, which is its own finding.

    Args:
        execution_id: incident execution id.
        top: how many definitions to report.
    """
    try:
        return _running_backlog_buckets(execution_id, top)
    except RuntimeError as exc:  # a failed lookup is not "no backlog"
        return {"error": "backlog_lookup_failed", "detail": str(exc)}


def _running_backlog_buckets(execution_id: str, top: int) -> dict:
    from .running_backlog import plan_shard_query, build_backlog_report
    # Two small queries, not one big one: one-staging has 301 shards and listing them
    # all exceeds the ~8KB result cap, which silently comes back empty.
    counted = _sql_rows(execution_id, """SELECT count(*) AS shard_count FROM pg_stat_user_tables
        WHERE relname LIKE 'workflow_archive_shard%' AND n_live_tup > 0""")
    fleet = int(counted[0].get("shard_count") or 0) if counted else 0
    shards = _sql_rows(execution_id, """SELECT relname, n_live_tup FROM pg_stat_user_tables
        WHERE relname LIKE 'workflow_archive_shard%' AND n_live_tup > 0
        ORDER BY n_live_tup DESC LIMIT 4""")
    plan = plan_shard_query(shards, total_populated=fleet or None)
    if plan["mode"] == "none":
        return {"error": "no_populated_archive_shards",
                "hint": "RUNNING state may be Redis-only on this cluster"}
    union = " UNION ALL ".join(f"SELECT status, workflow_name, created_on FROM {t}"
                               for t in plan["shards"])
    status_rows = _sql_rows(execution_id,
        f"SELECT status, count(*) AS n FROM ({union}) x GROUP BY status ORDER BY n DESC")
    bucket_rows = _sql_rows(execution_id,
        f"""SELECT workflow_name, count(*) AS running, min(created_on) AS oldest
            FROM ({union}) x WHERE status='RUNNING'
            GROUP BY workflow_name ORDER BY running DESC LIMIT {int(top)}""")
    return build_backlog_report(plan, status_rows, bucket_rows, top=top)



@tool(timeout_seconds=_T)
def check_known_issues(execution_id: str, repushed_task_types: str = "",
                       waste_ratio: float = -1.0, thread_names: str = "",
                       frames: str = "") -> dict:
    """Is this a bug we already fixed upstream? Reads the running conductor image tag and
    matches it against known issues plus the symptoms you have already measured.

    Call this on ANY cpu/heap/'Conductor has failed' alert, after get_thread_summary and
    analyze_sweeper_waste, passing what they found. Both multi-hour outages this month
    were fixed upstream weeks earlier — nobody linked the version to the merged PR, so
    each was re-diagnosed from scratch. This closes that loop without a human.

    Version parsing fails CLOSED: branch-style tags exist in this fleet and are reported
    as UNKNOWN rather than assumed safe.

    Args:
        execution_id: incident execution id.
        repushed_task_types: comma-separated task types being re-pushed (WAIT, HUMAN, ...),
            from the `queue_message_repushed` metric or the sweeper repair lines.
        waste_ratio: analyze_sweeper_waste()["waste_ratio"], or -1 if unknown.
        thread_names: comma-separated notable thread names from the dump.
        frames: comma-separated notable stack frames from the dump.
    """
    from .known_issues import match_known_issues
    img = run_kubectl_read.__wrapped__(execution_id,
        "get deployment orkes-conductor-deployment -o jsonpath={.spec.template.spec.containers[?(@.name=='conductor')].image}") \
        if hasattr(run_kubectl_read, "__wrapped__") else run_kubectl_read(execution_id,
        "get deployment orkes-conductor-deployment -o jsonpath={.spec.template.spec.containers[?(@.name=='conductor')].image}")
    out = img.get("output") if isinstance(img, dict) else None
    tag = str((out.get("result") if isinstance(out, dict) else out) or "").strip()
    split = lambda v: {x.strip() for x in v.split(",") if x.strip()}
    return match_known_issues(
        tag or None,
        repushed_task_types=split(repushed_task_types) or None,
        waste_ratio=None if waste_ratio < 0 else waste_ratio,
        thread_names=split(thread_names) or None,
        frames=split(frames) or None,
    )



_CONDUCTOR_REPO = os.environ.get("ORKES_CONDUCTOR_REPO", str(Path.home() / "Orkes" / "orkes-conductor"))


def _git(args: list[str]) -> list[str]:
    import subprocess
    try:
        r = subprocess.run(["git", "-C", _CONDUCTOR_REPO, *args],
                           capture_output=True, text=True, timeout=45)
        return [ln for ln in r.stdout.splitlines() if ln.strip()] if r.returncode == 0 else []
    except Exception:
        return []


@tool(timeout_seconds=_T)
def find_missing_fixes(execution_id: str, symbol: str, top: int = 8) -> dict:
    """Does an upstream fix already exist for the code you are looking at?

    GENERAL — no prior knowledge of the bug required. Give it any code identifier you
    OBSERVED (a hot RUNNABLE frame, the class in a log line, an exception type) and it
    resolves that to a source file and asks git what has been fixed in that code since
    the version this cluster runs, including PR numbers.

    Use it the moment a frame or class becomes your prime suspect, BEFORE reasoning the
    bug out from first principles. Both multi-hour outages this month were already fixed
    upstream; nobody checked.

    Args:
        execution_id: incident execution id (used to read the running image tag).
        symbol: a class or file name, e.g. "OrkesWorkflowSweeper" or "ExecutorUtils".
        top: how many candidate commits to return.
    """
    from .fix_finder import parse_log, build_report
    from .known_issues import parse_version
    if not Path(_CONDUCTOR_REPO, ".git").exists():
        return {"error": "conductor_repo_unavailable", "path": _CONDUCTOR_REPO,
                "hint": "set ORKES_CONDUCTOR_REPO to a checkout of orkes-conductor"}
    safe = re.sub(r"[^A-Za-z0-9_.$]", "", symbol or "")
    if not safe:
        return {"error": "invalid_symbol", "symbol": symbol}

    img = run_kubectl_read.__wrapped__(execution_id,
        "get deployment orkes-conductor-deployment -o jsonpath={.spec.template.spec.containers[?(@.name=='conductor')].image}") \
        if hasattr(run_kubectl_read, "__wrapped__") else run_kubectl_read(execution_id,
        "get deployment orkes-conductor-deployment -o jsonpath={.spec.template.spec.containers[?(@.name=='conductor')].image}")
    out = img.get("output") if isinstance(img, dict) else None
    tag = str((out.get("result") if isinstance(out, dict) else out) or "").strip()
    parsed = parse_version(tag)
    if parsed is None:
        return build_report(safe, [], None, [], [], top=top)

    _git(["fetch", "origin", "main", "--tags", "-q"])
    # The running build may be an rc ("5.5.0-rc19"): diff from THAT tag, not the bare
    # semver, and refuse to answer when no tag exists — an empty git log means "unknown",
    # not "this code is current".
    raw = tag.rsplit(":", 1)[-1].strip()
    version = next((c for c in (f"v{raw}", raw, "v" + ".".join(map(str, parsed)))
                    if _git(["rev-parse", "--verify", "-q", f"refs/tags/{c}"])), None)
    if version is None:
        return {"error": "running_version_tag_not_found", "image_tag": raw,
                "detail": "no matching git tag — missing fixes cannot be computed; do not read this as current"}
    paths = [p for p in _git(["ls-tree", "-r", "--name-only", "origin/main"])
             if p.endswith(f"{safe}.java") and "/test/" not in p]
    if not paths:
        return {"error": "symbol_not_found_in_repo", "symbol": safe, "running_version": version}

    commits, merges = [], []
    for p in paths:
        commits += parse_log(_git(["log", "--oneline", f"{version}..origin/main", "--", p]))
        merges += parse_log(_git(["log", "--oneline", "--merges", "--full-history",
                                  f"{version}..origin/main", "--", p]))
    seen, uniq = set(), []
    for c in commits:
        if c["sha"] not in seen:
            seen.add(c["sha"]); uniq.append(c)
    return build_report(safe, paths, version, uniq, merges, top=top)


ALL_TOOLS = [
    get_incident_details,
    get_alert_recurrence,
    get_node_churn,
    get_cluster_metrics,
    get_infrastructure_metrics,
    get_pods_data,
    get_deployments_info,
    get_pod_events,
    get_top_output,
    run_kubectl_read,
    download_heap_dump,
    download_thread_dump,
    get_thread_summary,
    analyze_sweeper_waste,
    get_running_backlog_buckets,
    check_known_issues,
    find_missing_fixes,
    pull_pod_logs,
    get_ingress_info,
    check_ingress_config,
    get_azure_events,
    run_sql_select,
]
