# Sentinel Agents

**Status:** Consolidated 2026-06-26 (scheduling shipped; other triggers roadmap)

**Scope:** Sentinel Agents are always-on, event-driven agents — regular agents (model + tools + instructions) augmented with **triggers** that define when and how they activate. Where today's agentic frameworks are request-response (a human prompts, the agent runs once, returns), sentinels are autonomous background processes with LLM brains: a scheduled health-checker, a log watcher that files tickets on errors, an incident responder that wakes on a PagerDuty alert, a PR reviewer triggered by a webhook. Each needs **activation** (something to wake it), **context** (the triggering data injected into its prompt), **tools** (actions it can take), **durability** (retry, audit, timeout), and **lifecycle management** (deploy, pause, resume, undeploy, observe). This doc defines the trigger model, the **shipped** Phase 1 (declarative cron scheduling, across all four SDKs and the UI), and the roadmap for the remaining trigger types. See also [`agentspan-design.md`](agentspan-design.md), [`sdk-design.md`](sdk-design.md), and [`stateful-agents.md`](stateful-agents.md).

---

## 1. Scope & Vision

A **Sentinel Agent** is a regular agent with one addition — **triggers** that define when and how it activates:

```
Sentinel Agent = Agent + Triggers
```

The agent definition describes **what** it does. Triggers describe **when** it runs.

The activation layer sits in front of agent execution. A trigger fires, injects context into the prompt template, the agent executes (LLM ↔ tools, with guardrails and optional memory), and the result drives an action — an alert, a fix, a report, a ticket, a restart.

```
┌──────────────────────────────────────────────────────────────┐
│                     ACTIVATION LAYER                          │
│                                                               │
│   ┌──────────┐ ┌───────────┐ ┌─────────┐ ┌───────────────┐  │
│   │ Schedule  │ │  Event    │ │ Webhook │ │  Source Watch  │  │
│   │ (cron)   │ │ (pub/sub) │ │ (HTTP)  │ │ (file/stream) │  │
│   └────┬─────┘ └─────┬─────┘ └────┬────┘ └───────┬───────┘  │
│        │              │            │              │           │
│        └──────────────┴────────────┴──────────────┘           │
│                           │                                   │
│                    ┌──────▼──────┐                             │
│                    │   TRIGGER   │ ← context injected          │
│                    │   (prompt)  │   into prompt template       │
│                    └──────┬──────┘                             │
│                           │                                   │
│              ┌────────────▼─────────────┐                     │
│              │    AGENT EXECUTION       │                     │
│              │  ┌─────┐ ┌─────┐ ┌────┐ │                     │
│              │  │ LLM │→│Tools│→│ LLM│ │                     │
│              │  └─────┘ └─────┘ └────┘ │                     │
│              │  + guardrails + memory   │                     │
│              └────────────┬─────────────┘                     │
│                           │                                   │
│                    ┌──────▼──────┐                             │
│                    │   ACTION    │ (alert, fix, report,        │
│                    │   (output)  │  create ticket, restart...) │
│                    └─────────────┘                             │
└──────────────────────────────────────────────────────────────┘
```

### Landscape & the gap

No current framework provides a clean, unified model for always-on, multi-trigger agents with durable execution and simple deployment.

| Capability | AutoGen | CrewAI | LangGraph | **Ours (Goal)** |
|---|---|---|---|---|
| Cron scheduling | - | - | Partial | **Yes (shipped)** |
| Event triggers | Internal | Internal | Webhooks | **Yes (Conductor events)** |
| Webhook triggers | - | - | Status only | **Yes** |
| File/log watching | - | - | - | **Yes (local daemon)** |
| Stream watching (Kafka/Redis) | - | - | - | **Yes (local consumer)** |
| Multi-trigger per agent | - | - | - | **Yes** |
| Durable execution (retry, audit) | - | - | Yes | **Yes (Conductor)** |
| Simple deployment | - | - | Managed service | **Yes (pip + one command)** |

- **AutoGen v0.4 (AG2)** — async, event-driven actor model with rich event surfacing. *Gap*: no deployment model, no external triggers; you run it, it runs once.
- **CrewAI** — Crews (agent groups) vs. Flows (event-driven pipelines). *Gap*: "events" are internal flow routing, not external activation; no cron/file/webhook out of the box.
- **LangGraph Platform** — background runs, task queue, webhook status callbacks, mentions cron. *Gap*: a managed deployment service, not a framework primitive; limited event sources; no local daemon patterns.
- **OmniDaemon (research)** — daemon + topic subscription (e.g. Redis streams). *Gap*: single event-source type; no scheduling, no file watching.
- **Microsoft Sentinel (security)** — sidecar deployment, continuous behavioral monitoring, hybrid rule + LLM auditing. *Gap*: domain-specific, not general-purpose.

