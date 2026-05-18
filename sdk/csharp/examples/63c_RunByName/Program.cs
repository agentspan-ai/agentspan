// Copyright (c) 2025 Agentspan
// Licensed under the MIT License.

// Run by Name — execute a pre-deployed agent via runtime.RunByNameAsync(name, prompt).
//
// This pattern decouples execution from deployment:
//   - CI/CD deploys the workflow definition once (using agent config)
//   - Application code runs it by name (no Agent object needed at runtime)
//   - Workers register separately as long-running services
//
// For agents that use only server-side tools (HTTP, MCP, API) — no worker
// process is needed. This example uses a server-side HTTP tool so both
// the initial run and run-by-name work without local workers.
//
// Requirements:
//   - AGENTSPAN_SERVER_URL=http://localhost:6767/api in environment
//   - AGENTSPAN_LLM_MODEL set in environment

using Agentspan;
using Agentspan.Examples;

// HTTP tool — server-side, no worker process needed
var getCurrentTime = HttpTools.Create(
    name:        "get_world_clock",
    description: "Get the current UTC time from a public world clock API.",
    url:         "http://worldtimeapi.org/api/timezone/UTC",
    headers:     new Dictionary<string, string> { ["Accept"] = "application/json" });

var agent = new Agent("world_clock_agent_63c")
{
    Model        = Settings.LlmModel,
    Tools        = [getCurrentTime],
    Instructions = "You are a time assistant. Use get_world_clock to check the current UTC time.",
};

await using var runtime = new AgentRuntime();

// ── First run: deploys the workflow + server registers it ─────────────

Console.WriteLine("--- First run (by Agent object) ---");
var result1 = await runtime.RunAsync(agent, "What time is it in UTC right now?");
result1.PrintResult();

// ── Second run: by workflow name — no Agent object needed ─────────────
// Since this uses only server-side tools (HTTP), no workers are required.

Console.WriteLine("\n--- Second run (by workflow name) ---");
var result2 = await runtime.RunByNameAsync("world_clock_agent_63c", "Tell me the current UTC datetime.");
result2.PrintResult();
