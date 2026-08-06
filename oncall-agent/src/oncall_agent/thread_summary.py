"""Deterministic JVM thread-dump summariser.

Why this exists: `download_thread_dump` uploads the dump to S3 and returns only a
``paths`` entry, so the model never saw a single stack frame. Asked to explain a CPU
alert it therefore reasoned from backlog COUNTS ("N RUNNING workflows, sweeper churn")
— the same story every time, because that is all it could see. This turns a dump into
a small structured fact set the model can actually reason over.

Pure text in, dict out: no network, no LLM, no cluster access. Handles `jstack`/
`jcmd Thread.print` plain format (the only format that carries thread STATE and
`Locked ownable synchronizers`).
"""
from __future__ import annotations

import re
from collections import Counter

_THREAD_START = re.compile(r'^"([^"]+)"')
# `jcmd Thread.dump_to_file -format=plain` uses `#<id> "<name>"` and carries NO
# `Thread.State:` line — but it DOES include virtual threads, which jstack omits. So we
# accept both formats and, when the state is absent, infer it from the top frame: a
# thread parked in Unsafe.park/Object.wait/sleep is not running; anything else is.
_THREAD_START_PLAIN = re.compile(r'^#\d+\s+"([^"]+)"')
_PARKED_TOPS = (
    "java.base/jdk.internal.misc.Unsafe.park",
    "java.base/java.lang.Object.wait",
    "java.base/java.lang.Thread.sleep",
    "java.base/java.lang.VirtualThread.park",
    "java.base/java.lang.ref.Reference.waitForReferencePendingList",
)
_STATE = re.compile(r"java\.lang\.Thread\.State: ([A-Z_]+)")
_FRAME = re.compile(r"^\s+(?:at )?([\w.$/]+\([^)]*\))")
_PARKING_ON = re.compile(r"- parking to wait for\s+<(0x[0-9a-f]+)>")
_WAITING_ON = re.compile(r"- waiting (?:to lock|on)\s+<(0x[0-9a-f]+)>")
_OWNED = re.compile(r"^\s+- <(0x[0-9a-f]+)>")
_LOCKED_SECTION = "Locked ownable synchronizers:"

# Frames that carry no diagnostic signal — never the answer to "what is this thread doing".
_NOISE = (
    "java.base/jdk.internal.misc.Unsafe.park",
    "java.base/java.lang.Thread.sleep",
    "java.base/java.lang.Object.wait",
    "java.base/java.lang.VirtualThread.park",
)

# A RUNNABLE thread sitting in epoll/kqueue or the reference handler is IDLE waiting
# for I/O — the OS parks it and it burns no CPU. Counting these as "running app code"
# is how a wedged JVM gets misread as busy.
_IDLE_RUNNABLE = (
    "sun.nio.ch.EPoll.wait",
    "sun.nio.ch.KQueue.poll",
    "sun.nio.ch.Net.poll",
    "java.lang.ref.Reference.waitForReferencePendingList",
)

# Everything the JDK ships. `sun.` / `com.sun.` are JDK internals too — not our code.
_JDK_PREFIXES = ("java.base/", "java.", "jdk.", "sun.", "com.sun.")


def _first_meaningful_frame(frames: list[str]) -> str | None:
    """The shallowest frame that says something — skip park/wait plumbing."""
    for f in frames:
        if not any(f.startswith(n) for n in _NOISE):
            return f
    return frames[0] if frames else None


def _app_frame(frames: list[str]) -> str | None:
    """The shallowest non-JDK frame — i.e. OUR code or a library, not java.base."""
    for f in frames:
        if not f.startswith(_JDK_PREFIXES):
            return f
    return None


def _is_idle_runnable(frames: list[str]) -> bool:
    """RUNNABLE but parked in the kernel on I/O — consumes no CPU."""
    return bool(frames) and any(frames[0].startswith(p) for p in _IDLE_RUNNABLE)


