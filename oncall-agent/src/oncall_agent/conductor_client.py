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
import time
import uuid
from typing import Any

from conductor.client.configuration.configuration import Configuration
from conductor.client.configuration.settings.authentication_settings import (
    AuthenticationSettings,
)
from conductor.client.orkes_clients import OrkesClients

_TERMINAL = {"COMPLETED", "FAILED", "TERMINATED", "TIMED_OUT", "PAUSED"}


def _trim(value: Any, max_len: int = 8000) -> Any:
    """Keep tool outputs from blowing up the LLM context."""
    try:
        rendered = json.dumps(value, default=str)
    except Exception:
        rendered = str(value)
    if len(rendered) > max_len:
        return rendered[:max_len] + f"... [truncated {len(rendered) - max_len} chars]"
    return value


class ConductorDispatcher:
    def __init__(self, server_url: str, key_id: str, key_secret: str):
        config = Configuration(
            server_api_url=server_url,
            authentication_settings=AuthenticationSettings(
                key_id=key_id, key_secret=key_secret
            ),
        )
        self._wf = OrkesClients(configuration=config).get_workflow_client()

    # ── reads ────────────────────────────────────────────────
    def get_execution(self, workflow_id: str) -> dict:
        return self._summarize(self._wf.get_workflow(workflow_id, include_tasks=True))

    def get_context(self, execution_id: str) -> dict:
        """Org / cluster / cloudEnvironmentTag read off a health_check execution input."""
        wf = self._wf.get_workflow(execution_id, include_tasks=False)
        wf_input = getattr(wf, "input", None) or {}
        return {
            "organizationId": wf_input.get("organizationId") or wf_input.get("customerId"),
            "organizationName": wf_input.get("organizationName"),
            "clusterId": wf_input.get("clusterId"),
            "clusterName": wf_input.get("clusterName"),
            "cloudEnvironmentTag": wf_input.get("cloudEnvironmentTag"),
            "environment": wf_input.get("environment", "prod"),
        }

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

        correlation_id = f"{context.get('organizationId')}#-#{context.get('clusterName')}"
        wf_id = self._wf.start_workflow_by_name(
            workflow_name, wf_input, correlationId=correlation_id
        )
        return self._poll(wf_id, timeout_s, poll_s)

    def _poll(self, wf_id: str, timeout_s: int, poll_s: int) -> dict:
        deadline = time.time() + timeout_s
        while True:
            wf = self._wf.get_workflow(wf_id, include_tasks=True)
            if getattr(wf, "status", None) in _TERMINAL or time.time() >= deadline:
                return self._summarize(wf)
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
