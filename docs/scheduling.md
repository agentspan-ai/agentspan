# Agent Scheduling

Run any agent on a cron schedule. The agentspan SDK lets you attach one or
more crons to a deployed agent in a single declarative call; the runtime's
scheduler fires the agent on cadence and you watch the executions roll in.

This page covers the user-facing API. For the design rationale see
[`docs/design/scheduling.md`](design/scheduling.md). For the implementation
plan see [`docs/design/plans/2026-05-27-agent-scheduling.md`](design/plans/2026-05-27-agent-scheduling.md).

## What you get

- **One agent, many schedules.** Each schedule is a named cron expression
  with its own input, timezone, and pause/resume state.
- **Declarative deploy.** `deploy(agent, schedules=[...])` reconciles whatever
  you pass against what's on the server — added, modified, removed.
- **Pause/resume/run-now** via a wire-name-keyed module API.
- **Tri-state semantics**: omit `schedules` → leave alone. Pass `[]` → purge.
  Pass `[…]` → upsert listed, prune the rest.
- **Identical surface in all four SDKs** (Python, TypeScript, Java, C#).

## Requirements

- agentspan-runtime ≥ 0.x with the scheduler module enabled
  (`conductor.scheduler.enabled=true`, on by default).
- Cron expressions use the **6-field Quartz format** (`sec min hour day mon dow`)
  that Conductor's scheduler expects, e.g. `0 0 9 * * ?` for "every day at 9am".

## Quickstart

### Python

```python
from agentspan.agents import Agent, deploy, schedules
from agentspan.agents.schedule import Schedule

agent = Agent(name="daily_digest", model="openai/gpt-4o-mini",
              instructions="Summarize today's eng activity.")

deploy(
    agent,
    schedules=[
        Schedule(name="weekday-9am",
                 cron="0 0 9 * * MON-FRI",
                 timezone="America/Los_Angeles",
                 input={"channel": "#eng"}),
        Schedule(name="friday-5pm",
                 cron="0 0 17 * * FRI",
                 input={"channel": "#all-hands", "mode": "weekly"}),
    ],
)

# Lifecycle (key by wire name returned from list())
infos = schedules.list(agent="daily_digest")
schedules.pause("daily_digest-weekday-9am", reason="rate limit cooldown")
schedules.resume("daily_digest-weekday-9am")
schedules.delete("daily_digest-weekday-9am")

# Fire ad-hoc; returns execution id immediately.
exec_id = schedules.run_now("daily_digest-friday-5pm")

# Preview cron fire times in the UI.
next_times = schedules.preview_next("0 0 9 * * MON-FRI", n=5)
```

A full working example is in `sdk/python/examples/hello_world_agent_schedule.py`.

### TypeScript

```ts
import {
  Agent, AgentRuntime, Schedule, schedules,
} from "@agentspan-ai/sdk";

const agent = new Agent({
  name: "dailyDigest",
  model: "openai/gpt-4o-mini",
  instructions: "Summarize today's eng activity.",
});

await using const runtime = new AgentRuntime();
await runtime.deploy(agent, {
  schedules: [
    new Schedule({
      name: "weekday-9am",
      cron: "0 0 9 * * MON-FRI",
      timezone: "America/Los_Angeles",
      input: { channel: "#eng" },
    }),
    new Schedule({
      name: "friday-5pm",
      cron: "0 0 17 * * FRI",
      input: { channel: "#all-hands", mode: "weekly" },
    }),
  ],
});

await schedules.list({ agent: "dailyDigest" });
await schedules.pause("dailyDigest-weekday-9am", { reason: "rate limit cooldown" });
await schedules.resume("dailyDigest-weekday-9am");
await schedules.delete("dailyDigest-weekday-9am");
const execId = await schedules.runNow("dailyDigest-friday-5pm");
const nextTimes = await schedules.previewNext("0 0 9 * * MON-FRI", { n: 5 });
```

### Java

```java
import ai.agentspan.Agent;
import ai.agentspan.AgentRuntime;
import ai.agentspan.schedule.Schedule;

Agent agent = Agent.builder()
        .name("daily_digest")
        .model("openai/gpt-4o-mini")
        .instructions("Summarize today's eng activity.")
        .build();

try (AgentRuntime runtime = new AgentRuntime()) {
    runtime.deploy(agent, List.of(
            Schedule.builder()
                    .name("weekday-9am")
                    .cron("0 0 9 * * MON-FRI")
                    .timezone("America/Los_Angeles")
                    .input(Map.of("channel", "#eng"))
                    .build(),
            Schedule.builder()
                    .name("friday-5pm")
                    .cron("0 0 17 * * FRI")
                    .input(Map.of("channel", "#all-hands", "mode", "weekly"))
                    .build()
    ));

    runtime.schedules().list("daily_digest");
    runtime.schedules().pause("daily_digest-weekday-9am", "rate limit cooldown");
    runtime.schedules().resume("daily_digest-weekday-9am");
    String execId = runtime.schedules().runNow(runtime.schedules().get("daily_digest-friday-5pm"));
    List<Long> nextTimes = runtime.schedules().previewNext("0 0 9 * * MON-FRI", 5);
}
```

### C#

```csharp
using Agentspan;
using Agentspan.Scheduling;

var agent = new Agent
{
    Name = "daily_digest",
    Model = "openai/gpt-4o-mini",
    Instructions = "Summarize today's eng activity.",
};

await using var runtime = new AgentRuntime();
await runtime.DeployAsync(agent, new[]
{
    new Schedule
    {
        Name = "weekday-9am",
        Cron = "0 0 9 * * MON-FRI",
        Timezone = "America/Los_Angeles",
        Input = new Dictionary<string, object?> { ["channel"] = "#eng" },
    },
    new Schedule
    {
        Name = "friday-5pm",
        Cron = "0 0 17 * * FRI",
        Input = new Dictionary<string, object?>
        {
            ["channel"] = "#all-hands",
            ["mode"] = "weekly",
        },
    },
});

await runtime.Schedules.ListAsync("daily_digest");
await runtime.Schedules.PauseAsync("daily_digest-weekday-9am", reason: "rate limit cooldown");
await runtime.Schedules.ResumeAsync("daily_digest-weekday-9am");
var info = await runtime.Schedules.GetAsync("daily_digest-friday-5pm");
string execId = await runtime.Schedules.RunNowAsync(info);
var nextTimes = await runtime.Schedules.PreviewNextAsync("0 0 9 * * MON-FRI", n: 5);
```

## Concepts

### Wire-name prefix

You construct schedules with a short, agent-scoped `name` (e.g. `"daily"`).
The SDK transparently prefixes the wire name to `{agent.name}-{name}` so
Conductor's org-wide uniqueness requirement is satisfied. The lifecycle
calls — `pause`, `resume`, `delete`, `get`, `runNow` — take the **wire
name**, which is what `list()` returns. `ScheduleInfo` exposes both:

- `name`: the prefixed wire name (`"daily_digest-daily"`)
- `shortName` (`short_name` in Python): the user's original (`"daily"`)

### Declarative reconciliation on deploy

The `schedules=` argument to `deploy()` is **declarative**:

| Argument | Effect |
|---|---|
| omitted / `None` / `null` | Leave existing schedules untouched. |
| `[]` (empty list) | Delete every schedule for this agent. |
| `[Schedule(...), ...]` | Upsert listed, **prune** any other schedule for this agent. |

Reconciliation is scoped by `startWorkflowRequest.name == agent.name`, so
deploys never touch schedules belonging to other agents.

### Schedule fields

| Field | Required | Default | Notes |
|---|:---:|---|---|
| `name` | ✅ | — | Short identifier, unique within this agent. |
| `cron` | ✅ | — | 6-field Quartz cron (seconds-precision). |
| `timezone` (`zoneId` on the wire) | | `"UTC"` | IANA zone id. |
| `input` | | `{}` | Workflow input passed when the cron fires. |
| `catchup` (`runCatchupScheduleInstances` on the wire) | | `false` | Replay missed fires on resume. |
| `paused` | | `false` | Create in paused state (still computes `nextRunTime`). |
| `startAt`, `endAt` | | `null` | Optional epoch-ms execution window. |
| `description` | | `null` | Human-readable note. |

### Errors

All four SDKs surface the same typed errors:

| Error | When |
|---|---|
| `ScheduleNameConflict` | Two schedules in the same agent share a `name`. Raised before any wire call. |
| `ScheduleNotFound` | `get`/`pause`/`resume`/`delete` on a missing wire name. |
| `InvalidCronExpression` | Server rejects the cron syntax (400 + body mentions "cron"). |
| `ScheduleError` (base) | Other scheduler API failures. |

### `runNow` is non-blocking by default

`runNow` fires the agent once with the schedule's stored input and returns
the workflow execution id **immediately**. To wait for completion, poll the
runtime for the workflow status, or use the language-specific opt-in:

- Python: `schedules.run_now(name, wait=True)` returns the completed workflow.
- TS/Java/C#: poll `runtime`/Conductor workflow status using the returned id.

This default exists because agents can run for minutes; blocking would be
the wrong behavior for buttons, scripts, and serverless contexts.

## UI

The Scheduler page (`/scheduler`) lists all schedules across agents with an
**Agent** column and filterable by query string:

```
/scheduler?workflowName=daily_digest
```

…shows only schedules belonging to `daily_digest`. Open a row to edit it
in the drawer; new schedules get the standard form (cron, timezone, input
JSON, window, *catch-up missed runs on resume*, *start paused*).

## What's not covered yet

These are future-phase items, not blockers:

- **Skip-if-running** / **queue** overlap policies. Today Conductor fires
  every tick — if your agent runs longer than the cadence, executions
  overlap. If that's a concern, gate the agent with a workflow-level
  idempotency check, or set a wider cadence.
- **Event / webhook / file / stream triggers.** Separate trigger types
  under the same `triggers=[...]` umbrella; spec'd but not built.
- **Per-schedule retry / timeout overrides.** Inherits from the agent.
- **Optimistic concurrency on edits.** Conductor uses last-write-wins; no
  ETag is exposed.

## Recipes

### Run a hello-world agent every 5 seconds

```python
from agentspan.agents import Agent, AgentRuntime
from agentspan.agents.schedule import Schedule

agent = Agent(name="hello", model="openai/gpt-4o-mini",
              instructions="Say 'Hello, world!' and the current UTC time.")

with AgentRuntime() as rt:
    rt.deploy(agent, schedules=[
        Schedule(name="every-5s", cron="0/5 * * * * ?"),
    ])
    rt.serve(agent, blocking=False)
    time.sleep(20)  # let the scheduler fire 3–4 times
```

### Schedule the same agent on weekday and weekend cadences

```python
deploy(agent, schedules=[
    Schedule(name="weekday", cron="0 0 9 * * MON-FRI", input={"mode": "daily"}),
    Schedule(name="weekend", cron="0 0 11 * * SAT,SUN", input={"mode": "leisurely"}),
])
```

Each fire gets its own input, its own execution history, and its own
pause/resume state. Pause the weekend cadence without touching weekday.

### Snapshot-style redeploy: replace whatever's there

```python
deploy(agent, schedules=desired_list)  # any missing schedules get pruned
```

### Leave schedules alone on redeploy (CI/CD pattern)

```python
deploy(agent)                          # schedules untouched
# or, explicitly:
deploy(agent, schedules=None)
```

### Purge all schedules for an agent

```python
deploy(agent, schedules=[])
```
