# Worker Liveness & Idempotent Auto-Resume

**Date:** 2026-05-06
**Status:** Draft for review
**Owner:** Python SDK runtime

## Problem

When a Python SDK process that owns a Conductor execution dies — Ctrl-C, terminal close, SIGKILL, OOM, or a silent exception inside `WorkerManager.start()` — the workflow remains durable on the server but no worker is polling for the tools it needs. The execution stalls indefinitely with `pollCount=0` on every queued task. There is no signal back to the user; the only recovery today is to manually complete tasks via the Conductor UI or terminate the workflow.

Concrete incident: execution `9d7d0ac9-178a-46c6-9579-551e657889f2` (sub-workflow `95087a26-0c78-4424-9412-f06515343f50`) had `setup_repo` queued in domain `ad90efd2b73a460a84a6dd88bbe88a81` for ~192 seconds with `pollCount=0` before the user manually completed it through the UI. The parent workflow was eventually terminated.

## Failure modes

The same observable symptom — `pollCount=0` — has two distinct root causes that need different fixes:

**Mode A — process death after `start()` returned.** The Python process was killed after the workflow was created on the server. `_resolve_worker_domain` already re-attaches workers correctly when the user re-runs with the same `idempotency_key`, but:
- The user has no signal that a resume happened versus a fresh start.
- Without an `idempotency_key`, recovery requires explicitly calling `runtime.resume(execution_id, agent)`, which is not surfaced.

**Mode B — workers never polled even though the process is alive.** A registration race, a `fork()` deadlock on macOS, or a swallowed exception inside `WorkerManager._start_new_workers` leaves `_decorated_functions` populated but no polling subprocess actually running. `start()` returns successfully and `handle.join()` sits forever waiting on a task that no worker will pick up.

## Goals

1. Mode A: when an idempotency replay re-attaches workers, surface it clearly via log + handle attribute. Make `runtime.resume()` discoverable.
2. Mode B: detect "workers registered but not polling" within seconds, not minutes. Surface a typed exception with enough context to act on.
3. Add server-side stall detection in `handle.join()` so a mid-run worker death is caught, not silently waited on.
4. No new server-side changes. No new dependencies. Existing tests stay green.

## Non-goals

- Auto-discovery of orphaned executions on `AgentRuntime.__init__`. Listing all executions for a tenant is out of scope and invites surprise.
- Server-side stall detection or alerting. Conductor's behavior is not changed.
- Heartbeating to the server. Adds complexity and a new failure mode.
- Recovery for executions started without an `idempotency_key` and without an in-process `execution_id` — the explicit `runtime.resume()` API is the answer there and already exists.

## Architecture

Two independent mechanisms layered onto the existing `_resolve_worker_domain` plumbing in `AgentRuntime`. They share no state and can be enabled/disabled independently.

```
                                ┌────────────────────────────────┐
   start(idempotency_key=K) ──► │ server returns existing or     │
                                │ fresh execution_id             │
                                └──────────────┬─────────────────┘
                                               │
                                               ▼
                            _resolve_worker_domain (existing)
                                               │
                                               ▼
                            _prepare_workers   (existing)
                                               │
                  ┌────────────────────────────┴──────────────────────────┐
                  ▼                                                       ▼
        Mode B-1: LocalLivenessCheck (NEW)                 Mode A telemetry (NEW)
        Verify each registered worker process              If _extract_domain returned
        is alive within a short timeout.                   a domain != the run_id we
        Raise WorkerStartupError on failure.               generated, log INFO and set
                  │                                        AgentHandle.is_resumed=True.
                  ▼
        AgentHandle returned
                  │
                  ▼
        handle.join()
                  │
                  ▼
        Mode B-2: ServerLivenessMonitor (NEW)
        Daemon thread polls workflow.tasks every
        check_interval seconds. If a SCHEDULED task in
        our domain has been queued > stall_seconds with
        pollCount==0, store WorkerStallError on the
        handle. The poll loop raises it.
```

## Components

### `sdk/python/src/agentspan/agents/runtime/_liveness.py` (new)

A self-contained module, ~200 LOC, with three exported names.

#### `WorkerStartupError(RuntimeError)`

Raised by the local check. Carries:
- `missing: List[Tuple[str, Optional[str]]]` — `(task_def_name, domain)` pairs without a live process.
- `domain: Optional[str]` — the domain we were registering for (for diagnostics).
- `remediation: str` — short hint, e.g., `"Check logs for fork() failure; retry start()."`

#### `WorkerStallError(RuntimeError)`

Raised by the server-side monitor through the join() poll loop. Carries:
- `execution_id: str`
- `domain: Optional[str]`
- `stalled_tasks: List[StalledTaskInfo]` with `task_def_name`, `task_id`, `seconds_queued`.
- `remediation: str` — e.g., `"Re-run with idempotency_key=<...> to re-attach workers, or call runtime.resume(execution_id, agent)."`

