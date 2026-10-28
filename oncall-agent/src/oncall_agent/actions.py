"""The only changes the agent may make, each one approved by a human first.

Two narrow tools, not a generic "kubectl": the model picks WHICH deployment (one of
three) or WHAT heap size (bounded by the container's own limit); it never writes a
patch, a command or a cluster name. The cluster always comes from the incident.

Modes (``ONCALL_ACTIONS``):
* ``off``     — no action tools.
* ``propose`` — the tools only describe what they would do (eval, dry runs). Their task
                names end in ``_dryrun`` so they can never be picked up by a live worker.
* ``approve`` — the tools pause on an Agentspan HUMAN task (``approval_required``); the
                listener posts the proposal to Slack and approves/rejects it from a thread
                reply. Approved, the tool runs the ah5r workflow, waits for the rollout and
                reports before -> after.
"""
from __future__ import annotations

import re
import time

from conductor.ai.agents import tool

DEPLOYMENTS = {
    "conductor": "orkes-conductor-deployment",
    "workers": "orkes-workers-deployment",
    "agent": "orkes-agent-deployment",
}
HEAP_MAX_SHARE = 0.65  # -Xmx at most this share of the container memory limit (off-heap needs the rest)
HEAP_MIN_MB = 512
_ROLLOUT_WAIT_S = 600


def _tools():
    from . import tools  # late: tools imports the dispatcher and its config
    return tools


def _dispatch(execution_id: str, command: str, workflow: str, params: dict, label: str) -> dict:
    t = _tools()
    out = t._disp().dispatch(command, workflow, t._context(execution_id),
                             {**params, "customCommandLabel": f"on-call agent (approved): {label}"},
                             timeout_s=300)
    status = str(out.get("status") or "").upper() if isinstance(out, dict) else ""
    if status != "COMPLETED":
        raise RuntimeError(f"{workflow} ended {status or 'unknown'}: {str(out)[:300]}")
    return out


def _wait_rollout(execution_id: str, deployment: str) -> str:
    """Block until the rollout finishes (new pods Ready, old ones gone) or time out."""
    t = _tools()
    ns = t._namespace(execution_id)
    deadline = time.time() + _ROLLOUT_WAIT_S
    last = ""
    while time.time() < deadline:
        last = t._kubectl_text(execution_id, f"rollout status deployment/{deployment} -n {ns} --timeout=20s")
        if "successfully rolled out" in last:
            return last.strip()
        time.sleep(15)
    raise RuntimeError(f"rollout of {deployment} not finished after {_ROLLOUT_WAIT_S}s: {last.strip()[:200]}")


def _heap_and_limit(execution_id: str) -> tuple[str, int]:
    """The conductor container's JVM_MEMORY_SETTINGS and memory limit (MiB)."""
    t = _tools()
    ns = t._namespace(execution_id)
    base = f"get deploy {DEPLOYMENTS['conductor']} -n {ns} -o jsonpath="
    jvm = t._kubectl_text(execution_id, base + "{.spec.template.spec.containers[?(@.name=='conductor')]"
                                              ".env[?(@.name=='JVM_MEMORY_SETTINGS')].value}").strip()
    limit = t._kubectl_text(execution_id, base + "{.spec.template.spec.containers[?(@.name=='conductor')]"
                                                 ".resources.limits.memory}").strip()
    m = re.fullmatch(r"(\d+)(Mi|Gi|M|G)", limit)
    if not m:
        raise RuntimeError(f"cannot read the conductor memory limit (got {limit!r})")
    mb = int(m.group(1)) * (1024 if m.group(2).startswith("G") else 1)
    return jvm, mb


def _check_deployment(deployment: str) -> str:
    if deployment not in DEPLOYMENTS:
        raise ValueError(f"deployment must be one of {sorted(DEPLOYMENTS)}, not {deployment!r}")
    return DEPLOYMENTS[deployment]


