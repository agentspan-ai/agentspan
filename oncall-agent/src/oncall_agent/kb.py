"""The incident knowledge base: confirmed past incidents, looked up at the start of a triage.

Each incident (one JSON line in ``<store>/incidents.jsonl``, private — never in this public
repo) records the clusters, customer, symptoms, cause, fix and the evidence that proved it.
It grows without code: on-call replies "cause: ..." in an alert thread and
``scripts/harvest_cases.py`` appends the incident; people can also add lines by hand.

The lookup ranks past incidents for a new alert — same cluster first, then same customer,
then shared symptoms in the alert text — and returns a few as LEADS. The agent must verify a
lead against current evidence before citing it; a match is a hypothesis, never the answer.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

STORE = Path(os.environ.get("ONCALL_STORE", os.path.expanduser("~/.oncall-agent")))


def load(path: Path | None = None) -> list[dict]:
    path = path or STORE / "incidents.jsonl"
    if not path.exists():
        return []
    out = []
    for line in path.read_text().splitlines():
        try:
            out.append(json.loads(line))
        except ValueError:
            continue
    return out


def similar(cluster: str | None, customer: str | None, alert_text: str, incidents: list[dict],
            top: int = 3) -> list[dict]:
    """Past incidents worth checking for this alert, best first (empty when nothing is close)."""
    text = (alert_text or "").lower()
    ranked = []
    for inc in incidents:
        hits = [s for s in inc.get("symptoms", []) if s.lower() in text]
        same_cluster = bool(cluster) and cluster in inc.get("clusters", [])
        same_customer = bool(customer) and (inc.get("customer") or "").lower() in customer.lower() \
            and inc.get("customer") not in ("various", None, "")
        score = 5 * same_cluster + 2 * same_customer + len(hits)
        # A lead needs a symptom in common, or the very same cluster.
        if not hits and not same_cluster:
            continue
        ranked.append((score, inc, hits, same_cluster, same_customer))
    ranked.sort(key=lambda r: -r[0])
    return [{"id": inc["id"], "date": inc.get("date"), "clusters": inc.get("clusters"),
             "why": ", ".join(filter(None, ["same cluster" if sc else "", "same customer" if cu else "",
                                            f"shared symptoms: {hits}" if hits else ""])),
             "cause": inc.get("cause"), "fix": inc.get("fix"), "provedBy": inc.get("evidence")}
            for score, inc, hits, sc, cu in ranked[:top]]


def leads_for_alert(alert_text: str, cluster: str | None = None, exclude_execution: str | None = None,
                    incidents: list[dict] | None = None) -> str:
    """Prompt section with the similar past incidents for an alert ('' when none).

    ``exclude_execution`` hides the incident recorded FROM that very alert (eval leave-one-out:
    a case must not be answered by reading its own write-up)."""
    incidents = load() if incidents is None else incidents
    if exclude_execution:
        incidents = [i for i in incidents if exclude_execution not in (i.get("alert_executions") or [])]
    text = (alert_text or "").lower()
    if not cluster:
        names = {c for i in incidents for c in i.get("clusters", []) if c != "*"}
        cluster = next((c for c in sorted(names, key=len, reverse=True) if c.lower() in text), None)
    leads = similar(cluster, None, text, incidents)
    if not leads:
        return ""
    lines = [f"- {l['id']} ({l['date'] or 'date unknown'}; {l['why']}): {l['cause']} Fix: {l['fix']} "
             f"Proved by: {l['provedBy']}" for l in leads]
    return ("\nPAST INCIDENTS that look similar (LEADS — verify against this incident's evidence before "
            "citing; ignore any that do not match):\n" + "\n".join(lines) + "\n")