## 2. Trigger Model

Five trigger types span the spectrum from fully server-managed to local-daemon-driven. **Schedule is shipped today (Phase 1)**; the rest are roadmap (Section 4).

| Trigger | Activation | Deployment | Status |
|---|---|---|---|
| **Schedule** | cron expression | server-side | **Shipped** |
| **EventTrigger** | named pub/sub event | server-side | Roadmap |
| **WebhookTrigger** | matching HTTP request | server-side | Roadmap |
| **FileWatch** | local file matches pattern | local watcher | Roadmap |
| **StreamWatch** | message on a stream | local consumer | Roadmap |

#### Schedule
Runs the agent on a cron expression. Server-side — the orchestration platform handles timing. See Section 3 for the shipped API.

```
Schedule:
  cron: "*/5 * * * *"          # every 5 minutes
  prompt: "Run health checks on all production services."
  timezone: "UTC"               # optional
  start_time: null              # optional window start
  end_time: null                # optional window end
  catch_up: false               # run missed executions?
```

**Maps to**: Conductor `SchedulerClient.save_schedule()` / any execution engine's cron scheduler.

#### Event Trigger
Runs the agent when a named event fires. The event payload is injected into the prompt.

```
EventTrigger:
  event: "pagerduty:incident"   # event source/name
  condition: "event.severity == 'critical'"  # optional filter
  prompt: "Critical incident: ${event.title}\nDetails: ${event.description}"
```

**Maps to**: Conductor `EventHandler` / Kafka consumer / any pub-sub system.

#### Webhook Trigger
Runs the agent when an HTTP request arrives matching certain criteria.

```
WebhookTrigger:
  matches:                      # payload matching criteria
    type: "pull_request"
    action: "opened"
  prompt: "New PR opened: ${webhook.payload}"
```

**Maps to**: Conductor webhook receiver / any HTTP endpoint that starts a workflow.

#### File Watch
Runs the agent when a local file matches a pattern. Requires a local watcher process.

```
FileWatch:
  path: "/var/log/myapp/*.log"  # file path or glob
  pattern: "(ERROR|CRITICAL)"   # regex to match
  prompt: "Log error detected:\n\n{matched_lines}"
  debounce: 30                  # seconds between triggers (prevent storm)
  lookback: 50                  # lines of context around match
```

**Maps to**: Local daemon thread that tails files → calls workflow start API on match.

#### Stream Watch
Runs the agent when a message appears on a message stream.

```
StreamWatch:
  source: "kafka://alerts-topic"   # or redis://stream, sqs://queue, etc.
  filter: "message.level == 'error'"
  prompt: "Alert from stream: {message}"
```

**Maps to**: Local consumer thread → calls workflow start API on message.

### Prompt templating

Triggers inject context into the agent's prompt via template variables:

| Trigger Type | Available Variables |
|---|---|
| Schedule | `{run_time}`, `{run_count}`, `{last_run_time}` |
| EventTrigger | `${event.*}` (event payload fields) |
| WebhookTrigger | `${webhook.payload}`, `${webhook.headers}` |
| FileWatch | `{matched_lines}`, `{filepath}`, `{line_number}`, `{match}` |
| StreamWatch | `{message}`, `{topic}`, `{offset}`, `{timestamp}` |

Server-side triggers use `${...}` (Conductor expression syntax, resolved server-side). Local triggers use `{...}` (resolved by the local watcher before workflow start).

## 3. Phase 1 — Scheduling (SHIPPED)

