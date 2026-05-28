# Implementation Plan: Agent Scheduling

**Date**: 2026-05-27
**Spec**: [`docs/design/scheduling.md`](../scheduling.md)
**Scope**: Phase 1 — cron triggers across server (passthrough), 4 SDKs, UI.

---

## Strategy

Conductor's scheduler already provides everything we need at the REST + DAO layer. **No server-side scheduler work** — agentspan's server stays thin. The SDKs wrap `conductor-python` / `conductor-client` / etc. directly. The UI extends the existing `ui/src/pages/scheduler/` page and adds an agent-scoped tab.

Each stage is independently shippable. Python ships first (it's the canonical SDK and the eval suite uses it). UI ships in parallel once the Python SDK contract is stable.

Order:
1. **Stage 0** — Pre-work & test fixtures
2. **Stage 1** — Python SDK
3. **Stage 2** — TypeScript SDK
4. **Stage 3** — Java SDK
5. **Stage 4** — C# SDK
6. **Stage 5** — UI (agent Schedules tab + global list extension)
7. **Stage 6** — Validation (e2e per SDK, manual UI walkthrough)
8. **Stage 7** — Docs

Stages 2–4 are independent; can be parallelized after Stage 1's contract is locked.

---

## Stage 0 — Pre-work & test fixtures

**Goal**: confirm Conductor scheduler is reachable from the dev stack and lock the on-the-wire payload.

- [ ] Verify the bundled Conductor (referenced by `server/build.gradle`) includes the scheduler module on the default profile. If not, document the profile flag in `deployment.md` (separate doc task).
- [ ] Write a hand-rolled HTTP probe (`scripts/probe-scheduler.sh`) that:
  - `POST /api/scheduler/schedules` with a paused schedule pointing at a no-op workflow
  - `GET /api/scheduler/schedules?workflowName=...`
  - `PUT .../pause` + `.../resume`
  - `DELETE`
- [ ] Capture exact JSON shape returned by `GET /schedules/{name}` and `GET /schedules?workflowName=...` — locks the `ScheduleInfo` field mapping for all SDKs.
- [ ] Add `e2e/fixtures/noop_agent.py` — a minimal agent (no LLM call) used by every scheduling e2e test so we don't burn LLM budget validating cron plumbing.

**Exit criteria**: probe script round-trips every endpoint; captured JSON committed as `e2e/fixtures/scheduler_response_samples.json`.

---

## Stage 1 — Python SDK (canonical)

`sdk/python/src/agentspan/agents/schedule/`

### Files

```
sdk/python/src/agentspan/agents/schedule/
  __init__.py          # exports Schedule, ScheduleInfo, schedules namespace
  schedule.py          # @dataclass(frozen=True) Schedule + ScheduleInfo
  client.py            # thin wrapper over conductor-python SchedulerClient
  errors.py            # ScheduleNameConflict, InvalidCronExpression, ScheduleNotFound
```

### Work items

- [ ] `Schedule` dataclass with `__post_init__` validating: name non-empty, cron non-empty (don't re-validate cron syntax — let server do it); raise `ValueError` if `start_at >= end_at`.
- [ ] `ScheduleInfo` dataclass mirroring Conductor's `WorkflowSchedule` response (plus computed `agent` = `startWorkflowRequest.name`).
- [ ] `client._to_workflow_schedule(s: Schedule, agent_name: str) -> dict` — produces the on-wire JSON. Unit-tested against `scheduler_response_samples.json`.
- [ ] `client._from_workflow_schedule(d: dict) -> ScheduleInfo` — inverse mapping.
- [ ] `schedules` module-level API: `list`, `get`, `pause`, `resume`, `delete`, `run_now`, `executions`, `preview_next`, plus `_async` siblings.
- [ ] Wire `deploy(agent, schedules=...)` reconciliation into `AgentRuntime.deploy` (`sdk/python/src/agentspan/agents/runtime/runtime.py:2225`):
  - After the existing `_deploy_via_server` call, if `schedules is not None`, run the reconcile algorithm from spec §5.1.
  - Tri-state semantics: `None` skip, `[]` purge, `[...]` upsert+delete-others.
- [ ] Error translation: map `conductor-python` HTTP errors → typed agentspan errors.
- [ ] `run_now` does not call the scheduler API — it calls the workflow start API with the schedule's stored `input` (fetched via `get`). Returns `execution_id: str`. With `wait=True`, polls until terminal and returns `AgentResult`.

### Tests (unit, no LLM)

- [ ] `tests/unit/schedule/test_schedule_validation.py` — Schedule construction failure modes.
- [ ] `tests/unit/schedule/test_payload_mapping.py` — round-trips against `scheduler_response_samples.json`.
- [ ] `tests/unit/schedule/test_reconcile.py` — reconciliation algorithm with mocked client (declarative semantics: None vs [] vs list).

### E2E (no LLM — per CLAUDE.md)

`sdk/python/e2e/test_suite_NN_scheduling.py`

Each test follows the project rule: **write the test, make it fail first, then make it pass**.

- [ ] `test_deploy_creates_schedule` — deploy agent with one Schedule; assert it appears in `schedules.list(agent=...)`.
- [ ] `test_deploy_upserts_and_prunes` — deploy with [A, B]; redeploy with [A, C]; assert B is gone, C is present, A is unchanged.
- [ ] `test_deploy_empty_list_purges` — deploy with [A]; redeploy with []; assert no schedules remain.
- [ ] `test_deploy_none_preserves` — deploy with [A]; redeploy with `schedules=None`; assert A is unchanged.
- [ ] `test_pause_resume_lifecycle` — pause with reason; assert `paused=True` and reason persists; resume; assert `paused=False`.
- [ ] `test_run_now_returns_execution_id` — call `run_now`; assert execution id is returned immediately (under 1s); poll until workflow completes.
- [ ] `test_delete_idempotent` — delete twice; second call must not raise (or raises typed `ScheduleNotFound` — pick one and lock).
- [ ] `test_paused_on_create_has_next_run_time` — confirms the Conductor behavior from spec §10 Q3.

**Exit criteria**: all e2e pass against a local Conductor; lint + format clean (`ruff check`, `ruff format`).

---

## Stage 2 — TypeScript SDK

`sdk/typescript/src/schedule/`

### Files

```
sdk/typescript/src/schedule/
  index.ts             # public exports
  schedule.ts          # Schedule class + ScheduleInfo + ScheduleOptions types
  client.ts            # HTTP client (uses existing httpRequest plumbing)
  errors.ts            # typed error classes
```

### Work items

- [ ] `Schedule` class constructor takes a `ScheduleOptions` object; camelCase fields (`timezone`, `startAt`, `endAt`, `catchup`).
- [ ] Same payload mapping helpers as Python; share the `scheduler_response_samples.json` fixture.
- [ ] Wire `deploy(agent, { schedules })` into existing `deploy` in `sdk/typescript/src/runtime.ts:381` (extend signature to accept an options object).
- [ ] `schedules` namespace export with `list`, `get`, `pause`, `resume`, `delete`, `runNow`, `executions`, `previewNext`. All return Promises.
- [ ] Mirror Python reconciliation semantics.

### Tests

- [ ] `sdk/typescript/tests/unit/schedule/*.test.ts` mirroring Python unit tests.
- [ ] `sdk/typescript/tests/e2e/test_suite_NN_scheduling.test.ts` mirroring the Python e2e suite test-for-test.

**Exit criteria**: parity with Python e2e suite; `pnpm typecheck && pnpm test` clean.

---

## Stage 3 — Java SDK

`sdk/java/src/main/java/ai/agentspan/schedule/`

### Files

```
sdk/java/src/main/java/ai/agentspan/schedule/
  Schedule.java        # Lombok @Builder, immutable
  ScheduleInfo.java
  Schedules.java       # interface; instance accessed via runtime.schedules()
  SchedulesImpl.java   # uses Conductor Java SchedulerClient
  ScheduleException.java + subclasses
```

### Work items

- [ ] `Schedule` with Lombok `@Builder`; required-field validation in builder's `build()`.
- [ ] Add `runtime.schedules()` accessor to `AgentRuntime` (`sdk/java/src/main/java/ai/agentspan/AgentRuntime.java`).
- [ ] Overload `AgentRuntime.deploy(Agent agent, List<Schedule> schedules)` — Java doesn't have keyword args; the overload is clearer than a builder for a one-shot call.
- [ ] For `runNowAndWait`, provide overload that returns `AgentResult` (mirrors existing `run` vs `start` split in the Java SDK).

### Tests

- [ ] `sdk/java/src/test/...Schedule*Test.java` for unit-level mapping.
- [ ] `sdk/java/examples/.../Example99ScheduledAgent.java` exercised by the existing examples test harness.
- [ ] Cross-SDK e2e parity test driven from the same scenario list as Python/TS.

**Exit criteria**: Gradle build + tests clean; example runs against local Conductor.

---

## Stage 4 — C# SDK

`sdk/csharp/src/Agentspan/Scheduling/`

### Files

```
sdk/csharp/src/Agentspan/Scheduling/
  Schedule.cs          # property-init class
  ScheduleInfo.cs
  Schedules.cs         # accessor on AgentRuntime
  SchedulesImpl.cs
  ScheduleExceptions.cs
```

### Work items

- [ ] `Schedule` as init-property class; `Cron` and `Name` required (compile-time enforced via `required` modifier where target framework allows; otherwise runtime check).
- [ ] Add `Schedules` property to `AgentRuntime` (`sdk/csharp/src/Agentspan/AgentRuntime.cs:20`).
- [ ] `DeployAsync` overload accepting `IEnumerable<Schedule>? schedules = null` with tri-state semantics.
- [ ] Async-first methods (`ListAsync`, `PauseAsync`, etc.) + sync wrappers matching the existing `Run`/`RunAsync` pattern.

### Tests

- [ ] `sdk/csharp/tests/Scheduling/*Tests.cs` unit + integration.
- [ ] Cross-SDK parity scenario as above.

**Exit criteria**: `dotnet test` clean; sample in `sdk/csharp/examples/` runs.

---

## Stage 5 — UI

### 5a. Agent detail → Schedules tab (new)

`ui/src/pages/agents/<agent>/Schedules.tsx` (or wherever the agent detail tabs live — verify path before starting).

- [ ] New tab component that calls `GET /api/scheduler/schedules?workflowName={agent.name}` (no new endpoint needed).
- [ ] Reuse existing `ScheduleButtons.tsx`, `CronExpressionHelp.tsx`, `cronExpressionHelpers.ts`, `TimezonePicker.tsx`.
- [ ] Row layout per spec §7.1: status glyph · name · cron · tz · next run · last run · actions.
- [ ] Pause action opens a small inline prompt for optional `reason`; calls `PUT .../pause?reason=...`.

### 5b. New/edit drawer

- [ ] Reuse the existing schedule editor (`ui/src/pages/scheduler/Schedule.tsx`) but launch it in drawer mode when entered from an agent context — workflow name is pre-filled and locked.
- [ ] Add the "Catch up missed runs on resume" checkbox (currently hidden; field exists in `IScheduleDto`).
- [ ] Add "Start paused" checkbox.

### 5c. Schedule detail drawer

- [ ] Tabs: Executions / Definition / History.
- [ ] Executions tab uses existing `GET /api/scheduler/search/executions` (`SchedulerResource.java:145`).

### 5d. Global Schedules list

- [ ] Extend `ui/src/pages/scheduler/` list view: add `Agent` column (derived from `startWorkflowRequest.name`) and an Agent filter.

**Exit criteria**: golden-path manual walkthrough (create, pause with reason, resume, edit, run now, delete) on local stack with screenshots.

---

## Stage 6 — Validation

This is its own stage per project rule.

- [ ] All e2e suites (Python, TS, Java, C#) pass against a clean Conductor instance.
- [ ] **Make-it-fail check** per CLAUDE.md: for each new e2e test, before claiming pass, temporarily break the production code path it covers and confirm the test fails — then revert. Capture this as a checklist item with sign-off.
- [ ] UI manual walkthrough per Stage 5 exit criteria.
- [ ] Cross-SDK contract check: same agent deployed from Python, listed from TS, paused from Java, resumed from C# — confirm the schedule round-trips identically.
- [ ] Edge cases:
  - Schedule with `paused=true` on first create shows correct `nextRunTime` in UI (regression guard for the Q3 Conductor behavior).
  - Bad cron expression returns typed error in all 4 SDKs with the server's parse message preserved.
  - Duplicate name across two different agents returns `ScheduleNameConflict` (lock the global-uniqueness behavior at the SDK layer).

**Exit criteria**: validation checklist signed off; no open P0/P1 bugs.

---

## Stage 7 — Documentation

- [ ] User-facing scheduling guide: `docs/scheduling.md` (different from the design doc — this is for users). Cover: quickstart per language, declarative deploy semantics with the tri-state table, lifecycle examples, FAQ.
- [ ] Per-SDK API reference updates:
  - `docs/python-sdk/api-reference.md` — add Schedule + schedules namespace.
  - `docs/typescript-sdk/` — new schedule page.
  - Java + C# API ref entries.
- [ ] Add to `mkdocs.yml` nav.
- [ ] Working examples committed to each SDK's `examples/` directory:
  - `sdk/python/examples/NN_scheduled_digest.py`
  - `sdk/typescript/examples/NN-scheduled-digest.ts`
  - `sdk/java/examples/.../Example99ScheduledAgent.java`
  - `sdk/csharp/examples/Scheduling/Program.cs`
- [ ] Mark `docs/python-sdk/sentinel-agents.md` Phase 1 items as shipped.

**Exit criteria**: docs PR merged; examples runnable from a fresh checkout per `quickstart.md`.

---

## Open dependencies / risks

1. **Conductor version pinning** — confirm `server/build.gradle` resolves a Conductor with the `SchedulerResource` already wired. If we're behind, bump first.
2. **conductor-python version** — `pyproject.toml:13` pins `conductor-python>=1.3.11`. Verify `SchedulerClient.get_all_schedules(workflow_name=...)` is in that range (it is, as of the installed copy probed above).
3. **TS / Java / C# Conductor clients** — confirm each has equivalent `SchedulerClient` surface; if any lacks `get_all_schedules(workflowName)`, we fall back to filtering client-side from `getAllSchedules()`. Add a check item to Stage 0.
4. **Auth scoping** — `SchedulerResource` uses `getOrgId()`; multi-tenant deployments need agent + schedule in the same org. Worth a smoke test in Stage 6.
5. **Schedule name scoping** — Resolved: SDK auto-prefixes wire names as `{agent.name}-{name}`. Users write `Schedule(name="daily")`; lifecycle calls (`pause`/`resume`/etc.) use the prefixed wire name returned by `list()`. `ScheduleInfo` exposes both `name` (prefixed) and `short_name` (original).

---

## Sequencing recommendation

```
Stage 0 ─► Stage 1 ─┬─► Stage 2 ─┐
                    ├─► Stage 3 ─┼─► Stage 6 ─► Stage 7
                    ├─► Stage 4 ─┤
                    └─► Stage 5 ─┘
```

Stage 1 must finish first because it locks the on-wire payload and the reconcile semantics that 2/3/4/5 mirror. After that, the four downstream stages parallelize.
