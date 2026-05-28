// Copyright (c) 2026 Agentspan
// Licensed under the MIT License.

using System.Net.Http;
using System.Net.Http.Json;
using System.Text;
using System.Text.Json.Nodes;
using Agentspan.Scheduling;
using Xunit;

namespace AgentspanE2eTests;

/// <summary>
/// Unit + integration tests for the C# scheduling SDK.
/// Integration tests skipped unless the agentspan-runtime scheduler is reachable.
/// </summary>
public class ScheduleUnitTests
{
    [Fact]
    public void Minimal()
    {
        var s = new Schedule { Name = "daily", Cron = "0 0 9 * * ?" };
        Assert.Equal("daily", s.Name);
        Assert.Equal("UTC", s.Timezone);
        Assert.False(s.Catchup);
        Assert.False(s.Paused);
    }

    [Fact]
    public void RejectsEmptyName()
    {
        var s = new Schedule { Name = "", Cron = "* * * * * ?" };
        Assert.Throws<ScheduleException>(() => s.Validate());
    }

    [Fact]
    public void RejectsInvertedWindow()
    {
        var s = new Schedule { Name = "x", Cron = "* * * * * ?", StartAt = 2000, EndAt = 1000 };
        Assert.Throws<ScheduleException>(() => s.Validate());
    }

    [Fact]
    public void PrefixRoundtrips()
    {
        var wire = Schedules.Prefix("digest", "daily");
        Assert.Equal("digest-daily", wire);
        Assert.Equal("daily", Schedules.Unprefix("digest", wire));
    }

    [Fact]
    public void UnprefixNoMatchReturnsInput()
    {
        Assert.Equal("unrelated", Schedules.Unprefix("agent", "unrelated"));
    }

    [Fact]
    public void DuplicateNameRaises()
    {
        var sched = new[]
        {
            new Schedule { Name = "a", Cron = "* * * * * ?" },
            new Schedule { Name = "a", Cron = "0 0 9 * * ?" },
        };
        Assert.Throws<ScheduleNameConflict>(() => Schedules.CheckUniqueNames(sched));
    }

    [Fact]
    public void ToSaveRequestMinimal()
    {
        var s = new Schedule { Name = "daily", Cron = "0 0 9 * * ?" };
        var req = Schedules.ToSaveRequest(s, "digest");
        Assert.Equal("digest-daily", req["name"]!.GetValue<string>());
        Assert.Equal("0 0 9 * * ?", req["cronExpression"]!.GetValue<string>());
        Assert.Equal("UTC", req["zoneId"]!.GetValue<string>());
        var swr = req["startWorkflowRequest"]!.AsObject();
        Assert.Equal("digest", swr["name"]!.GetValue<string>());
    }

    [Fact]
    public void FromWorkflowScheduleBasic()
    {
        var ws = new JsonObject
        {
            ["name"] = "digest-daily",
            ["cronExpression"] = "0 0 9 * * ?",
            ["zoneId"] = "UTC",
            ["paused"] = false,
            ["startWorkflowRequest"] = new JsonObject
            {
                ["name"] = "digest",
                ["input"] = new JsonObject { ["c"] = "#eng" },
            },
            ["createTime"] = 111L,
            ["createdBy"] = "alice",
        };
        var info = Schedules.FromWorkflowSchedule(ws, "digest");
        Assert.Equal("digest-daily", info.Name);
        Assert.Equal("daily", info.ShortName);
        Assert.Equal("digest", info.Agent);
        Assert.Equal("0 0 9 * * ?", info.Cron);
        Assert.False(info.Paused);
        Assert.Equal(111L, info.CreateTime);
        Assert.Equal("alice", info.CreatedBy);
        Assert.Equal("#eng", info.Input["c"]);
    }
}

public class ScheduleIntegrationTests
{
    private const string ServerUrl = "http://localhost:6767";

    private static bool SchedulerAvailable()
    {
        try
        {
            using var http = new HttpClient { Timeout = TimeSpan.FromSeconds(3) };
            var r = http.GetAsync($"{ServerUrl}/api/scheduler/schedules").GetAwaiter().GetResult();
            return r.IsSuccessStatusCode;
        }
        catch { return false; }
    }

    private static readonly bool s_schedulerAvailable = SchedulerAvailable();

    private async Task<(Schedules schedules, string agentName, HttpClient http)> SetupAsync()
    {
        var agentName = $"e2e_cs_sched_noop_{Guid.NewGuid().ToString("N").Substring(0, 8)}";

        var workflowDef = new JsonObject
        {
            ["name"] = agentName, ["version"] = 1, ["schemaVersion"] = 2,
            ["ownerEmail"] = "e2e@agentspan.test",
            ["timeoutSeconds"] = 60, ["timeoutPolicy"] = "TIME_OUT_WF",
            ["tasks"] = new JsonArray(new JsonObject
            {
                ["name"] = "noop_terminate",
                ["taskReferenceName"] = "noop_terminate_ref",
                ["type"] = "TERMINATE",
                ["inputParameters"] = new JsonObject
                {
                    ["terminationStatus"] = "COMPLETED",
                    ["workflowOutput"] = new JsonObject { ["ok"] = true },
                },
            }),
        };

        var http = new HttpClient { Timeout = TimeSpan.FromSeconds(15) };
        var resp = await http.PostAsync(
            $"{ServerUrl}/api/metadata/workflow",
            new StringContent(workflowDef.ToJsonString(), Encoding.UTF8, "application/json"));
        resp.EnsureSuccessStatusCode();

        // Schedules uses the same /api prefix that Python/TS do — match by using full base.
        var schedHttp = new HttpClient { Timeout = TimeSpan.FromSeconds(15) };
        var schedules = new Schedules(schedHttp, $"{ServerUrl}/api");
        return (schedules, agentName, http);
    }