**Status: complete across all four SDKs (Python, TypeScript, Java, C#) and the UI (2026-06).** Users can put an agent on one or more cron schedules from code, with full lifecycle control (deploy, list, pause/resume, delete, ad-hoc run-now). Schedules survive process restarts; the orchestration server (Conductor) handles timing.

### 3.1 Model

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

### 3.2 Conductor surface this builds on

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

### 3.3 Schedule object — fields

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

### 3.4 Lifecycle semantics

#### Deploy is declarative, scoped to this agent

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

#### Module-level lifecycle API

All operations are keyed by schedule **name** — no handles to pass around, survives process restart.

```text
schedules.list(agent=name) -> [ScheduleInfo]
schedules.get(name)        -> ScheduleInfo
schedules.pause(name, reason=None)
schedules.resume(name)
schedules.delete(name)
schedules.run_now(name)               # bypasses scheduler; returns execution id immediately
schedules.run_now(name, wait=True)    # synchronous wait variant — block until completion (all four SDKs)
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

#### Overlap

Fixed to `allow` in v1 (Conductor's native behavior). Every cron tick starts a new workflow execution even if the prior one is still running. Skip-if-running and queue policies are future agentspan-layer features.

#### Errors

- Duplicate `name` within the same agent → SDK raises `ScheduleNameConflict` before the wire call. Across agents, names are isolated by the `{agent.name}-` prefix, so no collision possible.
- Bad cron → 400. SDK surfaces `InvalidCronExpression` with the server's parse error.
- Schedule not found on `pause`/`resume`/`delete`/`get` → 404 → `ScheduleNotFound`.

### 3.5 Language SDK surfaces

Same semantics, idiomatic shape per language. All four wrap the same Conductor REST surface.

#### Python

```python
from conductor.ai.agents import Agent, deploy, schedules
from conductor.ai.agents.schedule import Schedule

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

#### TypeScript

```ts
import { Agent, deploy, schedules, Schedule } from "@conductoross/conductor-agent-sdk";

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

#### Java

```java
import org.conductoross.conductor.ai.Agent;
import org.conductoross.conductor.ai.AgentRuntime;
import org.conductoross.conductor.ai.schedule.Schedule;
import org.conductoross.conductor.ai.schedule.Schedules;

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
schedules.runNow("weekday-9am");                  // name-keyed; fire-and-return execution id
schedules.runNowAndWait("weekday-9am");           // synchronous wait variant (returns AgentResult)
schedules.delete("weekday-9am");
schedules.previewNext("0 9 * * MON-FRI", 5);
```

`Schedule` uses Lombok `@Builder` (mirrors `WorkflowSchedule.java` from Conductor). `Schedules` is reached via `runtime.schedules()` rather than a top-level static — fits the existing `AgentRuntime`-centric Java idiom. Overloaded `deploy(Agent agent, List<Schedule> schedules)` extends the current `deploy(Agent...)`.

#### C#

```csharp
using Conductor.AI;
using Conductor.AI.Scheduling;

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
await schedules.RunNowAsync("weekday-9am");              // name-keyed; fire-and-return execution id
await schedules.RunNowAsync("weekday-9am", wait: true);  // synchronous wait variant (returns AgentResult)
await schedules.DeleteAsync("weekday-9am");
await schedules.PreviewNextAsync("0 9 * * MON-FRI", n: 5);
```

`Schedule` is a property-init record-style class. All operations async-first (sync wrappers mirror existing `AgentRuntime` style). `Schedules` accessor on `AgentRuntime` parallels Java.

### 3.6 UI

Two surfaces. Both back onto the same REST endpoints.

#### Agent detail → Schedules tab

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

#### New / edit drawer

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

#### Schedule detail drawer

- Header: name · cron · tz · status · `[Pause/Resume]` `[Run now]` `[Edit]` `[Delete]`
- Tabs:
  - **Executions** — table of past runs (started, duration, status, workflow id → click through)
  - **Definition** — read-only JSON
  - **History** — audit trail (created / paused with reason / edited)

#### Global Schedules list

`Agent` column + filter on `ui/src/pages/scheduler/`. Same row controls. The cross-agent view; the agent-detail tab is a filtered slice.

### 3.7 Validation evidence

- Conductor REST surface — `scheduler/corexx/src/main/java/io/orkes/conductor/scheduler/rest/SchedulerResource.java` (verified all endpoints exist).
- `findAllSchedules(orgId, workflowName)` — `scheduler/core/.../dao/scheduler/SchedulerDAO.java:36`.
- `WorkflowSchedule` model fields — `scheduler/corexx/.../model/WorkflowSchedule.java`.
- conductor-python already has `SchedulerClient` (`save_schedule`, `get_all_schedules(workflow_name=...)`, `delete_schedule`, `pause_schedule`, `resume_schedule`) — agentspan SDKs wrap it.
- agent.name → workflow name — `server/.../AgentService.java:222` (`def.getName()` returned as `agentName`).

### 3.8 Resolved design questions (Phase 1)

1. **Module path** → `conductor.ai.agents.schedule.Schedule`. Ships only what exists today; if/when Webhook/Event triggers land, they get their own modules and we revisit a `triggers/` umbrella.
2. **`run_now` blocking** → the default returns the execution id immediately. Agents can run for minutes; blocking is the wrong default for a UI button or scripted invocation. **`run_now` is now name-keyed in all four SDKs, and all four expose an opt-in synchronous wait variant**: Python `run_now(name, wait=True)`, TS `runNow(name, {wait})` / `runNowAndWait(name)`, Java `runNow(name)` / `runNowAndWait(name)`, C# `RunNowAsync(name)` / `RunNowAsync(name, wait: true)`. The wait variant returns an `AgentResult` **uniformly across all four SDKs** — no return-type divergence.
3. **`nextRunTime` when paused-on-create** → verified against Conductor source (`scheduler/core/.../SchedulerService.java:732`): `setNextRunTimeInEpoch(...)` is called unconditionally on save; the `isPaused()` check only gates the queue-message push that triggers the fire. The UI's "Next: ..." column is reliable for paused schedules. No SDK or UI accommodation needed.
4. **Schedule name scoping** → unique **per agent**, not globally. The SDK auto-prefixes the wire name to `{agent.name}-{name}` at `deploy()` time so users write `Schedule(name="daily")` ergonomically while Conductor's org-wide uniqueness is satisfied. The prefixed name is the canonical identifier returned by `list()`/`get()` and accepted by `pause`/`resume`/`delete`/`run_now`. The `ScheduleInfo` dataclass exposes both `name` (prefixed, wire) and `short_name` (the user's original) for display.

## 4. Roadmap — Event / Webhook / File / Stream Triggers

The remaining four trigger types extend the same `deploy(agent, triggers=[...])` umbrella. Server-side triggers (Event, Webhook) are fully managed by the orchestration server; local source watchers (FileWatch, StreamWatch) require a local daemon.

### 4.1 Deployment architecture

#### Server-side triggers (Event, Webhook)

Fully managed by the orchestration server. No local process needed beyond initial registration.

```
Developer                    Orchestration Server
    │                              │
    │  deploy(agent, triggers)     │
    │─────────────────────────────►│
    │                              │  1. Register workflow definition
    │                              │  2. Create schedule (cron)
    │                              │  3. Register event handlers
    │                              │  4. Start tool workers
    │  DeploymentHandle            │
    │◄─────────────────────────────│
    │                              │
    │                              │  [cron fires / event arrives]
    │                              │  → Start agent execution
    │                              │  → LLM + tools execute
    │                              │  → Result stored
    │                              │
    │  handle.executions()         │
    │─────────────────────────────►│
    │  [list of past runs]         │
    │◄─────────────────────────────│
```

#### Local source watchers (FileWatch, StreamWatch)

These require a local daemon process that watches the source and triggers the agent.

```
┌─────────────────────────────────┐       ┌───────────────────────┐
│      Local Watcher Process       │       │  Orchestration Server │
│                                  │       │                       │
│  ┌────────────────────────────┐  │       │                       │
│  │ FileWatch Thread           │  │       │                       │
│  │  tail -F /var/log/app.log  │──┼─match─┼──► start_workflow()   │
│  │  pattern: "ERROR"          │  │       │      prompt = "..."   │
│  │  debounce: 30s             │  │       │      → Agent runs     │
│  └────────────────────────────┘  │       │                       │
│                                  │       │                       │
│  ┌────────────────────────────┐  │       │                       │
│  │ StreamWatch Thread         │  │       │                       │
│  │  Kafka consumer: alerts    │──┼──msg──┼──► start_workflow()   │
│  │  filter: level == 'error'  │  │       │      prompt = "..."   │
│  └────────────────────────────┘  │       │                       │
│                                  │       │                       │
│  ┌────────────────────────────┐  │       │                       │
│  │ Tool Workers               │  │       │                       │
│  │  Serving @tool functions   │◄─┼───────┼── poll for tasks      │
│  └────────────────────────────┘  │       │                       │
│                                  │       │                       │
│  runtime.wait() ← blocks here   │       │                       │
└─────────────────────────────────┘       └───────────────────────┘
```

The local process runs:
1. **Watcher threads** — one per FileWatch/StreamWatch trigger
2. **Tool workers** — serving the agent's @tool functions to the orchestration server
3. **Main thread** — `runtime.wait()` blocks, keeping everything alive

#### How you install and run this

**Scenario: "Tail a log file and trigger an agent on errors"**

```bash
# 1. Install
pip install conductor-agent-sdk   # or: npm install @conductoross/conductor-agent-sdk

# 2. Write the sentinel (sentinel.py / sentinel.ts)
#    Define agent + tools + FileWatch trigger

# 3. Run
python sentinel.py             # foreground, for dev/testing
# or
conductor-agent deploy sentinel.py    # daemonize (future CLI)
# or
docker run -v /var/log:/var/log:ro my-sentinel   # containerized
# or
systemctl start conductor-sentinel@log_monitor   # systemd service
```

**What `runtime.wait()` does:** blocks the main thread, keeps file watchers alive, keeps tool workers polling, handles graceful shutdown on SIGTERM/SIGINT, and logs trigger events and agent executions.

#### Multi-instance / HA deployment

| Trigger Type | Multi-Instance Behavior |
|---|---|
| **Schedule** | Orchestration server ensures exactly-once execution. Safe to run multiple instances. |
| **Event** | Event handler registered once. Server routes to one execution instance. |
| **Webhook** | Server-side. Single handler. |
| **FileWatch** | Local — each instance watches independently. Needs **distributed lock** or **leader election** to prevent duplicate triggers. |
| **StreamWatch** | Use consumer groups (Kafka) or competing consumers (SQS) for natural dedup. |

### 4.2 Lifecycle management (multi-trigger)

When an agent is deployed with non-schedule triggers, a handle is returned for ongoing management:

```
DeploymentHandle:
  name: string                   # agent name
  registered_name: string        # compiled workflow name
  triggers: Trigger[]            # active triggers
  status: "running" | "paused" | "stopped"

  pause()                        # pause all triggers
  resume()                       # resume triggers
  undeploy()                     # stop + remove all triggers + cleanup

  executions(limit=10)           # list recent agent runs
  last_execution()               # most recent run result
```

Observability: deployed sentinels expose execution history (when it ran, what triggered it, outcome), trigger status (active? last fire? error count?), metrics (runs/hour, avg duration, tokens, tool calls), and structured logs. Access via API (`handle.executions()`, `handle.status`), CLI (`conductor-agent status`, `conductor-agent logs <name>`), and the Web UI (Conductor's workflow execution UI).

### 4.3 Concrete examples

#### Log Sentinel (FileWatch + Schedule)

```
Agent:
  name: log_sentinel
  model: openai/gpt-4o
  tools: [read_log_context, create_jira_ticket, send_slack_alert]
  instructions: |
    You are a production log sentinel. When triggered with log errors:
    1. Read surrounding context to understand the error
    2. Assess severity (transient vs. real bug vs. critical outage)
    3. Transient: ignore. Bug: create JIRA ticket. Critical: Slack alert + ticket.

Triggers:
  - FileWatch:
      path: /var/log/myapp/error.log
      pattern: (ERROR|CRITICAL|FATAL)
      debounce: 30
      prompt: |
        Log error detected in {filepath} at line {line_number}:

        {matched_lines}

        Analyze this error, check context, and take appropriate action.

  - Schedule:
      cron: "0 9 * * 1"   # Monday 9am
      prompt: Compile a weekly summary of all errors from the past week.
```

#### PR Review Sentinel (WebhookTrigger + Schedule)

```
Agent:
  name: pr_reviewer
  model: anthropic/claude-sonnet
  tools: [list_open_prs, fetch_pr_diff, post_review_comment]
  instructions: |
    Review pull requests for code quality, bugs, and security issues.
    Post constructive review comments. Approve clean PRs.

Triggers:
  - WebhookTrigger:
      matches: {action: "opened", pull_request: {base: {ref: "main"}}}
      prompt: "New PR to main: ${webhook.payload.pull_request.title}. Review it."

  - Schedule:
      cron: "*/30 * * * *"
      prompt: "Check for any unreviewed PRs in the last 30 minutes."
```

#### Incident Responder (EventTrigger)

```
Agent:
  name: incident_responder
  model: openai/gpt-4o
  tools: [get_metrics, get_logs, restart_service, scale_replicas, notify_oncall]
  instructions: |
    You are the first responder for production incidents.
    1. Gather metrics and logs to understand the issue
    2. If it's a known pattern (OOM, connection pool), apply the fix
    3. If unknown, gather diagnostics and escalate to on-call

Triggers:
  - EventTrigger:
      event: pagerduty:incident
      condition: "event.severity == 'critical'"
      prompt: |
        CRITICAL INCIDENT: ${event.title}
        Service: ${event.service}
        Description: ${event.description}
        Triggered at: ${event.created_at}

  - EventTrigger:
      event: prometheus:alert
      condition: "event.labels.severity == 'warning'"
      prompt: |
        Warning alert: ${event.labels.alertname}
        ${event.annotations.description}
```

#### Omnipresent Ops Agent (all trigger types)

The most ambitious pattern — a single agent combining every trigger type:

```
Agent:
  name: ops_sentinel
  model: openai/gpt-4o
  tools: [
    check_health, get_metrics, query_logs,
    restart_pod, scale_service,
    create_ticket, send_alert,
    run_db_query, check_cert_expiry
  ]
  instructions: |
    You are the AI ops team member. You have multiple responsibilities:
    - Health checks (scheduled)
    - Error triage (log watching)
    - Alert response (event-driven)
    - Deployment verification (webhook-driven)
    Fix what you can autonomously. Escalate what you can't.

Triggers:
  - Schedule:
      cron: "*/5 * * * *"
      prompt: "Run health checks on all production services."

  - Schedule:
      cron: "0 8 * * *"
      prompt: "Morning report: summarize overnight incidents, current system health, upcoming cert expirations."

  - FileWatch:
      path: /var/log/k8s/*.log
      pattern: "OOMKilled|CrashLoopBackOff|ImagePullBackOff"
      prompt: "K8s issue detected:\n\n{matched_lines}\n\nDiagnose and fix if possible."

  - EventTrigger:
      event: prometheus:alert
      prompt: "Alert: ${event.labels.alertname}\n${event.annotations.description}"

  - WebhookTrigger:
      matches: {source: "github", action: "deployment"}
      prompt: "Deployment to ${webhook.payload.environment}: verify health."
```

### 4.4 Roadmap phases

**Phase 2 — Event & Webhook Triggers.** `EventTrigger` class → registers event handler with the orchestration server. `WebhookTrigger` class → registers webhook handler. Prompt template interpolation with event/webhook payload. *Example*: incident responder triggered by PagerDuty events.

**Phase 3 — Local File Watching.** `FileWatch` trigger class. Local file tailing engine (efficient, handles rotation and glob patterns). Pattern matching + debounce. On match → `runtime.start(agent, prompt=rendered_template)`. *Example*: log sentinel watching error.log.

**Phase 4 — Stream Watching.** `StreamWatch` trigger class. Connector interface for Kafka, Redis Streams, SQS, etc. Consumer-group support for multi-instance dedup. *Example*: data-pipeline monitor on a Kafka topic.

**Phase 5 — CLI & Observability.** `conductor-agent deploy <file>` (daemonize), `status` (list deployed sentinels), `logs <name>` (stream execution logs), `pause/resume/undeploy <name>`. Dashboard integration with execution history.

**Phase 6 — Advanced Patterns.** Cost controls (max runs/hour, spend threshold, auto-pause); concurrency policy (skip-if-running / queue / parallel); state across runs (automatic memory injection for scheduled agents — see [`stateful-agents.md`](stateful-agents.md)); multi-instance coordination (distributed locking for FileWatch in HA); chained sentinels (one sentinel's output triggers another).

### 4.5 Open design questions

1. **Prompt templating syntax**: Server-side triggers naturally use orchestration engine expressions (`${event.field}`). Local triggers resolve before the workflow starts (`{matched_lines}`). Unify, or keep the natural split?
2. **Concurrency on schedule overlap**: If a cron fires while the previous run is still executing — skip, queue, or parallel? Default recommendation: **skip-if-running** to prevent agent pile-up and runaway costs. (Schedule overlap is `allow` in shipped Phase 1; this is the Phase 6 agentspan-layer feature.)
3. **State persistence across scheduled runs**: Should sentinel agents automatically get conversation memory? Recommendation: **opt-in** via the memory parameter — memory adds cost and complexity.
4. **FileWatch reliability**: The local watcher process is a single point of failure. Options: (a) watchdog/health checks, (b) systemd auto-restart, (c) heartbeat to the orchestration server that alerts on missed heartbeats.
5. **Cost guardrails**: Sentinel agents can run thousands of times per day. Should triggers support max executions per hour, a monthly spend cap, auto-pause on threshold?
6. **Trigger composition**: Can triggers have dependencies? E.g., "only trigger on FileWatch if the last Schedule run found issues." Adds complexity — defer to Phase 6.
7. **Multi-SDK consistency**: Trigger classes and deployment API should be identical in structure across Python, TypeScript, Java, and C# SDKs, differing only in language idiom — as already achieved for Phase 1 scheduling.
