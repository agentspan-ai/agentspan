"""Match a cluster's symptoms against known, already-fixed Conductor bugs.

The point is that the agent should reach these conclusions WITHOUT a human recognising
the pattern. Both of the multi-hour incidents this month were already fixed upstream
weeks earlier; nobody connected the running version to the merged PR, so each one was
re-diagnosed from scratch.

Two inputs decide it:
  1. the running conductor image tag, and
  2. a symptom fingerprint the agent can already measure (thread frames, repushed
     taskType, sweeper waste).

Version comparison fails CLOSED: branch-style tags like
``fix-archive-feature-async-reconcile-latest`` are real in this fleet and must never be
parsed as a version, or a cluster gets told it is safe when it is not.
"""
from __future__ import annotations

import re

_SEMVER = re.compile(r"^v?(\d+)\.(\d+)\.(\d+)")

# id -> what it is, what fixes it, and what the agent can observe.
KNOWN_ISSUES = [
    {
        "id": "wait-human-resweep-cadence",
        "title": "WAIT/HUMAN-parked workflows re-swept on the flat 30s offset",
        "prs": ["#3754 (HUMAN)", "#3775 (indefinite WAIT + async EVENT)"],
        "fixed_in": (5, 5, 0),
        "mechanism": (
            "ExecutorUtils.computePostpone() computes the real remaining wait, then caps it "
            "with Math.min(postpone, workflowOffsetTimeout=30s) — so it can only ever sweep "
            "MORE often, never defer. Combined with isTaskRepairable treating any non-system "
            "task in SCHEDULED as repairable, every parked workflow is re-swept every 30s and "
            "logs 'Going to repair', forever."
        ),
        # observable without a human
        "taskTypes": {"WAIT", "HUMAN", "EVENT"},
        "min_waste_ratio": 0.5,
    },
    {
        "id": "jdk21-carrier-pin",
        "title": "JDK-21 carrier pin: decider vthread holds the Jedis pool lock forever",
        "prs": ["#3796 (CCOR-13223)"],
        "fixed_in": (5, 5, 0),
        "mechanism": (
            "A decider VIRTUAL thread borrows a Redis connection; inside "
            "GenericObjectPool.create() it enters a synchronized monitor, which on JDK 21 pins "
            "it to its carrier while holding the pool's ReentrantLock. It is never rescheduled, "
            "the lock is never released, and every thread needing Redis queues forever."
        ),
        "thread_names": {"decider-executor-vthread"},
        "frames": {"GenericObjectPool.borrowObject"},
    },
]


def parse_version(image_tag: str | None) -> tuple[int, int, int] | None:
    """(major, minor, patch) from an image tag, or None if it is not a version.

    Returns None for branch tags — the caller must treat None as "unknown", never "safe".
    """
    if not image_tag:
        return None
    tag = image_tag.rsplit(":", 1)[-1].strip()
    m = _SEMVER.match(tag)
    return (int(m.group(1)), int(m.group(2)), int(m.group(3))) if m else None


def match_known_issues(image_tag: str | None, *, repushed_task_types: set[str] | None = None,
                       waste_ratio: float | None = None,
                       thread_names: set[str] | None = None,
                       frames: set[str] | None = None) -> dict:
    """Which known-and-fixed bugs is this cluster both exposed to AND showing?"""
    version = parse_version(image_tag)
    exposed, matched = [], []

    for issue in KNOWN_ISSUES:
        if version is None:
            continue  # fail closed — cannot claim exposure or safety
        if version >= issue["fixed_in"]:
            continue
        exposed.append(issue["id"])

        # symptom match — each issue declares what is observable
        hit = False
        if issue.get("taskTypes") and repushed_task_types:
            if issue["taskTypes"] & {t.upper() for t in repushed_task_types}:
                hit = waste_ratio is None or waste_ratio >= issue.get("min_waste_ratio", 0)
        if issue.get("thread_names") and thread_names:
            hit = hit or any(any(n in t for t in thread_names) for n in issue["thread_names"])
        if issue.get("frames") and frames:
            hit = hit or any(any(f in g for g in frames) for f in issue["frames"])
        if hit:
            matched.append(issue)

    return {
        "image_tag": image_tag,
        "version": ".".join(map(str, version)) if version else None,
        "version_parsed": version is not None,
        "exposed_to": exposed,
        "matched": [{"id": i["id"], "title": i["title"], "prs": i["prs"],
                     "fixed_in": ".".join(map(str, i["fixed_in"])),
                     "mechanism": i["mechanism"]} for i in matched],
        "verdict": _verdict(version, image_tag, exposed, matched),
    }


def _verdict(version, image_tag, exposed: list[str], matched: list[dict]) -> str:
    if version is None:
        return (f"Cannot parse a version from image tag {image_tag!r} (branch-style tags exist "
                "in this fleet). Exposure to known issues is UNKNOWN — verify by hand rather "
                "than assuming the cluster is patched.")
    v = ".".join(map(str, version))
    if matched:
        m = matched[0]
        fixed = ".".join(map(str, m["fixed_in"]))
        return (f"KNOWN ISSUE, already fixed upstream: {m['title']}. Fixed by {', '.join(m['prs'])} "
                f"in {fixed}; this cluster runs {v}. The symptoms match — this is not a "
                "new incident and not a capacity problem. Restarting is a remedy; upgrading is "
                "the fix.")
    if exposed:
        return (f"Cluster runs {v} and is EXPOSED to {len(exposed)} known issue(s) "
                f"({', '.join(exposed)}), but the current symptoms do not match any of them. "
                "Diagnose on the evidence; do not assume it is one of these.")
    return f"Cluster runs {v}, which post-dates all known issues in this table."
