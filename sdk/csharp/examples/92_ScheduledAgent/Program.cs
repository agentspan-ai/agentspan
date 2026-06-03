// Copyright (c) 2025 Agentspan
// Licensed under the MIT License.

// Scheduled Agent — deploy an agent on a cron schedule.
//
// Demonstrates the declarative schedule API: attach named cron schedules to
// an agent at deploy time, then use the Schedules accessor to list, pause,
// resume, run-now, preview next fires, and purge on cleanup.
//
// Usage:
//   AGENTSPAN_SERVER_URL=http://localhost:6767/api \
//   AGENTSPAN_LLM_MODEL=openai/gpt-4o-mini \
//   dotnet run --project sdk/csharp/examples/92_ScheduledAgent/Example92ScheduledAgent.csproj

using Agentspan;
using Agentspan.Examples;
using Agentspan.Scheduling;

var agent = new Agent("eng_digest_92")
{
    Model        = Settings.LlmModel,
    Instructions =
        "You are a concise engineering digest writer. " +
        "Summarise recent activity for the channel provided in your input " +
        "and return a short markdown bullet list (max 5 items).",
};

await using var runtime = new AgentRuntime();

// 1. Deploy with two named schedules.
await runtime.DeployAsync(agent, new[]
{
    new Schedule
    {
        Name        = "weekday-9am",
        Cron        = "0 0 9 * * MON-FRI",
        Timezone    = "America/Los_Angeles",
        Input       = new Dictionary<string, object?> { ["channel"] = "#eng" },
        Description = "Weekday morning digest",
    },
    new Schedule
    {
        Name        = "friday-5pm",
        Cron        = "0 0 17 * * FRI",
        Timezone    = "America/Los_Angeles",
        Input       = new Dictionary<string, object?> { ["channel"] = "#all-hands", ["mode"] = "weekly" },
        Description = "Weekly all-hands digest",
    },
});
Console.WriteLine($"✓ Deployed '{agent.Name}' with 2 schedules");

// 2. List schedules for this agent.
var infos = await runtime.Schedules.ListAsync(agent.Name);
Console.WriteLine($"\nSchedules ({infos.Count}):");
foreach (var s in infos)
    Console.WriteLine($"  {s.Name}  {s.Cron}  [{(s.Paused ? "PAUSED" : "active")}]");

if (infos.Count < 2)
{
    Console.Error.WriteLine("Expected 2 schedules; aborting.");
    return;
}

var weekdayName = infos.First(s => s.ShortName == "weekday-9am").Name;
var fridayName  = infos.First(s => s.ShortName == "friday-5pm").Name;

// 3. Pause the weekday schedule.
await runtime.Schedules.PauseAsync(weekdayName, reason: "rate-limit cooldown demo");
var afterPause = await runtime.Schedules.GetAsync(weekdayName);
Console.WriteLine($"\n✓ Paused '{weekdayName}': Paused={afterPause.Paused}, Reason={afterPause.PausedReason}");

// 4. Resume it.
await runtime.Schedules.ResumeAsync(weekdayName);
var afterResume = await runtime.Schedules.GetAsync(weekdayName);
Console.WriteLine($"✓ Resumed '{weekdayName}': Paused={afterResume.Paused}");

// 5. Ad-hoc run of the friday schedule.
var execId = await runtime.Schedules.RunNowAsync(fridayName);
Console.WriteLine($"\n✓ RunNow '{fridayName}' → execution id: {execId}");

// 6. Preview next 5 fire times for the weekday cron.
var nextFires = await runtime.Schedules.PreviewNextAsync("0 0 9 * * MON-FRI", n: 5);
Console.WriteLine("\nNext 5 fires for weekday-9am:");
for (int i = 0; i < nextFires.Count; i++)
    Console.WriteLine($"  {i + 1}. {DateTimeOffset.FromUnixTimeMilliseconds(nextFires[i]):u}");

// 7. Cleanup: redeploy with empty list to purge all schedules.
await runtime.DeployAsync(agent, Array.Empty<Schedule>());
Console.WriteLine($"\n✓ Purged all schedules for '{agent.Name}'");
