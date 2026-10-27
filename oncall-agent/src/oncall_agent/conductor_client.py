"""Thin wrapper over the ah5r-prod Conductor API.

Two jobs:
  * read the failing ``health_check`` execution (issues, per-component health, and
    the org/cluster/cloudEnvironmentTag context),
  * dispatch a read-only agent-handler workflow (``pull_logs``, ``get_cluster_metrics``,
    ``sql_conductor`` …) and poll its execution for the result.

The agent-handler workflows self-bootstrap the customer-cluster JWT via their first
``prepare_agent_handler`` task, so we only pass the org/cluster context — no JWT minting.
"""
from __future__ import annotations

import json
import logging
import re
import time
import uuid
from typing import Any, Callable

from conductor.client.configuration.configuration import Configuration
from conductor.client.configuration.settings.authentication_settings import (
    AuthenticationSettings,
)
from conductor.client.http.models.start_workflow_request import StartWorkflowRequest
from conductor.client.orkes_clients import OrkesClients

_TERMINAL = {"COMPLETED", "FAILED", "TERMINATED", "TIMED_OUT", "PAUSED"}

# Orchestration tasks that run on ah5r-prod itself (orkes-saas workers), not in the
# customer cluster — they must NOT be routed to the customer domain. Everything else
# is wildcarded to the customer-cluster agent's domain (orgId#-#clusterName), which is
# how the control plane routes agent-handler tasks.
_CONTROL_PLANE_TASKS = (
    "prepare_agent_handler",
    "save_agent_handler_results",
    "health_check_issues",
    "cluster_metrics_ingestion",
    "save_conductor_metrics",
    "find_latest_conductor_metrics_records",
    "certificates_expiration_summary",
    "fetch_deployment_info",
    "save_eks_version",
    "HTTP",
)


def _trim(value: Any, max_len: int = 8000) -> Any:
    """Keep tool outputs from blowing up the LLM context without destroying their shape.

    Long strings keep their head (headers, first lines) AND their tail (the newest log
    lines — the evidence); dicts and lists are trimmed field by field, so callers that
    read ``output["result"]`` still get a dict instead of one truncated JSON string.
    """
    if isinstance(value, str):
        if len(value) <= max_len:
            return value
        head = max_len // 5
        return (value[:head] + f"\n... [{len(value) - max_len} chars cut] ...\n"
                + value[-(max_len - head):])
    if isinstance(value, dict):
        return {k: _trim(v, max_len) for k, v in value.items()}
    if isinstance(value, list):
        return [_trim(v, max_len) for v in value[:200]]
    return value


log = logging.getLogger("oncall_agent")


_POD = re.compile(r"\b[a-z0-9-]+-[a-z0-9]{8,10}-[a-z0-9]{5}\b")


def issue_keys(reason: str | None) -> set[str]:
    """The issue lines of a health-check alert, normalized for comparison.

    The first line is boilerplate shared by every alert ("The health-checking has FAILED
    for ..."), so only the issue lines count; severity markers, pod names and numbers are
    dropped so one issue matches across firings.
    """
    keys = set()
    for line in (reason or "").splitlines()[1:]:
        line = re.sub(r"^\W*(CRITICAL|MAJOR|MINOR|WARNING)\W*", "", line.strip(), flags=re.I)
        line = _POD.sub("<pod>", line.lower())
        line = re.sub(r"[\d.]+%?", "#", line).strip()
        if line:
            keys.add(line)
    return keys


def _epoch_ms(value: Any) -> int | None:
    """Search results carry start_time as epoch ms or an ISO-8601 string."""
    if isinstance(value, (int, float)):
        return int(value)
    if isinstance(value, str) and value:
        from datetime import datetime
        try:
            return int(datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp() * 1000)
        except ValueError:
            return int(value) if value.isdigit() else None
    return None


