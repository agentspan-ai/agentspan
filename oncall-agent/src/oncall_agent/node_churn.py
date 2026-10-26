"""Did the cluster's nodes change around the alert?

A node-pool upgrade, auto-repair or autoscaler scale-down drains nodes and moves
every pod. Single-replica Grafana and workers have no endpoint while they move, a
rescheduled conductor pod has no IP yet, and the health check reports it as
"Conductor has failed" / "domain is down". Nothing is broken; the pods were moving.

Kubernetes forgets this fast (events live ~1h, restartCount resets when a pod
moves), so the question is answered from what survives: node creationTimestamps
and any node events still retained, both measured against the ALERT time, not now.
"""
from __future__ import annotations

from datetime import datetime, timezone

# A node created this long before the alert, or up to this long after it, belongs
# to the same rollout. GKE replaces one node every few minutes.
_BEFORE_S = 30 * 60
_AFTER_S = 20 * 60

_CHURN_EVENTS = {"NodeNotReady", "NodeNotSchedulable", "RemovingNode", "DeletingNode",
                 "Rebooted", "NodeShutdown", "TerminatingEvictedPod"}


def _ts(value: str) -> datetime | None:
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _rows(text: str) -> list[list[str]]:
    lines = [l for l in (text or "").splitlines() if l.strip()]
    return [l.split(None, 3) for l in lines[1:]]  # skip the custom-columns header


def summarize_node_churn(nodes_text: str, events_text: str, alert_ms: int) -> dict:
    """Classify node churn around the alert.

    Args:
        nodes_text: ``get nodes -o custom-columns=NAME:..,CREATED:..,VERSION:..`` output.
        events_text: ``get events -A --field-selector involvedObject.kind=Node
            -o custom-columns=TIME:..,REASON:..,NODE:..`` output.
        alert_ms: when the alert's health check ran (epoch ms).
    """
    alert = datetime.fromtimestamp(alert_ms / 1000, tz=timezone.utc)
    nodes, fresh = [], []
    for row in _rows(nodes_text):
        if len(row) < 2:
            continue
        created = _ts(row[1])
        if created is None:
            continue
        delta = (created - alert).total_seconds()
        node = {"name": row[0], "created": row[1], "version": row[2] if len(row) > 2 else None,
                "createdMinutesFromAlert": round(delta / 60, 1)}
        nodes.append(node)
        if -_BEFORE_S <= delta <= _AFTER_S:
            fresh.append(node)

    events = []
    for row in _rows(events_text):
        if len(row) < 3 or row[1] not in _CHURN_EVENTS:
            continue
        at = _ts(row[0])
        if at is not None and -_BEFORE_S <= (at - alert).total_seconds() <= _AFTER_S:
            events.append({"time": row[0], "reason": row[1], "node": row[2]})

    if not nodes:
        verdict = "UNKNOWN"
        detail = "node list unavailable; cannot tell whether nodes changed"
    elif fresh and (len(fresh) == len(nodes) or len(fresh) >= 2 or events):
        verdict = "NODE_CHURN"
        detail = (f"{len(fresh)} of {len(nodes)} nodes were created within "
                  f"{_BEFORE_S // 60} min before / {_AFTER_S // 60} min after the alert"
                  + (f", with {len(events)} node drain/removal events" if events else "")
                  + ": a node-pool upgrade, auto-repair or scale-down moved the pods.")
    elif fresh or events:
        verdict = "PARTIAL_CHURN"
        detail = (f"{len(fresh)} node(s) created and {len(events)} node event(s) near the alert; "
                  "one node replaced — pods on it moved.")
    elif any(n["createdMinutesFromAlert"] * 60 > _AFTER_S for n in nodes):
        verdict = "UNKNOWN"
        detail = ("nodes were replaced AFTER the alert, so the nodes present at alert time are gone; "
                  "node churn at the alert can no longer be judged from the cluster.")
    else:
        verdict = "NO_CHURN"
        newest = max(n["createdMinutesFromAlert"] for n in nodes)
        detail = (f"every node predates the alert (newest created {abs(newest):.0f} min before it); "
                  "node movement did not cause this alert.")
    return {"verdict": verdict, "detail": detail, "freshNodes": fresh,
            "nodeEvents": events, "nodeCount": len(nodes)}
