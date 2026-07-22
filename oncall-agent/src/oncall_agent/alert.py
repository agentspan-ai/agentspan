"""Parse a Slack health-check alert into the bits the agent needs.

Only the execution id is required — everything authoritative (org, cluster,
cloudEnvironmentTag) is read from the failing execution itself. The severity /
cluster / org parsed here are best-effort, for logging and the agent prompt.

Example alert::

    [CRITICAL] The health-checking has FAILED for the Vizient's prod viz-stage
    cluster with the following issue:
    CRITICAL: The Redis instance is at 66%, above the CRITICAL threshold of 65%
    https://ah5r-prod.orkesconductor.com/execution/364b459a-689f-11f1-94b6-de01f12a4ed9
"""
from __future__ import annotations

import re
from dataclasses import dataclass

_EXEC_RE = re.compile(r"/execution/([0-9a-fA-F][0-9a-fA-F\-]{7,})")
_SEV_RE = re.compile(r"\[(CRITICAL|MAJOR|MINOR|WARNING)\]", re.IGNORECASE)
# The worker emits Slack markdown — bold `*`, code `` ` ``, italic `_org_` — around the
# org and cluster (e.g. "for the _Vizient's_ prod *`viz-stage`* cluster"). `*`/`` ` `` are
# stripped before matching; the `_?` here absorbs the italic underscores that wrap the org,
# and the cluster is captured without underscores so the trailing italic marker is excluded.
_CLUSTER_RE = re.compile(
    r"for the\s+_?(?P<org>.+?)'s_?\s+\S+\s+_?(?P<cluster>[^\s_]+)_?\s+cluster",
    re.IGNORECASE,
)
# Slack decoration that never appears inside an org/cluster name — drop it before matching.
_DECORATION = str.maketrans("", "", "*`")


_URL_RE = re.compile(r"<[^>]*>|https?://\S+")
_NUMBERISH = re.compile(r"[\d.]+%?")


def alert_signature(text: str | None) -> str:
    """A stable identity for the INCIDENT behind an alert message.

    The raw channel fires the same incident every ~5 minutes with a fresh
    execution id and slightly different numbers (seconds, percentages). The
    signature is the sorted set of word tokens with URLs stripped and
    number-ish / hex-ish tokens (uuid fragments, pod hashes) dropped — equal
    across firings of one incident, different across clusters and alert types.
    """
    cleaned = _URL_RE.sub(" ", text or "")
    words = re.split(r"[^a-z0-9.]+", cleaned.lower())
    tokens = sorted(
        {
            w
            for w in words
            if w
            and not _NUMBERISH.fullmatch(w)
            # Mixed digit+letter tokens are identifiers by nature — uuid/hex
            # fragments, ReplicaSet hashes, and k8s pod suffixes (…-65pkn vs
            # …-pv6m5 split one incident into two signatures, seen live).
            and not (any(c.isdigit() for c in w) and any(c.isalpha() for c in w))
        }
    )
    return ",".join(tokens)


def message_text(msg: dict) -> str:
    """Flatten a Slack message to plain text: top-level ``text`` plus every
    mrkdwn text inside its blocks.

    The alert-aggregator digest channel puts only a headline in ``text``; the
    original alert (execution URL included) is quoted inside a section block,
    and the occurrence counter lives in a context block. Both must reach the
    parser and the triage prompt.
    """
    parts = [msg.get("text") or ""]
    for block in msg.get("blocks") or []:
        text = (block.get("text") or {}).get("text")
        if text:
            parts.append(text)
        for el in block.get("elements") or []:
            el_text = el.get("text")
            if isinstance(el_text, str) and el_text:
                parts.append(el_text)
    return "\n".join(p for p in parts if p)


@dataclass
class Alert:
    execution_id: str
    severity: str | None
    cluster: str | None
    organization: str | None
    raw: str


def parse_alert(text: str | None) -> Alert | None:
    """Return an :class:`Alert` if the text looks like a health-check alert with an
    execution link, else ``None``."""
    if not text:
        return None
    m = _EXEC_RE.search(text)
    if not m:
        return None
    # Strip bold/code markers so the severity + cluster matchers see plain text; keep the
    # raw text intact on the Alert for logging.
    clean = text.translate(_DECORATION)
    sev = _SEV_RE.search(clean)
    cm = _CLUSTER_RE.search(clean)
    return Alert(
        execution_id=m.group(1),
        severity=sev.group(1).upper() if sev else None,
        cluster=cm.group("cluster") if cm else None,
        organization=cm.group("org") if cm else None,
        raw=text,
    )