def restart_deployment(execution_id: str, deployment: str, triage_summary: str) -> dict:
    """Rollout-restart ONE Orkes deployment in the incident's cluster (needs human approval).

    Use only when the cause is confirmed, still ongoing, and a restart clears it (e.g. a pod
    holding leaked DB connections, a wedged pod). Never for a self-healed alert.

    Args:
        execution_id: incident execution id.
        deployment: "conductor", "workers" or "agent".
        triage_summary: your 3-line *Cause*/*Action*/*Evidence* summary; shown to the approver.
    """
    name = _check_deployment(deployment)
    _dispatch(execution_id, "ROLLOUT_RESTART", "rollout_restart_app",
              {"resourceDeploymentName": name}, f"restart {name}")
    return {"executed": True, "action": f"rollout restart {name}",
            "rollout": _wait_rollout(execution_id, name)}


def set_conductor_heap(execution_id: str, xmx_mb: int, triage_summary: str) -> dict:
    """Set the conductor JVM heap (-Xms/-Xmx, in MB) and roll the pods (needs human approval).

    Use for conductor containers OOMKilled at their memory limit while the heap itself is not
    full: the heap plus off-heap memory does not fit. The value must leave room for off-heap
    (at most 65% of the container memory limit).

    Args:
        execution_id: incident execution id.
        xmx_mb: new heap size in MB (also used for -Xms).
        triage_summary: your 3-line *Cause*/*Action*/*Evidence* summary; shown to the approver.
    """
    before, limit_mb = _heap_and_limit(execution_id)
    if not HEAP_MIN_MB <= xmx_mb <= int(limit_mb * HEAP_MAX_SHARE):
        raise ValueError(f"xmx_mb={xmx_mb} outside {HEAP_MIN_MB}..{int(limit_mb * HEAP_MAX_SHARE)} "
                         f"(65% of the {limit_mb}Mi container limit)")
    after = f"-Xms{xmx_mb}M -Xmx{xmx_mb}M"
    patch = ('{"spec":{"template":{"spec":{"containers":[{"name":"conductor","env":['
             f'{{"name":"JVM_MEMORY_SETTINGS","value":"{after}"}}]}}]}}}}}}')
    name = DEPLOYMENTS["conductor"]
    _dispatch(execution_id, "PATCH_DEPLOYMENT", "patch_deployment",
              {"resource": name, "patchType": "strategic", "patchStatement": patch},
              f"conductor heap {before} -> {after}")
    return {"executed": True, "action": f"JVM_MEMORY_SETTINGS {before!r} -> {after!r}",
            "rollout": _wait_rollout(execution_id, name)}


ACTIONS = (restart_deployment, set_conductor_heap)


def describe(name: str, args: dict) -> str:
    """One line saying exactly what an action call will change."""
    base = name.removesuffix("_dryrun")
    if base == "restart_deployment":
        return f"rollout restart `{DEPLOYMENTS.get(args.get('deployment'), args.get('deployment'))}`"
    if base == "set_conductor_heap":
        return f"set conductor `JVM_MEMORY_SETTINGS` to `-Xms{args.get('xmx_mb')}M -Xmx{args.get('xmx_mb')}M` and roll the pods"
    return f"{name}({args})"


def _proposal(fn):
    def propose(**kwargs) -> dict:
        if "deployment" in kwargs:
            _check_deployment(kwargs["deployment"])
        return {"executed": False, "proposed": describe(fn.__name__, kwargs),
                "note": "dry run: proposed only — nothing was changed"}
    propose.__name__ = fn.__name__ + "_dryrun"
    propose.__doc__ = fn.__doc__.replace("(needs human approval)", "(DRY RUN: proposes, never executes)")
    propose.__annotations__ = dict(fn.__annotations__)
    import inspect
    propose.__signature__ = inspect.signature(fn)
    return propose


def action_tools(mode: str) -> list:
    if mode == "off":
        return []
    if mode == "propose":
        return [tool(timeout_seconds=30)(_proposal(fn)) for fn in ACTIONS]
    if mode == "approve":
        return [tool(approval_required=True, timeout_seconds=_ROLLOUT_WAIT_S + 360, retry_count=0)(fn)
                for fn in ACTIONS]
    raise ValueError(f"ONCALL_ACTIONS must be off, propose or approve — not {mode!r}")
