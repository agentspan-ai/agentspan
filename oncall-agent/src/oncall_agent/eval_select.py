"""Pick a scorable set of unique incidents from raw alerting health_check runs.

The alert stream is dominated by flappers — the same (cluster, alert-type)
firing every 5 minutes. Scoring 30 copies of one flapper tells us nothing, so
the eval batch dedupes to unique incidents first: an incident key is the
cluster plus the number-stripped token set of the alert text (the same
normalization that recurrence matching uses — percentages and counts vary per
firing, the words don't). Newest firing per incident wins, newest incidents
first, capped at ``limit``.

Only real health-check alerts qualify: a run whose reason doesn't carry the
"health-checking has FAILED" text (e.g. task poll timeouts) is monitoring
noise, not a triageable incident.
"""
from __future__ import annotations

from .recurrence import _tokens

_ALERT_MARKER = "health-checking has failed"


def _incident_key(reason: str) -> frozenset[str]:
    return frozenset(_tokens(reason))


def select_eval_incidents(rows: list[dict], limit: int) -> list[dict]:
    """Dedupe alerting runs to unique incidents, newest first, capped at limit.

    Args:
        rows: health_check run dicts with ``workflow_id``, ``reason`` and
            ``start_time`` (ISO-8601 string or epoch ms). Any order.
        limit: maximum incidents to return.
    """
    alerting = [
        r for r in rows if _ALERT_MARKER in str(r.get("reason") or "").lower()
    ]
    alerting.sort(key=lambda r: str(r.get("start_time") or ""), reverse=True)

    seen: set[frozenset[str]] = set()
    picked: list[dict] = []
    for r in alerting:
        key = _incident_key(str(r["reason"]))
        if key in seen:
            continue
        seen.add(key)
        picked.append(r)
        if len(picked) >= limit:
            break
    return picked
