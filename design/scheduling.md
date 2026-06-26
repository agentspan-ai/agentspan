# Agent Scheduling

**Status**: Draft — pending review
**Date**: 2026-05-27
**Scope**: Phase 1 of [sentinel-agents](../python-sdk/sentinel-agents.md) — cron triggers only.

---

## 1. Goals

Let users put an agent on one or more cron schedules from code, with full lifecycle control (deploy, list, pause/resume, delete, ad-hoc run-now). Schedules survive process restarts; the orchestration server (Conductor) handles timing.

## 2. Model

```
Agent ──deploy──► WorkflowDef
                    ▲
                    │  startWorkflowRequest.name = agent.name
                    │
              ┌─────┴─────┬───────────┐
          Schedule    Schedule    Schedule       ← N independent crons per agent
        (name="A")  (name="B")  (name="C")
```

- One `Schedule` = one cron expression + one input + one name.
- An agent can have **N schedules**; pause/resume/delete each independently.
- **Ownership is implicit**: a schedule "belongs to" an agent iff `startWorkflowRequest.name == agent.name`. No tags or metadata needed — Conductor's `findAllSchedules(workflowName)` does the lookup.
- Server-side scheduler is **Conductor** (`/api/scheduler/*`). The SDK is a thin typed wrapper.

## 3. Conductor surface this builds on