class ConductorDispatcher:
    def __init__(
        self,
        server_url: str,
        key_id: str,
        key_secret: str,
        client_factory: Callable[[], Any] | None = None,
    ):
        def _default_factory():
            config = Configuration(
                server_api_url=server_url,
                authentication_settings=AuthenticationSettings(
                    key_id=key_id, key_secret=key_secret
                ),
            )
            return OrkesClients(configuration=config).get_workflow_client()

        self._make_client = client_factory or _default_factory
        self._wf = self._make_client()

    def _call(self, op: Callable[[], Any]) -> Any:
        """Run *op*; on failure rebuild the client once and retry.

        A transient network blip can leave conductor-python's shared httpx
        client with a dead socket ("Bad file descriptor") and a poisoned auth
        token — every retry then reuses the broken client and the poll loop
        wedges (seen live 2026-07-23, ~4h stall). A fresh client gets a fresh
        pool and a fresh token exchange.
        """
        try:
            return op()
        except Exception as exc:
            log.warning("conductor call failed (%s) — rebuilding client and retrying", exc)
            self._wf = self._make_client()
            return op()

    # ── reads ────────────────────────────────────────────────
    def get_execution(self, workflow_id: str) -> dict:
        return self._summarize(
            self._call(lambda: self._wf.get_workflow(workflow_id, include_tasks=True))
        )

    def get_context(self, execution_id: str) -> dict:
        """Org / cluster / cloudEnvironmentTag read off a health_check execution input.

        ``cloudEnvironmentTag`` is not in the workflow input (it is produced by the
        ``prepare_agent_handler`` task), but ``sql_conductor`` reads it from the input,
        so derive it from the documented formula when absent:
        ``c`` + organizationId[:5] + ``-`` + clusterName.

        ``clusterName`` is not always top-level either: some health_check schedulers
        (all of Twilio's, seen live 2026-07-27) pass it only inside
        ``agentHandlerRequest``. It is load-bearing — ``dispatch`` builds the agent
        routing domain from it — so fall back to the nested copy rather than routing
        to ``<org>#-#None``, where nothing polls and every tool comes back empty.
        """
        wf = self._call(lambda: self._wf.get_workflow(execution_id, include_tasks=False))
        wf_input = getattr(wf, "input", None) or {}
        handler_request = wf_input.get("agentHandlerRequest") or {}
        if not isinstance(handler_request, dict):
            handler_request = {}
        org_id = wf_input.get("organizationId") or wf_input.get("customerId")
        cluster_name = wf_input.get("clusterName") or handler_request.get("clusterName")
        cloud_env_tag = wf_input.get("cloudEnvironmentTag")
        if not cloud_env_tag and org_id and cluster_name:
            cloud_env_tag = f"c{org_id[:5]}-{cluster_name}"
        return {
            "organizationId": org_id,
            "organizationName": wf_input.get("organizationName"),
            "clusterId": wf_input.get("clusterId"),
            "clusterName": cluster_name,
            "cloudEnvironmentTag": cloud_env_tag,
            "environment": wf_input.get("environment", "prod"),
        }

    def alert_info(self, execution_id: str) -> dict:
        """When the alert's health check ran (epoch ms) and its issue keys."""
        wf = self._call(lambda: self._wf.get_workflow(execution_id, include_tasks=False))
        wf_input = getattr(wf, "input", None) or {}
        at_ms = (wf_input.get("_scheduledTime") or wf_input.get("_executedTime")
                 or _epoch_ms(getattr(wf, "start_time", None)) or 0)
        return {"alert_ms": int(at_ms),
                "issues": issue_keys(getattr(wf, "reason_for_incompletion", None))}

    def failing_since(self, cluster_id: str, at_ms: int, issues: set[str] | None = None,
                      max_hours: int = 48) -> int:
        """Start of the unbroken run of health checks failing with the SAME issue as the alert.

        Walks back in 6h windows; the streak ends at the first run that is clean or fails
        only with other issues (a standing cert/API-key warning must not stretch an
        unrelated outage back for days). Returns ``at_ms`` itself when the previous run
        does not share an issue.
        """
        if not cluster_id or not at_ms:
            return at_ms
        onset = at_ms
        for window in range(max_hours // 6):
            hi = at_ms - window * 6 * 3_600_000
            result = self._call(lambda: self._wf.search(
                start=0, size=100, free_text=cluster_id,
                query=f"workflowType IN (health_check) AND startTime>{hi - 6 * 3_600_000} AND startTime<={hi}",
            ))
            runs = sorted(getattr(result, "results", None) or [],
                          key=lambda r: _epoch_ms(getattr(r, "start_time", None)) or 0, reverse=True)
            for r in runs:
                keys = issue_keys(getattr(r, "reason_for_incompletion", None))
                if not keys or (issues and not keys & issues):
                    return onset
                ms = _epoch_ms(getattr(r, "start_time", None))
                if ms is not None:
                    onset = min(onset, ms)
        return onset

    def runs_after(self, cluster_id: str, at_ms: int, n: int = 6) -> list[dict]:
        """The next ``n`` health checks after the alert: did it recover or keep failing?"""
        result = self._call(lambda: self._wf.search(
            start=0, size=50, free_text=cluster_id,
            query=f"workflowType IN (health_check) AND startTime>{at_ms + 60_000}",
        ))
        runs = sorted(getattr(result, "results", None) or [],
                      key=lambda r: _epoch_ms(getattr(r, "start_time", None)) or 0)[:n]
        return [{"startTime": getattr(r, "start_time", None),
                 "failing": bool(issue_keys(getattr(r, "reason_for_incompletion", None))),
                 "issues": sorted(issue_keys(getattr(r, "reason_for_incompletion", None)))}
                for r in runs]

    def recent_health_checks(self, cluster_id: str, size: int = 100) -> list[dict]:
        """Recent ``health_check`` runs for ONE cluster, newest first.

        Filters by the cluster's unique ``clusterId`` UUID via full-text search —
        deliberately NOT the human cluster name, which fuzzy-matches sibling
        clusters (``one-staging`` also matched other ``*-staging`` clusters and
        polluted the counts). A UUID is unique to the cluster, so the result set
        is deterministic. Returns each run's ``reason`` (the alert text lives in
        ``reasonForIncompletion``) and ``start_time`` (epoch ms) — enough for the
        pure recurrence classifier; no per-execution fetch, so it stays fast.

        ``size`` caps the window (default 100 ~= last 8h at the 5-min cadence);
        the search index is retention-bound to a few days regardless.
        """
        result = self._call(lambda: self._wf.search(
            start=0,
            size=size,
            free_text=cluster_id,
            query="workflowType IN (health_check)",
        ))
        runs: list[dict] = []
        for s in getattr(result, "results", None) or []:
            runs.append(
                {
                    "workflow_id": getattr(s, "workflow_id", None),
                    "start_time": getattr(s, "start_time", None),
                    "status": getattr(s, "status", None),
                    "reason": getattr(s, "reason_for_incompletion", None),
                }
            )
        return runs

    def latest_failed_health_check(self, cluster_name: str, at_ms: int) -> str | None:
        """Newest failed ``health_check`` run for exactly this cluster in the 30 min up to ``at_ms``."""
        result = self._call(lambda: self._wf.search(
            start=0, size=50, free_text=cluster_name,
            query=f"workflowType IN (health_check) AND startTime>{at_ms - 1_800_000} AND startTime<{at_ms + 60_000}",
        ))
        exact = re.compile(rf"clusterName={re.escape(cluster_name)}[,}}]")
        newest_first = sorted(getattr(result, "results", None) or [],
                              key=lambda r: _epoch_ms(getattr(r, "start_time", None)) or 0, reverse=True)
        hits = [s for s in newest_first
                if exact.search(getattr(s, "input", None) or "")
                and (getattr(s, "reason_for_incompletion", None) or "").startswith("*`[")]
        orgs = {m.group(1) for s in hits
                if (m := re.search(r"organizationId=([0-9a-f-]{36})", getattr(s, "input", None) or ""))}
        if len(orgs) > 1:
            log.warning("cluster name %s is failing in %d orgs; page is ambiguous", cluster_name, len(orgs))
            return None
        return getattr(hits[0], "workflow_id", None) if hits else None

    # ── dispatch ─────────────────────────────────────────────
    def dispatch(
        self,
        command: str,
        workflow_name: str,
        context: dict,
        parameters: dict | None = None,
        timeout_s: int = 180,
        poll_s: int = 4,
    ) -> dict:
        parameters = parameters or {}
        wf_input: dict[str, Any] = {
            "customerId": context.get("organizationId"),
            "organizationId": context.get("organizationId"),
            "organizationName": context.get("organizationName"),
            "clusterId": context.get("clusterId"),
            "agentHandlerId": str(uuid.uuid4()),
            "cloudEnvironmentTag": context.get("cloudEnvironmentTag"),
            "environment": context.get("environment", "prod"),
            "requestedBy": None,
            "agentHandlerRequest": {
                "clusterName": context.get("clusterName"),
                "command": command,
                "parameters": parameters,
            },
        }
        # Some workflows (e.g. pull_logs) read params from the top-level workflow
        # input; others (e.g. sql_conductor) read them from agentHandlerRequest.parameters.
        # Setting both covers every convention without clobbering the core fields.
        for key, val in parameters.items():
            wf_input.setdefault(key, val)

        # Route customer-cluster tasks to that cluster's agent domain; keep
        # control-plane tasks on ah5r-prod (NO_DOMAIN). Without this the action
        # task sits in the default queue and the in-cluster agent never polls it.
        customer_domain = f"{context.get('organizationId')}#-#{context.get('clusterName')}"
        task_to_domain = {"*": customer_domain}
        for task_name in _CONTROL_PLANE_TASKS:
            task_to_domain[task_name] = "NO_DOMAIN"

        request = StartWorkflowRequest(
            name=workflow_name,
            input=wf_input,
            correlation_id=customer_domain,
            task_to_domain=task_to_domain,
        )
        wf_id = self._call(lambda: self._wf.start_workflow(request))
        return self._poll(wf_id, timeout_s, poll_s)

    def _poll(self, wf_id: str, timeout_s: int, poll_s: int) -> dict:
        deadline = time.time() + timeout_s
        while True:
            wf = self._call(lambda: self._wf.get_workflow(wf_id, include_tasks=True))
            status = getattr(wf, "status", None)
            if status in _TERMINAL or time.time() >= deadline:
                out = self._summarize(wf)
                if status != "COMPLETED":
                    # A still-running or failed dispatch must not read as an empty result.
                    out["error"] = ("dispatch_timed_out" if status not in _TERMINAL
                                    else f"dispatch_{str(status).lower()}")
                return out
            time.sleep(poll_s)

    @staticmethod
    def _summarize(wf: Any) -> dict:
        tasks = []
        for t in getattr(wf, "tasks", None) or []:
            tasks.append(
                {
                    "ref": getattr(t, "reference_task_name", None),
                    "type": getattr(t, "task_type", None),
                    "status": getattr(t, "status", None),
                    "reason": getattr(t, "reason_for_incompletion", None),
                    "output": _trim(getattr(t, "output_data", None)),
                }
            )
        return {
            "workflowId": getattr(wf, "workflow_id", None),
            "status": getattr(wf, "status", None),
            "input": _trim(getattr(wf, "input", None)),
            "output": _trim(getattr(wf, "output", None)),
            "tasks": tasks,
        }