def summarize_thread_dump(text: str, top: int = 6) -> dict:
    """Structured facts from a plain-format thread dump.

    Returns states, what the RUNNABLE threads are actually executing (the only
    threads that can burn CPU), the biggest lock-wait pileups, and — critically —
    whether a contended lock has NO owner in the dump.
    """
    threads: list[dict] = []
    cur: dict | None = None
    in_locked = False

    for line in text.splitlines():
        m = _THREAD_START.match(line) or _THREAD_START_PLAIN.match(line)
        if m:
            if cur:
                threads.append(cur)
            cur = {"name": m.group(1), "state": None, "frames": [], "waiting_on": None, "owns": []}
            in_locked = False
            continue
        if cur is None:
            continue
        s = _STATE.search(line)
        if s:
            cur["state"] = s.group(1)
            continue
        if _LOCKED_SECTION in line:
            in_locked = True
            continue
        if in_locked:
            o = _OWNED.match(line)
            if o:
                cur["owns"].append(o.group(1))
            continue
        w = _PARKING_ON.search(line) or _WAITING_ON.search(line)
        if w and cur["waiting_on"] is None:
            cur["waiting_on"] = w.group(1)
            continue
        f = _FRAME.match(line)
        if f:
            cur["frames"].append(f.group(1))
    if cur:
        threads.append(cur)

    for t in threads:
        if t["state"] is None:  # plain format — infer from the top frame
            top_frame = t["frames"][0] if t["frames"] else ""
            t["state"] = "WAITING" if top_frame.startswith(_PARKED_TOPS) else "RUNNABLE"

    states = Counter(t["state"] for t in threads if t["state"])

    # RUNNABLE threads are the only ones that can consume CPU. If a CPU alert has
    # few RUNNABLE app threads, the CPU is NOT being burned in the JVM.
    runnable = [t for t in threads if t["state"] == "RUNNABLE"]
    runnable_frames = Counter()
    for t in runnable:
        fr = _first_meaningful_frame(t["frames"])
        if fr:
            runnable_frames[fr] += 1
    runnable_app = [
        t for t in runnable if _app_frame(t["frames"]) and not _is_idle_runnable(t["frames"])
    ]

    # Lock pileups: many threads parked on ONE monitor is a wedge, not load.
    waits = Counter(t["waiting_on"] for t in threads if t["waiting_on"])
    owners: dict[str, list[str]] = {}
    for t in threads:
        for lk in t["owns"]:
            owners.setdefault(lk, []).append(t["name"])

    contention = []
    for lock, n in waits.most_common(3):
        held_by = owners.get(lock, [])
        blocked = [t for t in threads if t["waiting_on"] == lock]
        contention.append({
            "lock": lock,
            "waiters": n,
            "owner": held_by[0] if held_by else None,
            "ownerless": not held_by,
            "waiter_frame": _app_frame(blocked[0]["frames"]) if blocked else None,
        })

    return {
        "total_threads": len(threads),
        "states": dict(states.most_common()),
        "runnable_total": len(runnable),
        "runnable_with_app_frames": len(runnable_app),
        "runnable_top_frames": runnable_frames.most_common(top),
        "lock_contention": contention,
        "verdict": _verdict(len(runnable_app), contention),
    }


def _verdict(runnable_app: int, contention: list[dict]) -> str:
    """One deterministic line the model must not contradict."""
    worst = contention[0] if contention else None
    if worst and worst["waiters"] >= 20 and runnable_app == 0:
        base = (
            f"WEDGE, not load: {worst['waiters']} threads parked on one lock "
            f"({worst['lock']}) and ZERO application threads are RUNNABLE. "
            "CPU is near-zero because parked threads consume none."
        )
        if worst["ownerless"]:
            base += (
                " No thread owns that lock in this dump — jstack does not attribute"
                " locks held by VIRTUAL threads, so the owner is unreportable."
            )
        return base
    if runnable_app == 0:
        return "No application thread is RUNNABLE — the JVM is not burning CPU in app code."
    return (
        f"{runnable_app} application thread(s) RUNNABLE — CPU is being spent in app code; "
        "attribute it to the top RUNNABLE frames above, not to a backlog count."
    )
