# Agentspan .NET SDK

The official .NET SDK for [Agentspan](https://agentspan.ai) — durable, scalable, observable AI agents.

- **Target**: .NET 8
- **Dependencies**: BCL only (`System.Text.Json`, `System.Net.Http`) — no external packages

## Quick Start

### 1. Prerequisites

- .NET 8 SDK (`dotnet --version` should show `8.x.x`)
- Agentspan server running (default: `http://localhost:6767`)

### 2. Reference the library

In your `.csproj`:

```xml
<ItemGroup>
  <ProjectReference Include="path/to/sdk/csharp/src/Agentspan/Agentspan.csproj" />
</ItemGroup>
```

### 3. Hello World

```csharp
using Agentspan;

var agent = new Agent("greeter")
{
    Model = "openai/gpt-4o-mini",
    Instructions = "You are a friendly assistant. Keep responses brief.",
};

await using var runtime = new AgentRuntime();
var result = await runtime.RunAsync(agent, "Say hello!");
result.PrintResult();
```

### 4. Environment variables

| Variable | Default | Description |
|---|---|---|
| `AGENTSPAN_SERVER_URL` | `http://localhost:6767/api` | Agentspan server URL |
| `AGENTSPAN_LLM_MODEL` | `openai/gpt-4o-mini` | Default LLM model |
| `AGENTSPAN_AUTH_KEY` | — | Auth key (no-auth mode if unset) |
| `AGENTSPAN_AUTH_SECRET` | — | Auth secret |

## Core Concepts

### Agent

The fundamental unit. An agent is an LLM with optional tools and/or sub-agents:

```csharp
var agent = new Agent("my_agent")
{
    Model = "openai/gpt-4o-mini",
    Instructions = "You are helpful.",
    Tools = myTools,        // optional: local worker tools
    Agents = [subAgent],    // optional: sub-agents (for multi-agent)
    Strategy = Strategy.Handoff,  // optional: orchestration strategy
    MaxTurns = 10,          // optional
};
```

### Tools

Decorate methods with `[Tool]` and use `ToolRegistry.FromInstance()`:

```csharp
internal sealed class MyTools
{
    [Tool("Get the weather for a city.")]
    public Dictionary<string, object> GetWeather(string city)
        => new() { ["temp_f"] = 72, ["condition"] = "Sunny" };
}

var tools = ToolRegistry.FromInstance(new MyTools());
var agent = new Agent("assistant") { Tools = tools };
```

Tool names are automatically converted to `snake_case` (`GetWeather` → `get_weather`).

### Strategies

| Strategy | Description |
|---|---|
| `Handoff` | Parent LLM picks which sub-agent to delegate to |
| `Sequential` | Agents run in order; output feeds next |
| `Parallel` | All sub-agents run concurrently, results aggregated |
| `Router` | Dedicated router agent selects which specialist handles the request |
| `RoundRobin` | Sub-agents take turns |
| `Random` | Sub-agent selected randomly |
| `Swarm` | Collaborative swarm |

### Sequential Pipeline (`>>` operator)

```csharp
var pipeline = researcher >> writer >> editor;
var result = await runtime.RunAsync(pipeline, "Topic: AI in 2025");
```

### Router Agent

```csharp
var team = new Agent("dev_team")
{
    Agents = [planner, coder, reviewer],
    Strategy = Strategy.Router,
    Router = selector, // dedicated classifier
};
```

### Streaming Events

```csharp
var handle = await runtime.StartAsync(agent, "Hello");
await foreach (var ev in handle.StreamAsync())
{
    switch (ev.Type)
    {
        case EventType.Thinking:
            Console.WriteLine($"[thinking] {ev.Content}");
            break;
        case EventType.ToolCall:
            Console.WriteLine($"[tool_call] {ev.ToolName}({ev.Args})");
            break;
        case EventType.Done:
            Console.WriteLine($"Done: {ev.Content}");
            break;
    }
}
```

### Human-in-the-Loop

```csharp
var handle = await runtime.StartAsync(agent, prompt);
await foreach (var ev in handle.StreamAsync())
{
    if (ev.Type == EventType.Waiting)
    {
        // Agent is waiting for human input
        await handle.ApproveAsync();   // or
        await handle.RejectAsync("reason");
    }
}
```

## Examples

Run from the `sdk/csharp` directory:

```bash
# Basic agent
dotnet run --project examples/01_BasicAgent

# Tools — LLM picks the right tool
dotnet run --project examples/02_Tools

# Simple weather + stock tools
dotnet run --project examples/02a_SimpleTools

# Multi-agent handoffs
dotnet run --project examples/05_Handoffs

# Sequential pipeline (researcher >> writer >> editor)
dotnet run --project examples/06_SequentialPipeline

# Parallel analysis (market + risk + compliance)
dotnet run --project examples/07_ParallelAgents

# Router with dedicated classifier
dotnet run --project examples/08_RouterAgent
```

Or build the whole solution:

```bash
dotnet build Agentspan.sln
```

## Project Structure

```
sdk/csharp/
├── Agentspan.sln
├── src/
│   └── Agentspan/
│       ├── Agentspan.csproj
│       ├── Agent.cs                  # Agent + Strategy + >> operator
│       ├── Tool.cs                   # [Tool] attribute + ToolRegistry
│       ├── Result.cs                 # AgentResult, AgentHandle, AgentEvent
│       ├── AgentConfigSerializer.cs  # Wire format serializer
│       ├── AgentHttpClient.cs        # HTTP + SSE client
│       ├── WorkerManager.cs          # Tool polling loop
│       └── AgentRuntime.cs           # Main entry point
└── examples/
    ├── Shared/Settings.cs
    ├── 01_BasicAgent/
    ├── 02_Tools/
    ├── 02a_SimpleTools/
    ├── 05_Handoffs/
    ├── 06_SequentialPipeline/
    ├── 07_ParallelAgents/
    └── 08_RouterAgent/
```

## Wire Format

The SDK serializes agents to the format the Agentspan server expects:

```json
{
  "agentConfig": {
    "name": "my_agent",
    "model": "openai/gpt-4o-mini",
    "instructions": "...",
    "tools": [
      {
        "name": "get_weather",
        "description": "...",
        "inputSchema": { "type": "object", "properties": { "city": { "type": "string" } }, "required": ["city"] },
        "toolType": "worker"
      }
    ],
    "agents": [],
    "strategy": "handoff"
  },
  "prompt": "What's the weather in Tokyo?",
  "sessionId": ""
}
```

## License

MIT License. Copyright (c) 2025 Agentspan.