#### `LocalLivenessCheck.verify(worker_manager, expected, *, timeout=2.0, poll_interval=0.05) -> None`

- `expected: Iterable[Tuple[str, Optional[str]]]` — `(task_def_name, domain)` pairs we just registered.
- Walks `worker_manager._task_handler.task_runner_processes`, indexes them by `(task_def_name, domain)` via `Worker.get_task_definition_name()` and `Worker.domain` as already used in `WorkerManager._start_new_workers`.
- For each expected pair, polls every `poll_interval` until we find a process whose `is_alive()` is True or the `timeout` elapses.
- On timeout: raises `WorkerStartupError` listing every pair still missing or dead.
- Pure local check, no network. Sub-second in the happy path.

Why local-only and not "wait for first server poll"? Because we don't yet know which task names will appear in the server-side queue (the workflow may not have scheduled any work for this tool yet). Process aliveness is the cheapest signal available at start().

#### `ServerLivenessMonitor`

```python
class ServerLivenessMonitor:
    def __init__(
        self,
        workflow_client,
        execution_id: str,
        domain: Optional[str],
        stall_seconds: float = 30.0,
        check_interval: float = 10.0,
        on_stall: Callable[[WorkerStallError], None],
    ): ...

    def start(self) -> None: ...   # spawn daemon thread
    def stop(self) -> None: ...    # cooperative stop
```

- Runs a daemon thread that calls `workflow_client.get_workflow(execution_id, include_tasks=True)` every `check_interval` seconds.
- Filters tasks where `domain == self.domain` (the SDK-registered domain) and `status == "SCHEDULED"`.
- If `now - scheduledTime > stall_seconds and pollCount == 0`, packages a `WorkerStallError` and invokes `on_stall(err)`. The monitor does not raise from its own thread; the handle's poll loop is responsible for surfacing the error.
- Auto-stops when the workflow status is terminal (`COMPLETED`/`FAILED`/`TERMINATED`/`PAUSED`/`TIMED_OUT`) or when `stop()` is called.
- One-shot: once `on_stall` has fired, the monitor stops itself. We don't want to re-raise repeatedly.

### `sdk/python/src/agentspan/agents/runtime/runtime.py` (modify)

After every call site that does `_prepare_workers(agent, ..., domain=worker_domain)` (there are four: `start`, `start_async`, `stream`, `stream_async`), call:

```python
expected_workers = self._collect_registered_pairs(agent, worker_domain)
LocalLivenessCheck.verify(self._worker_manager, expected_workers)
```

`_collect_registered_pairs(agent, domain)` is a small helper that walks the agent tree and returns the `(task_name, domain_for_that_worker)` pairs we actually pass to `worker_task(...)` — i.e., `(td.name, domain if (agent_stateful or td.stateful) else None)` matching the logic in `tool_registry.py:73`. We only check user-tool workers (the `@tool`-decorated ones), not system workers (stop_when, transfer, etc.) — system workers' liveness rides on the same WorkerManager and is implicitly covered by checking at least one process. For an MVP, checking the user tools is sufficient and avoids enumerating every system worker.

After `_start_via_server(...)` returns, compute:

```python
recorded_domain = self._extract_domain(execution_id)
is_resumed = bool(recorded_domain and run_id and recorded_domain != run_id)
if is_resumed:
    logger.info(
        "Resumed existing execution %s (status=%s) under domain %s — "
        "re-attaching workers. Triggered by idempotency_key=%s.",
        execution_id, status, recorded_domain, idempotency_key,
    )
```

Pass `is_resumed` into the `AgentHandle` constructor.

### `sdk/python/src/agentspan/agents/run.py` — `AgentHandle` (modify)

Add fields:
- `is_resumed: bool = False`
- `_stall_error: Optional[WorkerStallError] = None`
- `_liveness_monitor: Optional[ServerLivenessMonitor] = None`

In `join()` (and async equivalents), the existing `_poll_status_until_complete` loop checks `self._stall_error is not None` at the top of each iteration; if set, raise it. Stop the monitor in a `finally` block when the workflow reaches a terminal state.

Start the monitor lazily on first `join()` call (not in `__init__`) so handles created and discarded without joining don't spawn threads.

### `sdk/python/src/agentspan/agents/runtime/config.py` (modify)

Add four `AgentRuntimeConfig` fields, all with safe defaults:

| Field | Default | Purpose |
|---|---|---|
| `liveness_startup_timeout_seconds` | `2.0` | LocalLivenessCheck timeout |
| `liveness_stall_seconds` | `30.0` | ServerLivenessMonitor: queued-with-zero-polls threshold |
| `liveness_check_interval_seconds` | `10.0` | ServerLivenessMonitor: tick interval |
| `liveness_enabled` | `True` | Master kill-switch — set `False` to disable both checks |

