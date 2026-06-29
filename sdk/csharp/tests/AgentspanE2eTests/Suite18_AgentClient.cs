// Copyright (c) 2025 Agentspan
// Licensed under the MIT License.

// Suite 18 — AgentClient: the renamed control-plane client (formerly
// AgentHttpClient) must expose run + schedule for agents.
//
// run = control-plane only (start + poll to result; no local tool workers), so
// these use an LLM-only agent. Schedule = deploy + cron lifecycle.
//
// Deterministic: assert on result.Status / schedule list membership — never on
// LLM output text. CLAUDE.md: no LLM for validation; fail-first validated.

using System.Threading;
using Xunit;
using Conductor.AI.Examples;
using Conductor.AI.Scheduling;

namespace Conductor.AI.E2eTests;

[Collection("E2e")]
public sealed class Suite18_AgentClient
{
    private readonly E2eFixture _fixture;
    public Suite18_AgentClient(E2eFixture fixture) => _fixture = fixture;

    // ── 18.1  AgentClient.RunAsync runs an LLM-only agent (no workers) ────

    [SkippableFact]
    public async Task AgentClient_RunAsync_CompletesControlPlaneOnly()
    {
        _fixture.RequireServer();

        var agent = new Agent("s18_client_run")
        {
            Model        = Settings.LlmModel,
            Instructions = "Reply with a single short word.",
            MaxTurns     = 2,
        };

        // Use the AgentClient directly (via the runtime's Client accessor) — no
        // AgentRuntime worker orchestration involved.
        await using var runtime = new AgentRuntime();
        var result = await runtime.Client.RunAsync(agent, "Say hi.");

        Assert.Equal(Status.Completed, result.Status);
        Assert.False(string.IsNullOrEmpty(result.ExecutionId));
    }

    // ── 18.2  AgentClient schedules agents (deploy + cron lifecycle) ──────

    [SkippableFact]
    public async Task AgentClient_ScheduleAsync_CreatesListsAndPurges()
    {
        _fixture.RequireServer();

        var agent = new Agent("s18_client_sched")
        {
            Model        = Settings.LlmModel,
            Instructions = "Summarize the input in one line.",
        };

        await using var runtime = new AgentRuntime();
        var client = runtime.Client;

        var schedule = new Schedule
        {
            Name     = "s18-weekday-9am",
            Cron     = "0 0 9 * * MON-FRI",
            Timezone = "America/Los_Angeles",
        };

        try
        {
            // Schedule via AgentClient (deploy + reconcile).
            await client.ScheduleAsync(agent, new[] { schedule });

            var listed = await client.Schedules.ListAsync(agent.Name);
            Assert.Contains(listed, s => s.ShortName == "s18-weekday-9am");

            // Counterfactual: purge via empty reconcile → none remain for this agent.
            await client.ScheduleAsync(agent, Array.Empty<Schedule>());
            var afterPurge = await client.Schedules.ListAsync(agent.Name);
            Assert.DoesNotContain(afterPurge, s => s.ShortName == "s18-weekday-9am");
        }
        finally
        {
            // Best-effort cleanup in case an assertion above threw mid-way.
            try { await client.Schedules.ReconcileAsync(agent.Name, Array.Empty<Schedule>()); }
            catch { /* ignore */ }
        }
    }

    // ── 18.3  Runtime.Schedules and Client.Schedules are the same surface ─

    [Fact]
    public void Runtime_DelegatesScheduleSurfaceToClient()
    {
        using var runtime = new AgentRuntime();
        Assert.Same(runtime.Schedules, runtime.Client.Schedules);
    }
}
