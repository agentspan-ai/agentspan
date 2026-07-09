# Scheduling

Run agents on a cron schedule. Schedules are stored in Conductor and survive server restarts — no cron daemon or external scheduler needed.

## Deploy an agent with a schedule

```java
import org.conductoross.conductor.ai.schedule.Schedule;

Agent reportAgent = Agent.builder()
    .name("daily_report")
    .model("anthropic/claude-sonnet-4-6")
    .instructions("Generate a daily sales summary.")
    .build();

Schedule daily = Schedule.builder()
    .name("daily")
    .cron("0 9 * * *")              // 9 AM every day
    .timezone("America/New_York")
    .build();

try (AgentRuntime runtime = new AgentRuntime()) {
    runtime.deploy(reportAgent, List.of(daily));
}
```

## Schedule with custom input

Pass a fixed prompt or parameters to the scheduled run:

```java
Schedule weeklyDigest = Schedule.builder()
    .name("weekly")
    .cron("0 8 * * MON")
    .input(Map.of("report_type", "weekly", "include_charts", true))
    .description("Monday morning executive digest")
    .build();
```

## Manage schedules

```java
Schedules schedules = runtime.schedules();

// List all schedules for an agent
List<ScheduleInfo> all = schedules.list("daily_report");

// Get a specific schedule by its wire name (agent-name-schedule-name)
ScheduleInfo info = schedules.get("daily_report-daily");

// Trigger immediately (ignores cron timing) — runNow takes the ScheduleInfo
String executionId = schedules.runNow(info);

// Pause and resume (by wire name)
schedules.pause("daily_report-daily");
schedules.resume("daily_report-daily");

// Delete (by wire name)
schedules.delete("daily_report-daily");

// Preview the next N fire times for a cron expression
List<Long> next = schedules.previewNext("0 9 * * *", 5);   // epoch millis
```

## Schedule.builder() options

| Method | Type | Default | Description |
|---|---|---|---|
| `name(String)` | `String` | **required** | Unique name within the agent. |
| `cron(String)` | `String` | **required** | Standard 5-field cron expression. |
| `timezone(String)` | `String` | `"UTC"` | IANA timezone (e.g. `"Europe/London"`). |
| `input(Map)` | `Map<String,Object>` | `{}` | Fixed input passed to the agent on each run. |
| `description(String)` | `String` | `null` | Human-readable description. |
| `paused(boolean)` | `boolean` | `false` | Create in paused state. |
| `catchup(boolean)` | `boolean` | `false` | Run missed executions after a server downtime. |
| `startAt(long)` | `long` | `null` | Epoch milliseconds — schedule not active before this time. |
| `endAt(long)` | `long` | `null` | Epoch milliseconds — schedule disabled after this time. |

## Cron syntax

Standard 5-field: `minute hour day-of-month month day-of-week`

```
0 9 * * *         every day at 9:00 AM
0 */6 * * *       every 6 hours
0 8 * * MON-FRI   weekdays at 8 AM
30 17 1 * *       1st of every month at 5:30 PM
```
