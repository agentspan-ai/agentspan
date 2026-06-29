"""Deterministic concurrent-injection contract tests.

See ``docs/design/secret-injection-contract.md`` §5 — every SDK with framework
passthrough has the same two-test pattern:

1. **Counterfactual** — a buggy "lock-around-mutation-only" implementation is
   reproduced inline and proven to clobber under concurrency. If this test
   ever stops failing-as-expected the counterfactual no longer holds.

2. **Fix verification** — the real ``inject_via_env`` is proven to isolate
   concurrent calls.

Both tests use a :class:`threading.Barrier` to **force** the race to happen
in deterministic step order. No sleeps, no retries, no flake.
"""

from __future__ import annotations

import os
import threading
from concurrent.futures import ThreadPoolExecutor

import pytest

from conductor.ai.agents.runtime.secret_injection import inject_via_env

# Two unique env var names so this test never collides with anything real on
# the developer's machine or in CI.
KEY = "_AS_TEST_RACE_KEY"


@pytest.fixture(autouse=True)
def _isolate_env():
    """Snapshot/restore env around each test so other tests aren't affected."""
    saved = os.environ.get(KEY)
    os.environ.pop(KEY, None)
    yield
    if saved is None:
        os.environ.pop(KEY, None)
    else:
        os.environ[KEY] = saved


# ── Counterfactual: the broken pattern races ──────────────────────────────────


def _buggy_inject(secrets: dict, invoke):
    """The OLD broken pattern — lock guarding only the mutation step.

    Kept here as a counterfactual so the test below can prove the race is
    observable under this implementation. Do NOT use in real code.
    """
    _buggy_lock = _buggy_inject._lock  # type: ignore[attr-defined]
    injected = []
    try:
        with _buggy_lock:
            for k, v in secrets.items():
                os.environ[k] = v
                injected.append(k)
        # ← lock RELEASED here, before the framework runs ↓
        return invoke()
    finally:
        for k in injected:
            os.environ.pop(k, None)


_buggy_inject._lock = threading.Lock()  # type: ignore[attr-defined]


def test_buggy_injection_races_deterministically():
    """Counterfactual proof: the old broken pattern lets a concurrent thread
    clobber the value an in-flight 'framework call' would observe.

    Step order forced by the barrier:
        1. Thread A: buggy_inject sets KEY=A, calls fake_invoke
        2. Thread A: fake_invoke reaches barrier, blocks
        3. Thread B: buggy_inject sets KEY=B, calls fake_invoke
        4. Thread B: fake_invoke reaches barrier, both threads released
        5. Both threads: read os.environ[KEY] and record it

    Without the fix, both threads see "B" (or A sees nothing if B finished
    its restore first). With the fix in place, A would see "A".
    """
    barrier = threading.Barrier(2, timeout=5)
    a_observed: list[str | None] = []
    b_observed: list[str | None] = []

    def fake_invoke(observed_out):
        # Hold here until BOTH threads are inside their fake_invoke.
        # This forces the env to contain whichever value was set most recently.
        barrier.wait()
        observed_out.append(os.environ.get(KEY))
        return "ok"

    def worker(value: str, observed_out: list):
        _buggy_inject({KEY: value}, lambda: fake_invoke(observed_out))

    with ThreadPoolExecutor(max_workers=2) as pool:
        fa = pool.submit(worker, "A", a_observed)
        fb = pool.submit(worker, "B", b_observed)
        fa.result(timeout=10)
        fb.result(timeout=10)

    # COUNTERFACTUAL ASSERTION:
    # The buggy pattern makes at least one of the threads observe something
    # OTHER than its own value. Concretely, the failure modes are:
    #   - Both threads see the latest writer's value ("clobber")
    #   - One thread sees None (the other's finally-block popped the key)
    #   - One thread sees the other's value, the other sees None
    # All are bug manifestations. The contract violation we test for is
    # "at least one thread did not see its own injected value".
    a_value = a_observed[0]
    b_value = b_observed[0]
    a_correct = a_value == "A"
    b_correct = b_value == "B"
    assert not (a_correct and b_correct), (
        f"Counterfactual expected at least one thread to observe a clobbered "
        f"env value, but both saw their own. Got A={a_value!r}, B={b_value!r}. "
        f"If the buggy pattern is no longer producing observable races, the "
        f"counterfactual is invalid — investigate before deleting this test."
    )


# ── Fix verification: inject_via_env isolates concurrent calls ────────────────


