"""Deterministic tests for the thread-dump summariser — no cluster, no LLM.

Context: every CPU alert used to come back as "large RUNNING backlog / sweeper churn"
because the agent could not see a single stack frame (download_thread_dump returns an
S3 path only) and the playbook told it to grep logs for sweeper churn. These tests pin
the facts the summariser must extract so a CPU diagnosis can be grounded in what the
threads are actually doing.
"""
from oncall_agent.thread_summary import summarize_thread_dump


def _thread(name, state, frames, parking=None, owns=None):
    out = [f'"{name}" #1 daemon prio=5 tid=0x1 nid=1 waiting on condition',
           f"   java.lang.Thread.State: {state}"]
    if parking:
        out.append(f"\t- parking to wait for  <{parking}> (a java.util.concurrent.locks.ReentrantLock$FairSync)")
    out += [f"\tat {f}" for f in frames]
    out.append("")
    out.append("   Locked ownable synchronizers:")
    out += [f"\t- <{o}> (a java.util.concurrent.locks.ReentrantLock$NonfairSync)" for o in (owns or [])] \
        or ["\t- None"]
    out.append("")
    return "\n".join(out)


POOL = "0x00000006ca7c0c30"
WEDGE_FRAMES = [
    "java.base/jdk.internal.misc.Unsafe.park(Native Method)",
    "java.base/java.util.concurrent.locks.ReentrantLock.lock(ReentrantLock.java:322)",
    "org.apache.commons.pool2.impl.LinkedBlockingDeque.pollFirst(LinkedBlockingDeque.java:892)",
    "org.apache.commons.pool2.impl.GenericObjectPool.borrowObject(GenericObjectPool.java:297)",
    "redis.clients.jedis.ConnectionPool.getResource(ConnectionPool.java:52)",
]


def _wedged_dump(n=40):
    parts = [_thread(f"http-nio-8080-exec-{i}", "WAITING", WEDGE_FRAMES, parking=POOL)
             for i in range(n)]
    # the idle plumbing a real dump always carries
    parts.append(_thread("http-nio-8080-Poller", "RUNNABLE", ["sun.nio.ch.EPoll.wait(Native Method)"]))
    parts.append(_thread("Reference Handler", "RUNNABLE",
                         ["java.lang.ref.Reference.waitForReferencePendingList(Native Method)"]))
    return "\n".join(parts)


def test_wedge_is_reported_as_wedge_not_load():
    s = summarize_thread_dump(_wedged_dump())
    assert s["runnable_with_app_frames"] == 0
    assert "WEDGE, not load" in s["verdict"]
    assert "parked threads consume none" in s["verdict"]


def test_idle_epoll_runnable_is_not_counted_as_app_work():
    """sun.nio.ch.EPoll.wait is RUNNABLE but parked in the kernel — zero CPU.

    Counting it as app work flipped the verdict to 'CPU is being spent in app code'
    on a dump where the JVM was doing nothing at all.
    """
    s = summarize_thread_dump(_wedged_dump())
    assert s["runnable_total"] >= 2, "fixture should contain idle RUNNABLE threads"
    assert s["runnable_with_app_frames"] == 0, "epoll/reference-handler must not count as app work"


def test_lock_pileup_and_ownerless_detection():
    s = summarize_thread_dump(_wedged_dump())
    top = s["lock_contention"][0]
    assert top["lock"] == POOL
    assert top["waiters"] == 40
    assert top["ownerless"] is True
    assert "LinkedBlockingDeque" in top["waiter_frame"]
    assert "virtual" in s["verdict"].lower(), "must explain why no owner is listed"


def test_owner_is_named_when_a_platform_thread_holds_it():
    dump = _wedged_dump(5) + "\n" + _thread(
        "worker-7", "RUNNABLE",
        ["io.orkes.conductor.Foo.bar(Foo.java:1)"], owns=[POOL])
    s = summarize_thread_dump(dump)
    top = s["lock_contention"][0]
    assert top["ownerless"] is False
    assert top["owner"] == "worker-7"


def test_genuine_cpu_burn_attributes_to_the_hot_frame():
    """The other half: when app threads really ARE running, say so and name the frame."""
    dump = "\n".join(
        _thread(f"sweeper-thread-{i}", "RUNNABLE",
                ["io.orkes.conductor.server.service.sweeper.OrkesWorkflowSweeper.sweep(OrkesWorkflowSweeper.java:88)"])
        for i in range(4))
    s = summarize_thread_dump(dump)
    assert s["runnable_with_app_frames"] == 4
    assert "RUNNABLE" in s["verdict"] and "app code" in s["verdict"]
    assert "not to a backlog count" in s["verdict"]
    top_frame, count = s["runnable_top_frames"][0]
    assert "OrkesWorkflowSweeper" in top_frame and count == 4


# ── jcmd Thread.dump_to_file -format=plain ───────────────────────────────
# Different shape: `#id "name"`, frames with no `at ` prefix, and NO
# `Thread.State:` line at all — state must be inferred from the top frame.
# It is the only format that includes VIRTUAL threads, so it is what
# get_thread_summary captures.

PLAIN = '''14
2026-08-06T15:29:30Z
21.0.10+7-LTS

#9 "Reference Handler"
      java.base/java.lang.ref.Reference.waitForReferencePendingList(Native Method)

#77 "http-nio-8080-exec-7"
      java.base/jdk.internal.misc.Unsafe.park(Native Method)
      java.base/java.util.concurrent.locks.ReentrantLock.lock(ReentrantLock.java:322)
      org.apache.commons.pool2.impl.LinkedBlockingDeque.pollFirst(LinkedBlockingDeque.java:892)

#88 "sweeper-thread-1"
      io.orkes.conductor.server.service.sweeper.OrkesWorkflowSweeper.sweep(OrkesWorkflowSweeper.java:88)
'''


def test_plain_format_is_parsed_and_state_inferred():
    s = summarize_thread_dump(PLAIN)
    assert s["total_threads"] == 3, "must parse the `#id \"name\"` header form"
    # parked-in-Unsafe.park -> WAITING; real app frame on top -> RUNNABLE
    assert s["states"].get("RUNNABLE") == 1
    assert s["states"].get("WAITING") == 2
    assert s["runnable_with_app_frames"] == 1
    top_frame, _ = s["runnable_top_frames"][0]
    assert "OrkesWorkflowSweeper" in top_frame
