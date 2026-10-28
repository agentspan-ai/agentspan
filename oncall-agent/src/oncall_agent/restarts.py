"""Why does a pod restart: memory, a crash, or the kubelet?

A container's last termination says it plainly: ``OOMKilled`` (exit 137) is the memory
limit; ``Error`` with exit 137 is a kill from outside — the kubelet's liveness probe;
``Error`` with another exit code is the process dying on its own (read its previous
logs). The restart count alone says none of this, and it resets when a pod moves.
"""
from __future__ import annotations


def _meaning(reason: str | None, code: int | None) -> str:
    if reason == "OOMKilled":
        return ("OOMKilled: the container hit its MEMORY LIMIT. For a JVM the heap (-Xmx) plus off-heap "
                "(metaspace, threads, direct buffers) exceeded the limit — lower -Xmx or raise the limit.")
    if code == 137:
        return "killed from outside (SIGKILL) without OOM: almost always a failed liveness probe."
    if code == 143:
        return "SIGTERM: stopped on purpose (rollout, eviction, node drain)."
    if reason:
        return f"the process exited by itself ({reason}, exit {code}): read the previous container's logs."
    return "no previous termination recorded."


COLUMNS = ("custom-columns=POD:.metadata.name,STARTED:.status.startTime,"
           "C:.status.containerStatuses[*].name,R:.status.containerStatuses[*].restartCount,"
           "READY:.status.containerStatuses[*].ready,"
           "REASON:.status.containerStatuses[*].lastState.terminated.reason,"
           "EXIT:.status.containerStatuses[*].lastState.terminated.exitCode,"
           "FINISHED:.status.containerStatuses[*].lastState.terminated.finishedAt")


def summarize_restarts(pods_text: str) -> dict:
    """Per container: restarts, last termination reason/exit/time and what it means.

    ``pods_text`` is ``get pods -o <COLUMNS>`` output; multi-container pods list their
    containers comma-separated in each column (a container that never terminated is
    simply absent from REASON/EXIT/FINISHED, so those are matched only for single
    containers or when the counts line up).
    """
    rows = [l.split() for l in (pods_text or "").splitlines()[1:] if l.strip()]
    out = []
    for row in rows:
        if len(row) < 5:
            continue
        pod, started, names, counts, ready = row[:5]
        rest = [c.split(",") if c != "<none>" else [] for c in (row[5:8] + ["<none>"] * 3)[:3]]
        names, counts, ready = names.split(","), counts.split(","), ready.split(",")
        for i, name in enumerate(names):
            n = int(counts[i]) if i < len(counts) and counts[i].isdigit() else 0
            aligned = len(names) == 1 or len(rest[0]) == len(names)
            reason = rest[0][i] if aligned and i < len(rest[0]) else None
            code = rest[1][i] if aligned and i < len(rest[1]) else None
            code = int(code) if code and code.lstrip("-").isdigit() else None
            if not n and not reason:
                continue
            out.append({"pod": pod, "container": name, "restarts": n,
                        "ready": ready[i] == "true" if i < len(ready) else None, "podStarted": started,
                        "lastReason": reason, "lastExitCode": code,
                        "lastFinishedAt": rest[2][i] if aligned and i < len(rest[2]) else None,
                        "meaning": _meaning(reason, code)})
    out.sort(key=lambda x: -x["restarts"])
    return {"restartingContainers": out[:12],
            "note": "restart counts reset when a pod is rescheduled; restartTimeline has the history"}