Verified against [conductor-oss/conductor](https://github.com/conductor-oss/conductor):

| SDK call | Conductor endpoint | Source |
|---|---|---|
| Save / upsert | `POST /api/scheduler/schedules` | `SchedulerResource.java:62` |
| List for agent | `GET  /api/scheduler/schedules?workflowName={agent}` | `SchedulerResource.java:69` |
| Get one | `GET  /api/scheduler/schedules/{name}` | `SchedulerResource.java:93` |
| Delete | `DELETE /api/scheduler/schedules/{name}` | `SchedulerResource.java:99` |
| Pause | `PUT  /api/scheduler/schedules/{name}/pause?reason=...` | `SchedulerResource.java:110` |
| Resume | `PUT  /api/scheduler/schedules/{name}/resume` | `SchedulerResource.java:119` |
| Preview next N fires | `GET  /api/scheduler/nextFewSchedules?cronExpression=...&limit=N` | `SchedulerResource.java:130` |
| Run now (ad-hoc) | `POST /api/workflow/{agent.name}` (bypasses scheduler) | core workflow API |

The `WorkflowSchedule` payload sent in `POST /schedules`:

```json
{
  "name": "weekday-9am",
  "cronExpression": "0 9 * * MON-FRI",
  "zoneId": "America/Los_Angeles",
  "paused": false,
  "runCatchupScheduleInstances": false,
  "scheduleStartTime": null,
  "scheduleEndTime": null,
  "description": "Daily digest",
  "startWorkflowRequest": {
    "name": "daily_digest",
    "version": null,
    "input": { "channel": "#eng" },
    "correlationId": null
  }
}
```

## 4. Schedule object — fields

| Field | Type | Required | Default | Notes |
|---|---|---|---|---|
| `name` | string | **yes** | — | Unique per agent. SDK auto-prefixes the wire name as `{agent.name}-{name}` to satisfy Conductor's org-wide uniqueness constraint while preserving the per-agent mental model. Raise at construction if omitted. |
| `cron` | string | **yes** | — | 5- or 6-field cron (seconds optional). Server validates. |
| `timezone` | string | no | `"UTC"` | IANA tz id, maps to `zoneId`. |
| `input` | object | no | `{}` | Workflow input. |
| `catchup` | bool | no | `false` | Maps to `runCatchupScheduleInstances`. Replay missed fires on resume. |
| `paused` | bool | no | `false` | Start in paused state. |
| `start_at` | datetime | no | `null` | Window start (ms since epoch). |
| `end_at` | datetime | no | `null` | Window end. |
| `description` | string | no | `null` | Human-readable note. |

**Not exposed in v1**: `overlap` (Conductor fires every tick — agentspan-side skip/queue is future work), `cronSchedules` multi-cron list (covered by N schedules).

## 5. Lifecycle semantics

### 5.1 Deploy is declarative, scoped to this agent

```text
deploy(agent, schedules=...)
```

| `schedules=` value | Behavior |
|---|---|
| omitted / `None` | Leave existing schedules untouched. |
| `[]` (empty list) | Delete **all** schedules whose `workflowName == agent.name`. |
| `[Schedule(...), ...]` | **Upsert** the listed schedules; delete any other schedule whose `workflowName == agent.name`. |

Reconciliation algorithm:

```
existing  = SchedulerClient.getAllSchedules(workflowName=agent.name)
desired   = schedules
to_delete = {s.name for s in existing} - {s.name for s in desired}
to_upsert = desired
for s in to_delete: deleteSchedule(s)
for s in to_upsert: saveSchedule(s)
```

This works precisely because agent name = workflow name. No tagging scheme.

### 5.2 Module-level lifecycle API

All operations are keyed by schedule **name** — no handles to pass around, survives process restart.

```text
schedules.list(agent=name) -> [ScheduleInfo]
schedules.get(name)        -> ScheduleInfo
schedules.pause(name, reason=None)
schedules.resume(name)
schedules.delete(name)
schedules.run_now(name)               # bypasses scheduler; returns execution id immediately
schedules.run_now(name, wait=True)    # opt-in: block until completion (returns AgentResult)
schedules.executions(name, limit=20)  # past runs of this schedule
schedules.preview_next(cron, n=5)     # for UI / drawer
```

`ScheduleInfo` returned by `get` / `list`:

```
ScheduleInfo {
  name, cron, timezone, input, paused, paused_reason,
  catchup, start_at, end_at, description,
  next_run, last_run,        # epoch ms (server-computed)
  create_time, created_by, update_time, updated_by,
  agent,                     # = workflow name
}
```

### 5.3 Overlap

Fixed to `allow` in v1 (Conductor's native behavior). Every cron tick starts a new workflow execution even if the prior one is still running. Skip-if-running and queue policies are future agentspan-layer features.

### 5.4 Errors

- Duplicate `name` within the same agent → SDK raises `ScheduleNameConflict` before the wire call. Across agents, names are isolated by the `{agent.name}-` prefix, so no collision possible.
- Bad cron → 400. SDK surfaces `InvalidCronExpression` with the server's parse error.
- Schedule not found on `pause`/`resume`/`delete`/`get` → 404 → `ScheduleNotFound`.

---

## 6. Language SDK surfaces

Same semantics, idiomatic shape per language. All four wrap the same Conductor REST surface.

### 6.1 Python

```python
from agentspan.agents import Agent, deploy, schedules
from agentspan.agents.schedule import Schedule

agent = Agent(name="daily_digest", ...)

deploy(
    agent,
    schedules=[
        Schedule(
            name="weekday-9am",
            cron="0 9 * * MON-FRI",
            timezone="America/Los_Angeles",
            input={"channel": "#eng"},
        ),
        Schedule(name="friday-5pm", cron="0 17 * * FRI", input={"channel": "#all-hands"}),
    ],
)

schedules.list(agent="daily_digest")
schedules.pause("weekday-9am", reason="rate limit cooldown")
schedules.resume("weekday-9am")
schedules.run_now("weekday-9am")
schedules.delete("weekday-9am")
schedules.preview_next("0 9 * * MON-FRI", n=5)
```

`Schedule` is a `@dataclass(frozen=True)` (matches repo convention — no Pydantic). All names snake_case. Async siblings: `schedules.list_async`, `pause_async`, etc., plus `deploy_async(..., schedules=...)`.

### 6.2 TypeScript

```ts
import { Agent, deploy, schedules, Schedule } from "@agentspan/sdk";

const agent = new Agent({ name: "dailyDigest", /* ... */ });

await deploy(agent, {
  schedules: [
    new Schedule({
      name: "weekday-9am",
      cron: "0 9 * * MON-FRI",
      timezone: "America/Los_Angeles",
      input: { channel: "#eng" },
    }),
    new Schedule({ name: "friday-5pm", cron: "0 17 * * FRI", input: { channel: "#all-hands" } }),
  ],
});

await schedules.list({ agent: "dailyDigest" });
await schedules.pause("weekday-9am", { reason: "rate limit cooldown" });
await schedules.resume("weekday-9am");
await schedules.runNow("weekday-9am");
await schedules.delete("weekday-9am");
await schedules.previewNext("0 9 * * MON-FRI", { n: 5 });
```

Constructor takes a single options object (camelCase). Field renames: `timezone` (not `tz`), `catchup`, `startAt`, `endAt`. All operations return Promises. Type exported as `ScheduleOptions` for the constructor and `ScheduleInfo` for the runtime view.

### 6.3 Java

```java
import ai.agentspan.Agent;
import ai.agentspan.AgentRuntime;
import ai.agentspan.schedule.Schedule;
import ai.agentspan.schedule.Schedules;

Agent agent = Agent.builder().name("daily_digest")./*...*/.build();

AgentRuntime runtime = new AgentRuntime();
runtime.deploy(
    agent,
    List.of(
        Schedule.builder()
            .name("weekday-9am")
            .cron("0 9 * * MON-FRI")
            .timezone("America/Los_Angeles")
            .input(Map.of("channel", "#eng"))
            .build(),
        Schedule.builder()
            .name("friday-5pm")
            .cron("0 17 * * FRI")
            .input(Map.of("channel", "#all-hands"))
            .build()));

Schedules schedules = runtime.schedules();
schedules.list("daily_digest");
schedules.pause("weekday-9am", "rate limit cooldown");
schedules.resume("weekday-9am");
schedules.runNow("weekday-9am");
schedules.delete("weekday-9am");
schedules.previewNext("0 9 * * MON-FRI", 5);
```

`Schedule` uses Lombok `@Builder` (mirrors `WorkflowSchedule.java` from Conductor). `Schedules` is reached via `runtime.schedules()` rather than a top-level static — fits the existing `AgentRuntime`-centric Java idiom. Overloaded `deploy(Agent agent, List<Schedule> schedules)` extends the current `deploy(Agent...)`.

### 6.4 C#

```csharp
using Agentspan;
using Agentspan.Scheduling;

var agent = new Agent { Name = "daily_digest", /* ... */ };

await using var runtime = new AgentRuntime();
await runtime.DeployAsync(
    agent,
    schedules: new[]
    {
        new Schedule
        {
            Name     = "weekday-9am",
            Cron     = "0 9 * * MON-FRI",
            Timezone = "America/Los_Angeles",
            Input    = new { channel = "#eng" },
        },
        new Schedule
        {
            Name  = "friday-5pm",
            Cron  = "0 17 * * FRI",
            Input = new { channel = "#all-hands" },
        },
    });

var schedules = runtime.Schedules;
await schedules.ListAsync(agent: "daily_digest");
await schedules.PauseAsync("weekday-9am", reason: "rate limit cooldown");
await schedules.ResumeAsync("weekday-9am");
await schedules.RunNowAsync("weekday-9am");
await schedules.DeleteAsync("weekday-9am");
await schedules.PreviewNextAsync("0 9 * * MON-FRI", n: 5);
```

`Schedule` is a property-init record-style class. All operations async-first (sync wrappers mirror existing `AgentRuntime` style). `Schedules` accessor on `AgentRuntime` parallels Java.

---

## 7. UI

Two surfaces. Both back onto the same REST endpoints.

### 7.1 Agent detail → Schedules tab (new)

```
┌─ Agent: daily_digest ─────────────────────────────────────────────────┐
│  [ Overview ] [ Executions ] [ Schedules ] [ Versions ] [ Code ]      │
│ ───────────────────────────────────────────────────────────────────── │
│                                                              [+ New]  │
│  ● weekday-9am    0 9 * * MON-FRI   PT   next: Tue 9:00 AM            │
│      last: ✓ 2026-05-26 9:00 (12.4s)        [Pause] [Run now] [⋯]     │
│                                                                       │
│  ◐ friday-5pm     0 17 * * FRI      UTC  PAUSED (rate limit cooldown) │
│      last: ✓ 2026-05-22 17:00               [Resume] [Run now] [⋯]    │
└───────────────────────────────────────────────────────────────────────┘
```

Status glyph: ● active · ◐ paused · ⊘ expired. Row click → detail drawer.

### 7.2 New / edit drawer

```
┌─ New schedule ─────────────────────────────────────┐
│  Name *           [ weekday-9am               ]    │
│  Cron *           [ 0 9 * * MON-FRI           ]    │
│                   ⓘ "At 9:00 AM, Mon–Fri"          │
│                   Next: Tue 9:00 · Wed 9:00 · ...  │
│  Timezone         [ America/Los_Angeles      ▾ ]   │
│  Input (JSON)     ┌──────────────────────────┐     │
│                   │ { "channel": "#eng" }    │     │
│                   └──────────────────────────┘     │
│  Window           Start [ — ]  End [ — ]  (opt)    │
│  [ ] Catch up missed runs on resume                │
│  [ ] Start paused                                  │
│                                                    │
│             [ Cancel ]              [ Save ]       │
└────────────────────────────────────────────────────┘
```

Cron preview uses `GET /api/scheduler/nextFewSchedules` and the existing `cronExpressionHelpers.ts`.

### 7.3 Schedule detail drawer

- Header: name · cron · tz · status · `[Pause/Resume]` `[Run now]` `[Edit]` `[Delete]`
- Tabs:
  - **Executions** — table of past runs (started, duration, status, workflow id → click through)
  - **Definition** — read-only JSON
  - **History** — audit trail (created / paused with reason / edited)

### 7.4 Global Schedules list (existing page)

Add `Agent` column + filter to `ui/src/pages/scheduler/`. Same row controls. Becomes the cross-agent view; the agent-detail tab is just a filtered slice.

---

## 8. Out of scope (Phase 2+)

- Skip-if-running / queue overlap policies (agentspan-layer; Conductor doesn't support natively).
- Event / webhook / file / stream triggers (separate trigger types under the same `triggers=[...]` umbrella).
- Per-schedule retry / timeout / priority overrides.
- Memory persistence across scheduled runs (handled by `Agent(memory=...)`, not schedule-level).
- Optimistic concurrency on edit (Conductor uses last-write-wins; no ETag).

## 9. Validation evidence

- Conductor REST surface — `scheduler/corexx/src/main/java/io/orkes/conductor/scheduler/rest/SchedulerResource.java` (verified all endpoints exist).
- `findAllSchedules(orgId, workflowName)` — `scheduler/core/.../dao/scheduler/SchedulerDAO.java:36`.
- `WorkflowSchedule` model fields — `scheduler/corexx/.../model/WorkflowSchedule.java`.
- conductor-python already has `SchedulerClient` (`save_schedule`, `get_all_schedules(workflow_name=...)`, `delete_schedule`, `pause_schedule`, `resume_schedule`) — agentspan SDKs wrap it.
- agent.name → workflow name — `server/.../AgentService.java:222` (`def.getName()` returned as `agentName`).

## 10. Resolved design questions

1. **Module path** → `agentspan.agents.schedule.Schedule`. Ships only what exists today; if/when Webhook/Event triggers land, they get their own modules and we revisit a `triggers/` umbrella.
2. **`run_now` blocking** → returns the execution id immediately. Agents can run for minutes; blocking is the wrong default for a UI button or scripted invocation. Opt-in `wait=True` (Python/TS) / overloaded `runNowAndWait` (Java/C#) for sync use.
4. **Schedule name scoping** → unique **per agent**, not globally. The SDK auto-prefixes the wire name to `{agent.name}-{name}` at `deploy()` time so users write `Schedule(name="daily")` ergonomically while Conductor's org-wide uniqueness is satisfied. The prefixed name is the canonical identifier returned by `list()`/`get()` and accepted by `pause`/`resume`/`delete`/`run_now`. The `ScheduleInfo` dataclass exposes both `name` (prefixed, wire) and `short_name` (the user's original) for display.
3. **`nextRunTime` when paused-on-create** → verified against Conductor source (`scheduler/core/.../SchedulerService.java:732`): `setNextRunTimeInEpoch(...)` is called unconditionally on save; the `isPaused()` check only gates the queue-message push that triggers the fire. The UI's "Next: ..." column is reliable for paused schedules. No SDK or UI accommodation needed.
