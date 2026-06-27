# Agentspan .NET SDK — Documentation

The official .NET SDK for [Agentspan](https://agentspan.ai) — long-running, background, scheduled, event-driven, and plan-execute AI agents.

- **Package:** `conductor-agent-sdk` (NuGet)
- **Target:** .NET 10
- **Namespace:** `Conductor.AI`

## Contents

| Doc | Covers |
|---|---|
| [getting-started.md](getting-started.md) | Install, env vars, and a running agent in under 30 seconds. |
| [writing-agents.md](writing-agents.md) | Authoring agents: instructions, tools, multi-agent strategies, handoffs, guardrails, termination, callbacks, streaming, HITL, schedules, `[AgentDef]`, stateful agents. |
| [framework-agents.md](framework-agents.md) | Running agents authored with the OpenAI, Google ADK, and Semantic Kernel adapters. |
| [advanced.md](advanced.md) | Runtime options, the `AgentClient` control plane, deploy/serve/run/plan, worker tuning, structured output, credentials, plans / PLAN_EXECUTE. |
| [api-reference.md](api-reference.md) | The public surface, one section per type. |

## At a glance

```csharp
using Conductor.AI;

var agent = new Agent("greeter")
{
    Model        = "openai/gpt-4o-mini",
    Instructions = "You are a friendly assistant. Keep responses brief.",
};

await using var runtime = new AgentRuntime();
var result = await runtime.RunAsync(agent, "Say hello!");
result.PrintResult();
```

You need a running Agentspan server (default `http://localhost:6767/api`). See [getting-started.md](getting-started.md).
</content>
