# Agentspan C# SDK

A .NET 8 SDK for building and running AI agents with the Agentspan platform.

## Requirements

- .NET 8.0 SDK or later
- An Agentspan server instance

## Setup

### Environment Variables

```bash
export AGENTSPAN_SERVER_URL=http://localhost:8080/api
export AGENTSPAN_AUTH_KEY=your-auth-key
export AGENTSPAN_AUTH_SECRET=your-auth-secret
export AGENTSPAN_LLM_MODEL=openai/gpt-4o-mini
```

### Build

```bash
cd sdk/csharp
dotnet build Agentspan.sln
```

## Quick Start

```csharp
using Agentspan;

var agent = new Agent(
    name: "assistant",
    model: "openai/gpt-4o-mini",
    instructions: "You are a helpful assistant."
);

using var runtime = new AgentRuntime(AgentConfig.FromEnv());
var result = runtime.Run(agent, "Hello! Tell me about C#.");
result.PrintResult();
```

## Core Concepts

### AgentConfig

Configuration for the runtime and HTTP client:

```csharp
var config = new AgentConfig
{
    ServerUrl = "http://localhost:8080/api",
    AuthKey = "your-key",
    AuthSecret = "your-secret",
    WorkerPollIntervalMs = 100,
    StatusPollIntervalMs = 1000,
};

// Or load from environment variables:
var config = AgentConfig.FromEnv();
```

### Agent

Define agents with model, instructions, tools, and sub-agents:

```csharp
var agent = new Agent(
    name: "my_agent",
    model: "openai/gpt-4o-mini",
    instructions: "You are helpful.",
    tools: myTools,
    maxTurns: 25,
    temperature: 0.7
);
```

### Tools

Mark methods with `[Tool]` and register them using `ToolRegistry.FromInstance`:

```csharp
class MyTools
{
    [Tool(Description = "Get the current time")]
    public Dictionary<string, object> GetTime(string timezone = "UTC")
    {
        return new() { ["time"] = DateTime.UtcNow.ToString("o"), ["timezone"] = timezone };
    }

    [Tool(ApprovalRequired = true, Description = "Send a notification")]
    public Dictionary<string, object> SendNotification(string message, string recipient)
    {
        return new() { ["status"] = "sent" };
    }
}

var tools = ToolRegistry.FromInstance(new MyTools()).ToList();
```

You can also create HTTP and MCP tools:

```csharp
// HTTP tool
var httpTool = ToolRegistry.HttpTool(
    name: "weather_api",
    description: "Get weather data",
    url: "https://api.weather.com/v1/current",
    method: "GET"
);

// MCP tool
var mcpTool = ToolRegistry.McpTool(
    serverUrl: "http://localhost:3000",
    name: "search",
    description: "Search tool via MCP"
);
```

### Multi-Agent Strategies

```csharp
// Handoff: orchestrator routes to sub-agents
var orchestrator = new Agent(
    name: "orchestrator",
    model: "openai/gpt-4o-mini",
    subAgents: [agentA, agentB],
    strategy: Strategy.Handoff
);

// Sequential pipeline using >> operator
var pipeline = researcher >> writer >> editor;

// Parallel: all agents run simultaneously
var parallel = new Agent(
    name: "analyzer",
    model: "openai/gpt-4o-mini",
    subAgents: [analystA, analystB, analystC],
    strategy: Strategy.Parallel
);

// Router: dedicated router agent decides which sub-agent to call
var routed = new Agent(
    name: "main",
    model: "openai/gpt-4o-mini",
    subAgents: [agentA, agentB],
    strategy: Strategy.Router,
    router: routerAgent
);
```

### Guardrails

```csharp
var guardrail = new Guardrail(
    func: content => {
        if (content.Contains("sensitive"))
            return new GuardrailResult(false, "Contains sensitive content");
        return new GuardrailResult(true);
    },
    position: GuardrailPosition.Output,
    onFail: GuardrailOnFail.Retry,
    name: "content_check",
    maxRetries: 3
);

var agent = new Agent(
    name: "safe_agent",
    model: "openai/gpt-4o-mini",
    guardrails: [guardrail]
);
```

### Structured Output

```csharp
public class AnalysisResult
{
    public string Summary { get; set; } = "";
    public int ConfidenceScore { get; set; }
    public List<string> KeyPoints { get; set; } = [];
}

var agent = new Agent(
    name: "analyzer",
    model: "openai/gpt-4o-mini",
    outputType: typeof(AnalysisResult)
);

var result = runtime.Run(agent, "Analyze this text...");
var analysis = result.GetOutput<AnalysisResult>();
```

### Running Agents

```csharp
using var runtime = new AgentRuntime(config);

// Synchronous (blocks until complete)
var result = runtime.Run(agent, "Your prompt");

// Asynchronous
var result = await runtime.RunAsync(agent, "Your prompt");

// Start and get a handle (non-blocking)
var handle = await runtime.StartAsync(agent, "Your prompt");
var result = await handle.WaitAsync();

// Streaming events
await foreach (var ev in runtime.StreamAsync(agent, "Your prompt"))
{
    Console.WriteLine($"{ev.Type}: {ev.Content}");
}
```

### Human-in-the-Loop

```csharp
var handle = runtime.Start(agent, "Do something requiring approval");

// Later, approve or reject
await handle.ApproveAsync();
await handle.RejectAsync("Not authorized");
```

## Examples

| Example | Description |
|---------|-------------|
| `01_BasicAgent` | Simplest agent with no tools |
| `02_Tools` | Tools via `[Tool]` attribute and `ToolRegistry.FromInstance` |
| `03_StructuredOutput` | Typed output with `outputType` |
| `05_Handoffs` | Multi-agent orchestration with `Strategy.Handoff` |
| `06_SequentialPipeline` | Pipeline composition with `>>` operator |
| `07_ParallelAgents` | Concurrent sub-agents with `Strategy.Parallel` |
| `08_RouterAgent` | Explicit router with `Strategy.Router` |
| `09_HumanInTheLoop` | Approval workflow with `ApproveAsync`/`RejectAsync` |
| `10_Guardrails` | Output validation with custom guardrail functions |
| `11_Streaming` | Real-time SSE event streaming |

Run any example:

```bash
cd sdk/csharp/examples/01_BasicAgent
dotnet run
```

## Project Structure

```
sdk/csharp/
├── Agentspan.sln
├── README.md
├── src/
│   └── Agentspan/
│       ├── Agentspan.csproj
│       ├── AgentConfig.cs          # Runtime configuration
│       ├── Agent.cs                # Agent definition + >> operator
│       ├── Tool.cs                 # [Tool] attribute + ToolRegistry
│       ├── Guardrail.cs            # Guardrail definition
│       ├── Result.cs               # AgentResult, AgentHandle, AgentEvent
│       ├── AgentConfigSerializer.cs # Serializes Agent to JSON payload
│       ├── AgentHttpClient.cs      # HTTP client for API calls + SSE
│       ├── WorkerManager.cs        # Conductor task worker polling
│       └── AgentRuntime.cs         # Main entry point
└── examples/
    ├── Shared/Settings.cs          # Shared environment config
    ├── 01_BasicAgent/
    ├── 02_Tools/
    ├── 03_StructuredOutput/
    ├── 05_Handoffs/
    ├── 06_SequentialPipeline/
    ├── 07_ParallelAgents/
    ├── 08_RouterAgent/
    ├── 09_HumanInTheLoop/
    ├── 10_Guardrails/
    └── 11_Streaming/
```
