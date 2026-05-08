# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""E2E worker liveness tests.

Validates the two complementary checks added by the worker-liveness fix:
- LocalLivenessCheck (Mode B-1): fail fast in start() when worker subprocess
  isn't actually running.
- ServerLivenessMonitor (Mode B-2): fail in join() when a queued task in our
  domain has no polls past the stall threshold.
- AgentHandle.is_resumed (Mode A): observable when an idempotency_key replays
  an existing execution.

All assertions are algorithmic (no LLM-as-judge). Real Conductor server
required.
"""

from __future__ import annotations

import time
import uuid

import pytest

from agentspan.agents import (
    Agent,
    AgentRuntime,
    WorkerStallError,
    WorkerStartupError,
    tool,
)
from agentspan.agents.runtime.config import AgentConfig

pytestmark = pytest.mark.integration


@tool
def liveness_probe(payload: str) -> str:
    """A trivial tool used only to register a worker."""
    return f"ok:{payload}"


@tool
def slow_setup(payload: str) -> str:
    """A trivial tool whose body never runs in the stall test — the server
    schedules it via prefill_tools, but no worker polls because subprocess
    spawn was suppressed."""
    return f"setup:{payload}"


class _FakeTaskHandler:
    """Minimal stub for a Conductor TaskHandler.

    Replaces the real handler so that ``LocalLivenessCheck.verify`` can
    execute its loop without spawning any subprocess (avoiding the macOS
    fork() deadlock that occurs when multiprocessing is used from a
    multi-threaded parent).

    ``workers`` and ``task_runner_processes`` are intentionally empty so
    the liveness check always finds ``missing == expected_set`` and raises
    ``WorkerStartupError`` after the timeout.
    """

    def __init__(self) -> None:
        self.workers: list = []
        self.task_runner_processes: list = []

    def stop_processes(self) -> None:
        """Called by WorkerManager.stop() — no-op for the stub."""

    def start_processes(self) -> None:
        """Called by start() path — no-op for the stub."""


@pytest.fixture
def fast_liveness_config():
    """AgentConfig with aggressive liveness windows so tests stay fast."""
    cfg = AgentConfig.from_env()
    cfg.liveness_enabled = True
    cfg.liveness_startup_timeout_seconds = 1.0
    cfg.liveness_stall_seconds = 5.0
    cfg.liveness_check_interval_seconds = 1.0
    return cfg


def test_local_liveness_raises_when_workers_not_started(fast_liveness_config):
    """When WorkerManager.start is short-circuited so no subprocess is alive,
    runtime.start() must raise WorkerStartupError within startup_timeout.

    Mechanism: ``start()`` is replaced by a stub that:
      1. Installs a fake ``_task_handler`` (non-None so the liveness check
         does not bypass itself via the ``task_handler is None`` guard).
      2. Leaves ``workers`` and ``task_runner_processes`` empty so
         ``LocalLivenessCheck.verify`` always sees ``missing == expected_set``
         and raises ``WorkerStartupError`` after 1 second.

    No real subprocesses are spawned, so macOS fork() deadlocks cannot occur.
    """
    agent = Agent(
        name=f"liveness-test-{uuid.uuid4().hex[:8]}",
        model="openai/gpt-4o-mini",
        stateful=True,
        tools=[liveness_probe],
        max_turns=1,
    )

    with AgentRuntime(config=fast_liveness_config) as rt:
        original_start = rt._worker_manager.start

        def _fake_start() -> None:
            """Install a fake _task_handler without spawning any subprocess."""
            if rt._worker_manager._task_handler is None:
                rt._worker_manager._task_handler = _FakeTaskHandler()

        rt._worker_manager.start = _fake_start  # type: ignore[assignment]

        t0 = time.monotonic()
        with pytest.raises(WorkerStartupError) as exc_info:
            rt.start(agent, "hello")
        elapsed = time.monotonic() - t0

        # Restore so the runtime can shut down cleanly
        rt._worker_manager.start = original_start  # type: ignore[assignment]

    # NOTE: A clean-server run completes in ~1s (LocalLivenessCheck timeout
    # is 1s). On a backlogged shared Conductor instance, ``rt.start``'s HTTP
    # roundtrip alone can take ~30s. The hard upper bound here is generous
    # to absorb that — what we actually verify is the typed error and the
    # ``missing`` payload below.
    assert elapsed < 60.0, f"Liveness check took too long: {elapsed:.2f}s"
    err = exc_info.value
    assert any(name == "liveness_probe" for name, _ in err.missing)
    assert err.domain is not None  # stateful agent gets a domain


def test_local_liveness_disabled_does_not_raise(fast_liveness_config):
    """Validity counter-test: with liveness_enabled=False, the same scenario
    must NOT raise WorkerStartupError — proving the check is what's signaling.
    """
    fast_liveness_config.liveness_enabled = False

    agent = Agent(
        name=f"liveness-test-disabled-{uuid.uuid4().hex[:8]}",
        model="openai/gpt-4o-mini",
        stateful=True,
        tools=[liveness_probe],
        max_turns=1,
    )

    with AgentRuntime(config=fast_liveness_config) as rt:
        original_start = rt._worker_manager.start

        def _fake_start() -> None:
            if rt._worker_manager._task_handler is None:
                rt._worker_manager._task_handler = _FakeTaskHandler()

        rt._worker_manager.start = _fake_start  # type: ignore[assignment]

        # Should NOT raise. start() returns; we cancel before the LLM does
        # anything to keep the test fast.
        try:
            handle = rt.start(agent, "hello")
            handle.cancel("test cleanup")
        except WorkerStartupError:
            pytest.fail("liveness_enabled=False should disable WorkerStartupError")
        finally:
            rt._worker_manager.start = original_start  # type: ignore[assignment]


# ── Server-side stall detection (Mode B-2) ──────────────────────────────


def _start_with_no_workers(rt, agent, message):
    """Start a workflow on the real Conductor server while suppressing
    Python-side worker spawn.

    Returns the AgentHandle. The workflow is created server-side and
    ``prefill_tools`` are scheduled in our domain, but no worker polls
    because ``WorkerManager.start`` is replaced with a stub that installs
    ``_FakeTaskHandler``. ``liveness_enabled`` must be False on the runtime
    config for the duration of ``rt.start`` so ``LocalLivenessCheck`` does
    not abort start; the caller is responsible for re-enabling it before
    ``handle.join()``.
    """
    original_start = rt._worker_manager.start

    def _fake_start() -> None:
        if rt._worker_manager._task_handler is None:
            rt._worker_manager._task_handler = _FakeTaskHandler()

    rt._worker_manager.start = _fake_start  # type: ignore[assignment]
    try:
        return rt.start(agent, message)
    finally:
        rt._worker_manager.start = original_start  # type: ignore[assignment]


def test_server_liveness_detects_stall_during_join(fast_liveness_config):
    """When a SCHEDULED task in our domain has pollCount=0 past the stall
    threshold, ServerLivenessMonitor must surface ``WorkerStallError``
    via ``handle.join()`` — within the configured stall window plus a
    few ticks of margin.

    Mechanism:
      1. ``WorkerManager.start`` is stubbed (no subprocess spawn). The
         workflow is created on the live Conductor server and
         ``prefill_tools`` schedules ``slow_setup`` in the agent's domain.
      2. ``liveness_enabled=False`` during ``rt.start`` so the local check
         doesn't pre-empt the test. We re-enable it before ``join()`` so
         the server monitor spawns.
      3. ``liveness_stall_policy="raise"`` and ``max_restarts=0`` ensure
         the monitor's stall callback stores the typed error rather than
         attempting a worker restart.
    """
    cfg = fast_liveness_config
    cfg.liveness_stall_seconds = 3.0
    cfg.liveness_check_interval_seconds = 1.0
    cfg.liveness_stall_policy = "raise"
    cfg.liveness_stall_max_restarts = 0
    cfg.liveness_enabled = False  # disabled during start; re-enabled before join

    agent = Agent(
        name=f"stall-test-{uuid.uuid4().hex[:8]}",
        model="openai/gpt-4o-mini",
        stateful=True,
        tools=[slow_setup],
        prefill_tools=[slow_setup.call(payload="probe")],
        max_turns=1,
    )

    with AgentRuntime(config=cfg) as rt:
        handle = _start_with_no_workers(rt, agent, "go")
        cfg.liveness_enabled = True  # arm the server-side monitor for join()

        t0 = time.monotonic()
        try:
            with pytest.raises(WorkerStallError) as exc_info:
                handle.join(timeout=20)
            elapsed = time.monotonic() - t0
        finally:
            try:
                handle.cancel("test cleanup")
            except Exception:
                pass  # already terminal — fine

    # The intrinsic stall detection latency is `stall_seconds + check_interval`
    # plus one ``join()`` poll tick (~1s). On a backlogged server, individual
    # ``get_status`` calls inside join's poll loop can take many seconds, so
    # wall-clock elapsed can exceed the configured stall window. The strong
    # assertion is the typed error itself, plus ``seconds_queued`` below.
    assert elapsed < 60, f"Stall detection too slow: {elapsed:.2f}s"
    err = exc_info.value
    names = {t.task_def_name for t in err.stalled_tasks}
    assert "slow_setup" in names, (
        f"Expected slow_setup in stalled tasks, got {names!r}"
    )
    assert any(
        t.seconds_queued >= cfg.liveness_stall_seconds for t in err.stalled_tasks
    ), (
        f"Expected at least one stalled task queued >= {cfg.liveness_stall_seconds}s, "
        f"got {[t.seconds_queued for t in err.stalled_tasks]!r}"
    )
    assert err.execution_id == handle.execution_id
    assert err.domain == handle.run_id


def test_server_liveness_disabled_yields_timeout_not_stall(fast_liveness_config):
    """Validity counter-test: with liveness_enabled=False throughout, the
    same stall scenario must end in ``TimeoutError`` from ``join()``, not
    ``WorkerStallError`` — proving the monitor is what's signaling.
    """
    cfg = fast_liveness_config
    cfg.liveness_stall_seconds = 3.0
    cfg.liveness_check_interval_seconds = 1.0
    cfg.liveness_enabled = False  # stays disabled the whole way

    agent = Agent(
        name=f"stall-disabled-{uuid.uuid4().hex[:8]}",
        model="openai/gpt-4o-mini",
        stateful=True,
        tools=[slow_setup],
        prefill_tools=[slow_setup.call(payload="probe")],
        max_turns=1,
    )

    with AgentRuntime(config=cfg) as rt:
        handle = _start_with_no_workers(rt, agent, "go")
        # liveness_enabled stays False — monitor should NOT spawn

        t0 = time.monotonic()
        try:
            with pytest.raises(TimeoutError):
                handle.join(timeout=10)
            elapsed = time.monotonic() - t0
        finally:
            try:
                handle.cancel("test cleanup")
            except Exception:
                pass

    # Real timeout, not early stall — should be close to the join timeout
    assert elapsed >= 9.0, f"Join returned suspiciously fast: {elapsed:.2f}s"


# ── Idempotent resume telemetry (Mode A) ────────────────────────────────


def test_idempotent_resume_sets_is_resumed_flag(caplog):
    """When ``runtime.start`` is called twice with the same
    ``idempotency_key`` from independent processes, the second call must
    re-attach to the existing execution and surface that fact via
    ``handle.is_resumed`` and the ``Resumed existing execution`` INFO
    log.

    Mechanism:
      1. First ``AgentRuntime`` starts a workflow with idempotency_key=K.
         Its workers register under a freshly-generated domain.
      2. The first runtime's ``with``-block exits → workers die. The
         workflow is left in whatever state it reached on the server.
      3. A second ``AgentRuntime`` calls ``start`` with the same K. The
         server returns the original ``execution_id``. ``_resolve_worker_domain``
         re-attaches the new runtime's workers under the original domain.
      4. ``is_resumed=True`` is set on the handle and the INFO log is
         emitted.

    The agent uses real workers (no monkey-patches) so the workflow
    actually runs to completion, demonstrating the resume path is
    functional, not just a flag.
    """
    import logging

    cfg1 = AgentConfig.from_env()
    cfg2 = AgentConfig.from_env()
    idempotency_key = f"t-resume-{uuid.uuid4().hex[:8]}"

    agent = Agent(
        name=f"resume-test-{uuid.uuid4().hex[:8]}",
        model="openai/gpt-4o-mini",
        stateful=True,
        tools=[liveness_probe],
        max_turns=1,
        instructions="Reply with the single word: pong.",
    )

    # ── First start ──────────────────────────────────────────────────
    with AgentRuntime(config=cfg1) as rt1:
        handle1 = rt1.start(agent, "ping", idempotency_key=idempotency_key)
        original_execution_id = handle1.execution_id
        original_run_id = handle1.run_id
        assert handle1.is_resumed is False, (
            "First start should not be a resume"
        )
        # Don't join — let the with-block exit, workers die.

    # ── Second start (resume) ───────────────────────────────────────
    caplog.set_level(logging.INFO, logger="agentspan.agents.runtime")
    caplog.clear()

    with AgentRuntime(config=cfg2) as rt2:
        handle2 = rt2.start(agent, "ping", idempotency_key=idempotency_key)
        try:
            assert handle2.execution_id == original_execution_id, (
                f"Resumed execution_id mismatch: "
                f"{handle2.execution_id!r} != {original_execution_id!r}"
            )
            assert handle2.is_resumed is True, (
                "is_resumed should be True on idempotency replay"
            )
            # The second runtime's run_id (newly generated) differs from
            # the recorded server domain (which equals original_run_id).
            # _resolve_worker_domain re-attaches under original_run_id.
            assert handle2.run_id == original_run_id, (
                f"handle2.run_id={handle2.run_id!r} should equal "
                f"original_run_id={original_run_id!r} (re-attached)"
            )

            # INFO log assertion — the precise marker the implementation emits.
            resume_logs = [
                r for r in caplog.records
                if r.levelname == "INFO"
                and "Resumed existing execution" in r.getMessage()
                and original_execution_id in r.getMessage()
            ]
            assert resume_logs, (
                "Expected INFO log 'Resumed existing execution ...' for "
                f"{original_execution_id}, got: "
                f"{[r.getMessage() for r in caplog.records if r.levelname=='INFO']!r}"
            )

            # Let the resumed workflow complete normally.
            result = handle2.join(timeout=60)
            assert result is not None
        finally:
            try:
                handle2.cancel("test cleanup")
            except Exception:
                pass


def test_fresh_start_does_not_set_is_resumed():
    """Validity counter-test: with a *new* idempotency_key (no prior
    execution to match), ``is_resumed`` must be False — proving the flag
    is meaningful and not always-True.
    """
    cfg = AgentConfig.from_env()

    agent = Agent(
        name=f"fresh-test-{uuid.uuid4().hex[:8]}",
        model="openai/gpt-4o-mini",
        stateful=True,
        tools=[liveness_probe],
        max_turns=1,
        instructions="Reply with the single word: pong.",
    )

    with AgentRuntime(config=cfg) as rt:
        handle = rt.start(
            agent,
            "ping",
            idempotency_key=f"t-fresh-{uuid.uuid4().hex[:8]}",
        )
        try:
            assert handle.is_resumed is False, (
                "Fresh start should never have is_resumed=True"
            )
            handle.join(timeout=60)
        finally:
            try:
                handle.cancel("test cleanup")
            except Exception:
                pass