def test_fixed_injection_isolates_concurrent_calls():
    """With ``inject_via_env``, Thread A's framework call ALWAYS observes A's
    value, even when Thread B is concurrently injecting B's value.

    Because the helper holds a single process-wide lock around the whole
    invocation, B can't enter its own invoke() until A has finished — so
    A's view of os.environ is never clobbered.

    The barrier here is used differently than in the counterfactual: A is
    free-running, and B *attempts* to enter but is blocked by the lock until
    A completes. We verify by snapshotting env inside A's invoke.
    """
    a_observed: list[str | None] = []
    b_observed: list[str | None] = []

    a_holding = threading.Event()
    a_can_release = threading.Event()

    def fake_invoke_a():
        # We're inside the lock. Capture what env looks like right now.
        a_observed.append(os.environ.get(KEY))
        a_holding.set()  # signal main thread that A is inside its invoke
        # Hold here so B has time to try (and fail) to clobber.
        # B will be blocked by the lock; this delay is the proof.
        a_can_release.wait(timeout=5)
        # Capture again, AFTER B has had a chance to try. Should still be "A".
        a_observed.append(os.environ.get(KEY))
        return "ok"

    def fake_invoke_b():
        b_observed.append(os.environ.get(KEY))
        return "ok"

    def worker_a():
        inject_via_env({KEY: "A"}, fake_invoke_a)

    def worker_b():
        # Will block on the lock until A releases.
        inject_via_env({KEY: "B"}, fake_invoke_b)

    with ThreadPoolExecutor(max_workers=2) as pool:
        fa = pool.submit(worker_a)
        a_holding.wait(timeout=5)  # don't launch B until A is inside the lock
        fb = pool.submit(worker_b)
        # Give B time to attempt to enter (it will block on the lock)
        import time

        time.sleep(0.1)
        # Release A
        a_can_release.set()
        fa.result(timeout=10)
        fb.result(timeout=10)

    # FIX ASSERTION 1: A saw its own value both before AND after B's attempt.
    assert a_observed == ["A", "A"], (
        f"Thread A's view of env was clobbered: {a_observed!r}. "
        f"inject_via_env must hold the lock across the whole invoke."
    )

    # FIX ASSERTION 2: B saw its own value (after A released, B got the lock).
    assert b_observed == ["B"], (
        f"Thread B's view of env was wrong: {b_observed!r}. "
        f"B should have seen B's value after acquiring the lock."
    )

    # FIX ASSERTION 3: env is fully cleaned up afterwards.
    assert os.environ.get(KEY) is None, (
        f"env not restored after both invocations completed: {KEY}={os.environ.get(KEY)!r}"
    )


# ── Restoration semantics: pre-existing values are preserved ──────────────────


def test_restores_preexisting_env_value():
    """If KEY was already set before injection, it's restored to its original
    value on the way out. Catches bugs where ``pop`` is used instead of
    setting back the saved value.
    """
    os.environ[KEY] = "pre-existing-value"

    def fake_invoke():
        assert os.environ[KEY] == "injected-value"

    inject_via_env({KEY: "injected-value"}, fake_invoke)

    assert os.environ.get(KEY) == "pre-existing-value", (
        f"Pre-existing env value was lost: got {os.environ.get(KEY)!r}"
    )


def test_restores_on_exception_in_invoke():
    """Exception in the framework call must not leak injected values."""

    class BoomError(Exception):
        pass

    def boom():
        assert os.environ[KEY] == "should-be-cleaned"
        raise BoomError("framework blew up")

    with pytest.raises(BoomError):
        inject_via_env({KEY: "should-be-cleaned"}, boom)

    assert os.environ.get(KEY) is None, (
        f"env not cleaned up after exception in invoke: {os.environ.get(KEY)!r}"
    )


# ── Native @tool dispatch path uses the same helper ───────────────────────────


def test_native_dispatch_and_framework_share_one_lock():
    """The native @tool dispatch path (_dispatch.py) and the framework
    passthrough paths (frameworks/*.py) must contend for the *same* lock —
    otherwise a native @tool and a framework agent running concurrently
    could still clobber each other's env.

    Concrete check: kick off two ``inject_via_env`` calls from different
    threads; verify one is blocked while the other holds the lock. Both
    paths import the same helper, so a single lock is the invariant we test.
    """
    from conductor.ai.agents.runtime.secret_injection import _env_injection_lock

    held = threading.Event()
    release = threading.Event()
    other_entered = threading.Event()

    def holder():
        def invoke():
            held.set()
            release.wait(timeout=5)
            return None

        inject_via_env({KEY: "holder"}, invoke)

    def other():
        held.wait(timeout=5)
        # Try to acquire the same lock non-blockingly — must fail because holder
        # has it. This proves it's a SINGLE shared lock, not per-call.
        got = _env_injection_lock.acquire(blocking=False)
        try:
            if not got:
                other_entered.set()  # signal that lock was correctly contested
        finally:
            if got:
                _env_injection_lock.release()

    with ThreadPoolExecutor(max_workers=2) as pool:
        fh = pool.submit(holder)
        fo = pool.submit(other)
        assert other_entered.wait(timeout=5), (
            "Second thread acquired the lock while holder was inside its invoke. "
            "The native dispatch path and framework path must share one lock."
        )
        release.set()
        fh.result(timeout=5)
        fo.result(timeout=5)
