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