Plumb via env vars in `AgentRuntimeConfig.from_env()` using existing patterns (`AGENTSPAN_LIVENESS_*`).

## Error flow

| Scenario | Detected by | Surfaces as | Latency |
|---|---|---|---|
| Worker process never forked (e.g., `_decorated_functions` empty) | `LocalLivenessCheck` | `WorkerStartupError` from `start()` | ≤ 2s |
| Worker process forked then died immediately | `LocalLivenessCheck` retry loop | `WorkerStartupError` from `start()` | ≤ 2s |
| Process alive but polling thread wedged | `ServerLivenessMonitor` | `WorkerStallError` raised inside `handle.join()` | ~30–40s after task scheduled |
| User Ctrl-C'd previous run, re-runs with same idempotency_key | `_extract_domain` (existing) + new INFO log | `is_resumed=True`, INFO log; workers re-poll | immediate at `start()` |
| Process killed mid-run by external SIGKILL, no re-run | not detected by SDK (no live process) | n/a — user must `runtime.resume(execution_id, agent)` from a new process | n/a |
| Re-run from a new process; workers attach but slow first poll | `ServerLivenessMonitor` (suppressed) | Nothing — first poll arrives within 30s grace | n/a |

All exceptions carry `execution_id`, `domain`, the offending workers, and a one-line `remediation` string.

## Testing

Per `CLAUDE.md`: real e2e, no mocks, deterministic assertions, total suite ≤ 12 minutes (target ≤ 90 seconds for these three).

### Test 1 — `test_worker_startup_failure_raises_within_timeout` (e2e)

1. Create a `@tool` `slow_setup` whose function body is irrelevant.
2. Build a stateful agent with that tool.
3. Monkeypatch `WorkerManager._start_new_workers` to no-op (worker is registered in `_decorated_functions` but no process is created).
4. Call `runtime.start(agent, "go")`.
5. **Assert**: raises `WorkerStartupError` within 5 wall-clock seconds. Algorithmic — check exception type, `missing` list contains `("slow_setup", <domain>)`.
6. **Validity check (CLAUDE.md rule #2)**: temporarily disable the new check, re-run, assert the test FAILS with timeout-on-join — proves the test is real.

### Test 2 — `test_worker_stall_detected_during_join` (e2e)

1. Configure runtime with `liveness_stall_seconds=5`, `liveness_check_interval_seconds=2` to keep the test fast.
2. Start agent with `slow_setup` tool that returns immediately.
3. After `start()` returns, kill the worker subprocess via `process.terminate()`.
4. Use a `prefill_tools=[slow_setup.call(...)]` setup so the workflow schedules `slow_setup` deterministically without needing an LLM turn.
5. Call `handle.join(timeout=30)`.
6. **Assert**: raises `WorkerStallError` within 20s. Algorithmic — `stalled_tasks[0].task_def_name == "slow_setup"`, `stalled_tasks[0].seconds_queued >= 5`.
7. **Validity check**: with `liveness_enabled=False`, the same scenario must time out at 30s without the typed error.

### Test 3 — `test_idempotent_resume_sets_is_resumed_flag` (e2e)

1. `runtime.start(agent, "go", idempotency_key="t-resume-3")` → note `execution_id`. Stop the runtime cleanly (workers die).
2. New `AgentRuntime`. Call `runtime.start(agent, "go", idempotency_key="t-resume-3")`.
3. **Assert**: `handle.execution_id == original_execution_id`, `handle.is_resumed is True`, INFO log emitted (capture via caplog).
4. Let `handle.join()` complete normally.
5. **Validity check**: with the new INFO log temporarily commented out, the assertion on log content fails — proves we're checking the real signal, not a stub.

### Algorithmic-only validation

No LLM is used to assert correctness in these tests. Per memory `feedback_algorithmic_validation`: every assertion is on exception types, dataclass fields, log content, or workflow status fetched from the real Conductor server.

### Runtime budget

Each test ≤ 30s (test 1: ≤5s, test 2: ≤20s, test 3: ≤30s). Test 2 uses `liveness_stall_seconds=5` and `liveness_check_interval_seconds=2` to keep the stall-detection window short. Total suite well under the 12-minute e2e ceiling.

## Compatibility & rollout

- All new behavior is feature-flagged via `liveness_enabled` (default `True`) so a regression can be reverted by setting `AGENTSPAN_LIVENESS_ENABLED=false`.
- `AgentHandle.is_resumed` is a new attribute with a default; no existing user code breaks.
- New exception classes inherit from `RuntimeError`, so `except Exception` callers see them; users who want to handle them specifically can import from `agentspan.agents.runtime`.
- No server-side change. No new dependencies. No protocol change.

## Open questions

None. All design decisions resolved during brainstorming on 2026-05-06.
