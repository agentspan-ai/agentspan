# Getting Started

Get an agent running in under 30 seconds.

## 1. Install

The SDK ships as the `conductor-agent-sdk` NuGet package (target framework: .NET 10).

```bash
dotnet new console -n MyAgent
cd MyAgent
dotnet add package conductor-agent-sdk
```

> Working inside this repository instead of from NuGet? Reference the project directly:
>
> ```xml
> <ItemGroup>
>   <ProjectReference Include="path/to/sdk/csharp/src/Conductor.AI/Conductor.AI.csproj" />
> </ItemGroup>
> ```

## 2. Point at a server

You need a running Conductor Agents server. The defaults assume a local one at `http://localhost:6767/api`.

| Variable | Default | Description |
|---|---|---|
| `AGENTSPAN_SERVER_URL` | `http://localhost:6767/api` | Conductor Agents server URL. |
| `AGENTSPAN_AUTH_KEY` | — | Auth key. Unset = no-auth mode (local / OSS). |
| `AGENTSPAN_AUTH_SECRET` | — | Auth secret. Set together with the key for Orkes Cloud. |

```bash
export AGENTSPAN_SERVER_URL=http://localhost:6767/api
# Orkes Cloud only:
# export AGENTSPAN_AUTH_KEY=...
# export AGENTSPAN_AUTH_SECRET=...
```

The runtime reads these on construction. You can also pass them explicitly via `AgentRuntimeOptions` (see [advanced.md](advanced.md)).

## 3. Run an agent

Replace `Program.cs` with:

```csharp
using Conductor.AI;

var agent = new Agent("greeter")
{
    Model        = "openai/gpt-4o-mini",
    Instructions = "You are a friendly assistant. Keep responses brief.",
};

await using var runtime = new AgentRuntime();
var result = await runtime.RunAsync(agent, "Say hello and tell me a fun fact about C#.");
result.PrintResult();
```

```bash
dotnet run
```

That is the whole loop: define an `Agent`, open an `AgentRuntime`, `await runtime.RunAsync(agent, prompt)`, and read the `AgentResult`. `await using` disposes the runtime (and shuts down any local tool workers) when you are done.

## Reading the result

`RunAsync` returns an [`AgentResult`](api-reference.md#agentresult). Common members:

```csharp
result.PrintResult();                 // formatted summary to stdout
bool ok       = result.IsSuccess;     // Status == Completed
var  output   = result.Output;        // Dictionary<string, object>?; final text is usually output["result"]
var  tokens   = result.TokenUsage;    // TokenUsage? (prompt / completion / total)
var  finish   = result.FinishReason;  // FinishReason? (Stop, Length, Guardrail, Rejected, ...)
string execId = result.ExecutionId;   // durable execution id on the server
```

## Next

- [writing-agents.md](writing-agents.md) — tools, multi-agent orchestration, guardrails, streaming, HITL.
- [advanced.md](advanced.md) — deploy/serve, the control-plane `AgentClient`, structured output, credentials.
</content>
