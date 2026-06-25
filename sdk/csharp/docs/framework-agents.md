# Framework Agents

Agentspan ships thin adapters that let you author agents in the shape of three
popular frameworks and run them on the Agentspan runtime unchanged. Each adapter
builds a normal `Agent` (or attaches tools to one), so everything in
[writing-agents.md](writing-agents.md) and [advanced.md](advanced.md) still
applies — you run them with the same `AgentRuntime`.

| Framework | Package | Namespace | Entry point |
|---|---|---|---|
| OpenAI Agents | `Conductor.AI.OpenAI` | `Conductor.AI.OpenAI` | `OpenAIAgent.Builder()` / `OpenAIAgent.From(...)` |
| Google ADK | `Conductor.AI.GoogleADK` | `Conductor.AI.GoogleADK` | `GoogleADKAgent.Builder()` / `GoogleADKAgent.From(...)` |
| Semantic Kernel | `Conductor.AI.SemanticKernel` | `Conductor.AI.SemanticKernel` | `SemanticKernelAgent.From(...)` |

```bash
dotnet add package conductor-ai-sdk-openai
dotnet add package conductor-ai-sdk-google-adk
dotnet add package conductor-ai-sdk-semantic-kernel
```

(Inside this repo, reference the corresponding `src/Agentspan.*/*.csproj`.)

## OpenAI Agents

Mirrors the OpenAI Agents SDK shape. The SDK routes the agent through
`framework="openai"` and the server's `OpenAINormalizer` consumes it. Model names
without a provider prefix are auto-prefixed with `openai/` server-side.

```csharp
using Conductor.AI;
using Conductor.AI.OpenAI;

var agent = OpenAIAgent.Builder()
    .Name("greeter")
    .Instructions("You are a friendly assistant. Keep responses concise.")
    .Model("openai/gpt-4o-mini")
    .Build();

await using var runtime = new AgentRuntime();
var result = await runtime.RunAsync(agent, "Say hello and share a fun fact about C#.");
result.PrintResult();
```

**Tools** — pass objects whose public methods carry `[Tool]`; they are scanned via
`ToolRegistry.FromInstance` and become worker tools:

```csharp
var agent = OpenAIAgent.Builder()
    .Name("multi_tool_agent")
    .Instructions("Use the weather and calculator tools to answer questions.")
    .Model("openai/gpt-4o-mini")
    .Tools(new WeatherTools())          // [Tool]-annotated object(s)
    .Build();

internal sealed class WeatherTools
{
    [Tool(Name = "get_weather", Description = "Get the current weather for a city.")]
    public string GetWeather(string city) => $"Sunny in {city}.";
}
```

Use `.ToolDefs(...)` to add already-built `ToolDef`s (HTTP, MCP, etc.).

**Handoffs** — the OpenAI "handoffs" list of sub-agents the LLM can transfer to:

```csharp
var triage = OpenAIAgent.Builder()
    .Name("customer_service_triage")
    .Instructions("Triage the request and hand off to the right specialist.")
    .Model("openai/gpt-4o-mini")
    .Handoffs(orderAgent, refundAgent, salesAgent)
    .Build();
```

Convenience shortcut: `OpenAIAgent.From(name, model, instructions, params object[] toolObjects)`.
A structured-output type name can be set via `.OutputType("MyType")`.

## Google ADK

Mirrors the Google ADK (Agent Development Kit) shape. Differences from OpenAI at
the wire level: `Instruction` (singular), `SubAgents` (not handoffs), and bare
model names like `"gemini-2.0-flash"` are prefixed with `"google_gemini/"`
server-side. Consumed by the server's `GoogleADKNormalizer`.

```csharp
using Conductor.AI;
using Conductor.AI.GoogleADK;

var agent = GoogleADKAgent.Builder()
    .Name("greeter")
    .Model("gemini-2.0-flash")
    .Instruction("You are a friendly assistant. Keep responses concise.")  // note: singular
    .Build();

await using var runtime = new AgentRuntime();
var result = await runtime.RunAsync(agent, "Say hello and share a fun fact about ML.");
result.PrintResult();
```

Tools work the same way (`.Tools(new MyTools())` / `.ToolDefs(...)`). Delegate to
children with `.SubAgents(child1, child2)`. Shortcut:
`GoogleADKAgent.From(name, model, instruction, params object[] toolObjects)`.

## Semantic Kernel

Bridges Microsoft Semantic Kernel plugins. If you already have classes with
`[KernelFunction]`-annotated methods, hand them straight to
`SemanticKernelAgent.From` and each function becomes an Agentspan tool. (This
adapter builds a plain `Agent` — no `Framework` tag; the functions run as local
worker tools, invoked through the `KernelFunction` so SK's own arg coercion and
async unwrapping apply.)

```csharp
using System.ComponentModel;
using Conductor.AI;
using Conductor.AI.SemanticKernel;
using Microsoft.SemanticKernel;

internal sealed class CalculatorPlugin
{
    [KernelFunction, Description("Add two integers and return their sum.")]
    public int Add(
        [Description("first number")]  int a,
        [Description("second number")] int b) => a + b;
}

var agent = SemanticKernelAgent.From(
    name:         "sk_calc_agent",
    model:        "openai/gpt-4o-mini",
    instructions: "You are a calculator. Use the tools to answer math questions.",
    new CalculatorPlugin());

await using var runtime = new AgentRuntime();
var result = await runtime.RunAsync(agent, "What is 17 + 25?");
result.PrintResult();
```

You can also pass a prebuilt `KernelPlugin` instance:

```csharp
KernelPlugin plugin = KernelPluginFactory.CreateFromObject(new CalculatorPlugin(), "calc");

var agent = SemanticKernelAgent.From(
    name:         "sk_kernelplugin",
    model:        "openai/gpt-4o-mini",
    instructions: "Solve arithmetic using the calc plugin.",
    plugin);
```

`SemanticKernelAgent.From(name, model, instructions, params object[] plugins)`
accepts any mix of `[KernelFunction]` objects and `KernelPlugin` instances.
`SemanticKernelAgent.IsSemanticKernelPlugin(obj)` reports whether an object
qualifies.
</content>