    private async Task TeardownAsync(Schedules schedules, string agentName, HttpClient http)
    {
        try { await schedules.ReconcileAsync(agentName, new List<Schedule>()); } catch { }
        try { await http.DeleteAsync($"{ServerUrl}/api/metadata/workflow/{agentName}/1"); } catch { }
        http.Dispose();
    }

    [SkippableFact]
    public async Task ReconcileCreatesSchedules()
    {
        Skip.IfNot(s_schedulerAvailable, "Scheduler not reachable");
        var (sched, agent, http) = await SetupAsync();
        try
        {
            await sched.ReconcileAsync(agent, new[]
            {
                new Schedule { Name = "daily", Cron = "0 0 9 * * ?", Input = new Dictionary<string, object?> { ["k"] = 1 } },
                new Schedule { Name = "weekly", Cron = "0 0 9 * * MON" },
            });
            var infos = await sched.ListAsync(agent);
            Assert.Equal(2, infos.Count);
            var daily = infos.First(i => i.ShortName == "daily");
            Assert.Equal($"{agent}-daily", daily.Name);
            Assert.Equal("0 0 9 * * ?", daily.Cron);
            Assert.Equal(agent, daily.Agent);
        }
        finally { await TeardownAsync(sched, agent, http); }
    }

    [SkippableFact]
    public async Task UpsertAndPrune()
    {
        Skip.IfNot(s_schedulerAvailable, "Scheduler not reachable");
        var (sched, agent, http) = await SetupAsync();
        try
        {
            await sched.ReconcileAsync(agent, new[]
            {
                new Schedule { Name = "a", Cron = "0 0 1 * * ?" },
                new Schedule { Name = "b", Cron = "0 0 2 * * ?" },
            });
            await sched.ReconcileAsync(agent, new[]
            {
                new Schedule { Name = "a", Cron = "0 0 9 * * ?" },
                new Schedule { Name = "c", Cron = "0 0 17 * * ?" },
            });
            var infos = (await sched.ListAsync(agent)).ToDictionary(i => i.ShortName);
            Assert.Equal(new[] { "a", "c" }.ToHashSet(), infos.Keys.ToHashSet());
            Assert.Equal("0 0 9 * * ?", infos["a"].Cron);
        }
        finally { await TeardownAsync(sched, agent, http); }
    }

    [SkippableFact]
    public async Task PauseResume()
    {
        Skip.IfNot(s_schedulerAvailable, "Scheduler not reachable");
        var (sched, agent, http) = await SetupAsync();
        try
        {
            await sched.ReconcileAsync(agent, new[]
            {
                new Schedule { Name = "p", Cron = "0 0 9 * * ?" },
            });
            var wire = $"{agent}-p";
            Assert.False((await sched.GetAsync(wire)).Paused);
            await sched.PauseAsync(wire, "rate limit");
            Assert.True((await sched.GetAsync(wire)).Paused);
            await sched.ResumeAsync(wire);
            Assert.False((await sched.GetAsync(wire)).Paused);
        }
        finally { await TeardownAsync(sched, agent, http); }
    }

    [SkippableFact]
    public async Task EmptyListPurges()
    {
        Skip.IfNot(s_schedulerAvailable, "Scheduler not reachable");
        var (sched, agent, http) = await SetupAsync();
        try
        {
            await sched.ReconcileAsync(agent, new[]
            {
                new Schedule { Name = "x", Cron = "0 * * * * ?" },
            });
            Assert.Single(await sched.ListAsync(agent));
            await sched.ReconcileAsync(agent, new List<Schedule>());
            Assert.Empty(await sched.ListAsync(agent));
        }
        finally { await TeardownAsync(sched, agent, http); }
    }

    [SkippableFact]
    public async Task NullPreserves()
    {
        Skip.IfNot(s_schedulerAvailable, "Scheduler not reachable");
        var (sched, agent, http) = await SetupAsync();
        try
        {
            await sched.ReconcileAsync(agent, new[]
            {
                new Schedule { Name = "x", Cron = "0 * * * * ?" },
            });
            await sched.ReconcileAsync(agent, null);
            Assert.Single(await sched.ListAsync(agent));
        }
        finally { await TeardownAsync(sched, agent, http); }
    }

    [SkippableFact]
    public async Task DeleteThenGetRaises()
    {
        Skip.IfNot(s_schedulerAvailable, "Scheduler not reachable");
        var (sched, agent, http) = await SetupAsync();
        try
        {
            await sched.ReconcileAsync(agent, new[]
            {
                new Schedule { Name = "g", Cron = "0 * * * * ?" },
            });
            var wire = $"{agent}-g";
            await sched.DeleteAsync(wire);
            await Assert.ThrowsAsync<ScheduleNotFound>(() => sched.GetAsync(wire));
        }
        finally { await TeardownAsync(sched, agent, http); }
    }

    [SkippableFact]
    public async Task PreviewNext()
    {
        Skip.IfNot(s_schedulerAvailable, "Scheduler not reachable");
        var (sched, agent, http) = await SetupAsync();
        try
        {
            var times = await sched.PreviewNextAsync("0 0 9 * * ?", 3);
            Assert.Equal(3, times.Count);
            for (int i = 1; i < times.Count; i++) Assert.True(times[i] > times[i - 1]);
        }
        finally { await TeardownAsync(sched, agent, http); }
    }
}
