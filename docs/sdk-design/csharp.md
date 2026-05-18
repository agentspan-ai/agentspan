# C# SDK Translation Guide

**Date:** 2026-03-23
**Status:** Draft
**Base Spec:** `docs/sdk-design/2026-03-23-multi-language-sdk-design.md`
**Reference Implementation:** `sdk/python/examples/kitchen_sink.py`

---

## 1. Project Setup

### Target Framework

.NET 8.0+ (LTS). The SDK targets `net8.0` to leverage `IAsyncEnumerable`, `PeriodicTimer`, `System.Threading.Channels`, records, and nullable reference types, all of which are stable in .NET 8.

### Directory Layout

```
agentspan-dotnet/
  src/
    Agentspan/
      Agentspan.csproj
      Agent.cs
      AgentRuntime.cs
      Tools/
        Tool.cs
        ToolContext.cs
        ToolDef.cs
        HttpTool.cs
        McpTool.cs
        AgentTool.cs
        HumanTool.cs
        MediaTools.cs
        RagTools.cs
      Guardrails/
        Guardrail.cs
        GuardrailResult.cs
        RegexGuardrail.cs
        LlmGuardrail.cs
      Results/
        AgentResult.cs
        AgentHandle.cs
        AgentStatus.cs
        AgentEvent.cs
        AgentStream.cs
        TokenUsage.cs
      Strategies/
        Strategy.cs
      Termination/
        TerminationCondition.cs
        TextMentionTermination.cs
        MaxMessageTermination.cs
        TokenUsageTermination.cs
        StopMessageTermination.cs
      Handoffs/
        HandoffCondition.cs
        OnToolResult.cs
        OnTextMention.cs
        OnCondition.cs
      Memory/
        ConversationMemory.cs
        SemanticMemory.cs
        MemoryStore.cs
      CodeExecution/
        CodeExecutionConfig.cs
        CodeExecutor.cs
        LocalCodeExecutor.cs
        DockerCodeExecutor.cs
        JupyterCodeExecutor.cs
        ServerlessCodeExecutor.cs
      Credentials/
        CredentialFile.cs
        CredentialService.cs
      Workers/
        WorkerManager.cs
        WorkerPollLoop.cs
      Streaming/
        SseClient.cs
      Callbacks/
        CallbackHandler.cs
      Config/
        AgentConfig.cs
        AgentspanOptions.cs
      Exceptions/
        AgentspanException.cs
      Serialization/
        JsonConverters.cs
  tests/
    Agentspan.Tests/
      Agentspan.Tests.csproj
      MockRun.cs
      Assertions/
        AgentAssertions.cs
  examples/
    KitchenSink/
      KitchenSink.csproj
      Program.cs
```

### csproj Configuration

```xml
<Project Sdk="Microsoft.NET.Sdk">
  <PropertyGroup>
    <TargetFramework>net8.0</TargetFramework>
    <Nullable>enable</Nullable>
    <ImplicitUsings>enable</ImplicitUsings>
    <LangVersion>12</LangVersion>
    <RootNamespace>Agentspan</RootNamespace>
    <PackageId>Agentspan</PackageId>
    <Version>0.1.0</Version>
    <Description>Agentspan SDK for .NET</Description>
  </PropertyGroup>

  <ItemGroup>
    <!-- No external HTTP client needed; System.Net.Http is in-box -->
    <PackageReference Include="System.Text.Json" Version="8.0.5" />
    <PackageReference Include="System.Threading.Channels" Version="8.0.0" />
    <PackageReference Include="Microsoft.Extensions.Logging.Abstractions" Version="8.0.2" />
    <!-- Optional: Polly for resilience policies (retry, circuit breaker) -->
    <PackageReference Include="Polly" Version="8.5.0" />
  </ItemGroup>
</Project>
```

### Test Project

```xml
<Project Sdk="Microsoft.NET.Sdk">
  <PropertyGroup>
    <TargetFramework>net8.0</TargetFramework>
    <Nullable>enable</Nullable>
    <IsPackable>false</IsPackable>
  </PropertyGroup>

  <ItemGroup>
    <PackageReference Include="xunit" Version="2.9.3" />
    <PackageReference Include="xunit.runner.visualstudio" Version="2.8.2" />
    <PackageReference Include="FluentAssertions" Version="7.1.0" />
    <PackageReference Include="NSubstitute" Version="5.3.0" />
    <ProjectReference Include="../../src/Agentspan/Agentspan.csproj" />
  </ItemGroup>
</Project>
```

### Dependencies Summary

| Dependency | Purpose |
|---|---|
| `System.Net.Http` (in-box) | REST calls, SSE streaming |
| `System.Text.Json` | JSON serialization with `camelCase` policy |
| `System.Threading.Channels` | Producer/consumer for worker poll loop |
| `Microsoft.Extensions.Logging.Abstractions` | Structured logging interface |
| `Polly` (optional) | Retry/circuit-breaker for SSE reconnection |
| `xunit` + `FluentAssertions` | Testing framework |

---

## 2. Type System Mapping

### Core Enums

```csharp
using System.Text.Json.Serialization;

[JsonConverter(typeof(JsonStringEnumConverter))]
public enum Strategy
{
    [JsonPropertyName("handoff")]    Handoff,
    [JsonPropertyName("sequential")] Sequential,
    [JsonPropertyName("parallel")]   Parallel,
    [JsonPropertyName("router")]     Router,
    [JsonPropertyName("round_robin")]RoundRobin,
    [JsonPropertyName("random")]     Random,
    [JsonPropertyName("swarm")]      Swarm,
    [JsonPropertyName("manual")]     Manual,
}

[JsonConverter(typeof(JsonStringEnumConverter))]
public enum EventType
{
    [JsonPropertyName("thinking")]       Thinking,
    [JsonPropertyName("tool_call")]      ToolCall,
    [JsonPropertyName("tool_result")]    ToolResult,
    [JsonPropertyName("guardrail_pass")] GuardrailPass,
    [JsonPropertyName("guardrail_fail")] GuardrailFail,
    [JsonPropertyName("waiting")]        Waiting,
    [JsonPropertyName("handoff")]        Handoff,
    [JsonPropertyName("message")]        Message,
    [JsonPropertyName("error")]          Error,
    [JsonPropertyName("done")]           Done,
}

[JsonConverter(typeof(JsonStringEnumConverter))]
public enum Status
{
    Completed, Failed, Terminated, TimedOut,
}

[JsonConverter(typeof(JsonStringEnumConverter))]
public enum FinishReason
{
    Stop, Length, ToolCalls, Error, Cancelled, Timeout, Guardrail, Rejected,
}

[JsonConverter(typeof(JsonStringEnumConverter))]
public enum OnFail
{
    [JsonPropertyName("retry")] Retry,
    [JsonPropertyName("raise")] Raise,
    [JsonPropertyName("fix")]   Fix,
    [JsonPropertyName("human")] Human,
}

[JsonConverter(typeof(JsonStringEnumConverter))]
public enum Position
{
    [JsonPropertyName("input")]  Input,
    [JsonPropertyName("output")] Output,
}
```

### Core Records and Classes

C# records provide immutable value semantics with built-in equality, deconstruction, and `with` expressions. Use `record` for data-transfer objects and `class` for types with mutable state or behavior.

```csharp
// --- Token Usage ---
public record TokenUsage(
    [property: JsonPropertyName("promptTokens")]     int PromptTokens,
    [property: JsonPropertyName("completionTokens")] int CompletionTokens,
    [property: JsonPropertyName("totalTokens")]      int TotalTokens
);

// --- Agent Event (yielded by SSE stream) ---
public record AgentEvent
{
    [JsonPropertyName("type")]          public EventType Type { get; init; }
    [JsonPropertyName("content")]       public string?   Content { get; init; }
    [JsonPropertyName("toolName")]      public string?   ToolName { get; init; }
    [JsonPropertyName("args")]          public Dictionary<string, object>? Args { get; init; }
    [JsonPropertyName("result")]        public object?   Result { get; init; }
    [JsonPropertyName("target")]        public string?   Target { get; init; }
    [JsonPropertyName("output")]        public object?   Output { get; init; }
    [JsonPropertyName("executionId")]    public string?   ExecutionId { get; init; }
    [JsonPropertyName("guardrailName")] public string?   GuardrailName { get; init; }
    [JsonPropertyName("timestamp")]     public long?     Timestamp { get; init; }
}

// --- Agent Result (returned by run/stream) ---
public record AgentResult
{
    [JsonPropertyName("output")]       public Dictionary<string, object>? Output { get; init; }
    [JsonPropertyName("executionId")]   public string ExecutionId { get; init; } = "";
    [JsonPropertyName("correlationId")]public string? CorrelationId { get; init; }
    [JsonPropertyName("messages")]     public List<Dictionary<string, object>>? Messages { get; init; }
    [JsonPropertyName("toolCalls")]    public List<Dictionary<string, object>>? ToolCalls { get; init; }
    [JsonPropertyName("status")]       public Status Status { get; init; }
    [JsonPropertyName("finishReason")] public FinishReason? FinishReason { get; init; }
    [JsonPropertyName("error")]        public string? Error { get; init; }
    [JsonPropertyName("tokenUsage")]   public TokenUsage? TokenUsage { get; init; }
    [JsonPropertyName("metadata")]     public Dictionary<string, object>? Metadata { get; init; }
    [JsonPropertyName("events")]       public List<AgentEvent>? Events { get; init; }
    [JsonPropertyName("subResults")]   public Dictionary<string, object>? SubResults { get; init; }

    [JsonIgnore] public bool IsSuccess  => Status == Status.Completed;
    [JsonIgnore] public bool IsFailed   => Status == Status.Failed;
    [JsonIgnore] public bool IsRejected => FinishReason == FinishReason.Rejected;

    public void PrintResult() => Console.WriteLine(
        $"[{Status}] {Output?.GetValueOrDefault("result", "(no result)")}");
}

// --- Tool Context (injected into tool methods) ---
public record ToolContext
{
    public string SessionId  { get; init; } = "";
    public string ExecutionId { get; init; } = "";
    public string AgentName  { get; init; } = "";
    public Dictionary<string, object>? Metadata     { get; init; }
    public Dictionary<string, object>? Dependencies { get; init; }
    public Dictionary<string, object>? State        { get; init; }
}

// --- Guardrail Result ---
public record GuardrailResult(
    bool Passed,
    string? Message = null,
    string? FixedOutput = null
);

// --- Deployment Info ---
public record DeploymentInfo(
    [property: JsonPropertyName("registeredName")] string RegisteredName,
    [property: JsonPropertyName("agentName")]    string AgentName
);

// --- Agent Status (returned by polling) ---
public record AgentStatus
{
    [JsonPropertyName("executionId")]  public string ExecutionId { get; init; } = "";
    [JsonPropertyName("isComplete")]  public bool IsComplete { get; init; }
    [JsonPropertyName("isRunning")]   public bool IsRunning { get; init; }
    [JsonPropertyName("isWaiting")]   public bool IsWaiting { get; init; }
    [JsonPropertyName("output")]      public object? Output { get; init; }
    [JsonPropertyName("status")]      public string? StatusValue { get; init; }
    [JsonPropertyName("reason")]      public string? Reason { get; init; }
    [JsonPropertyName("currentTask")] public string? CurrentTask { get; init; }
    [JsonPropertyName("pendingTool")] public Dictionary<string, object>? PendingTool { get; init; }
    [JsonPropertyName("tokenUsage")]  public TokenUsage? TokenUsage { get; init; }
}

// --- Credential File ---
public record CredentialFile(
    string EnvVar,
    string? RelativePath = null,
    string? Content = null
);

// --- Prompt Template ---
public record PromptTemplate(
    string Name,
    Dictionary<string, string>? Variables = null,
    int? Version = null
);

// --- Code Execution ---
public record CodeExecutionConfig(
    bool Enabled = true,
    List<string>? AllowedLanguages = null,
    List<string>? AllowedCommands = null,
    int Timeout = 30
);

public record CliConfig(
    bool Enabled = true,
    List<string>? AllowedCommands = null,
    int Timeout = 30,
    bool AllowShell = false
);

public record ExecutionResult(
    string Output,
    string? Error = null,
    int ExitCode = 0,
    bool TimedOut = false
)
{
    [JsonIgnore] public bool Success => ExitCode == 0 && !TimedOut;
}
```

### JSON Serialization Options

All serialization uses a shared `JsonSerializerOptions` configured once:

```csharp
public static class AgentspanJson
{
    public static readonly JsonSerializerOptions Options = new()
    {
        PropertyNamingPolicy = JsonNamingPolicy.CamelCase,
        DefaultIgnoreCondition = JsonIgnoreCondition.WhenWritingNull,
        Converters = { new JsonStringEnumConverter(JsonNamingPolicy.SnakeCaseLower) },
        WriteIndented = false,
    };
}
```

The `CamelCase` naming policy matches the wire format requirement. `WhenWritingNull` omits null keys for cleaner JSON. The `SnakeCaseLower` enum converter maps C# `PascalCase` enum members to the `snake_case` wire values (e.g., `RoundRobin` becomes `"round_robin"`).

---

## 3. Attributes + Fluent Builder

### Attribute-Based Definition

C# attributes (`[Tool]`, `[AgentDef]`, `[Guardrail]`) declaratively mark methods and classes, mirroring Python's `@tool`, `@agent`, and `@guardrail` decorators. A source generator or runtime reflection scanner discovers annotated members at startup.

```csharp
// --- Tool attribute on methods ---
[AttributeUsage(AttributeTargets.Method)]
public class ToolAttribute : Attribute
{
    public string?  Name             { get; set; }
    public string?  Description      { get; set; }
    public bool     ApprovalRequired { get; set; }
    public bool     External         { get; set; }
    public bool     Isolated         { get; set; } = true;
    public int      TimeoutSeconds   { get; set; } = 120;
    public string[] Credentials      { get; set; } = [];
}

// --- Agent attribute on classes ---
[AttributeUsage(AttributeTargets.Class)]
public class AgentDefAttribute : Attribute
{
    public string?   Name         { get; set; }
    public string?   Model        { get; set; }
    public string?   Instructions { get; set; }
    public Strategy? Strategy     { get; set; }
    public int       MaxTurns     { get; set; } = 25;
}

// --- Guardrail attribute on methods ---
[AttributeUsage(AttributeTargets.Method)]
public class GuardrailAttribute : Attribute
{
    public string?  Name       { get; set; }
    public Position Position   { get; set; } = Position.Output;
    public OnFail   OnFail     { get; set; } = OnFail.Raise;
    public int      MaxRetries { get; set; } = 3;
}
```

**Usage example:**

```csharp
public class ResearchTools
{
    [Tool(Name = "research_database", Credentials = ["RESEARCH_API_KEY"])]
    public static Dictionary<string, object> ResearchDatabase(string query, ToolContext? ctx = null)
    {
        var session = ctx?.SessionId ?? "unknown";
        return new()
        {
            ["query"] = query,
            ["session_id"] = session,
            ["results"] = new[] { "quantum computing advances" },
        };
    }

    [Tool(ApprovalRequired = true)]
    public static Dictionary<string, object> PublishArticle(string title, string content, string platform)
    {
        return new() { ["status"] = "published", ["title"] = title, ["platform"] = platform };
    }

    [Tool(External = true)]
    public static Dictionary<string, object> ExternalResearchAggregator(string query, int sources = 10)
    {
        throw new NotImplementedException("Runs on remote worker");
    }
}

// Auto-discover from OpenAPI/Swagger/Postman spec
var stripe = ApiTool.Create("https://api.stripe.com/openapi.json")
    .WithHeaders(new() { ["Authorization"] = "Bearer ${STRIPE_KEY}" })
    .WithCredentials("STRIPE_KEY")
    .WithMaxTools(20)
    .Build();

public class SafetyGuardrails
{
    [Guardrail(Position = Position.Output, OnFail = OnFail.Human)]
    public static GuardrailResult FactValidator(string content)
    {
        var redFlags = new[] { "the best", "always", "never", "guaranteed" };
        var found = redFlags.Where(rf => content.Contains(rf, StringComparison.OrdinalIgnoreCase)).ToList();
        return found.Count > 0
            ? new GuardrailResult(false, $"Unverifiable claims: {string.Join(", ", found)}")
            : new GuardrailResult(true);
    }

    [Guardrail(Position = Position.Input, OnFail = OnFail.Raise)]
    public static GuardrailResult SqlInjectionGuard(string content)
    {
        var patterns = new[] { "DROP TABLE", "'; --", "OR 1=1" };
        return patterns.Any(p => content.Contains(p, StringComparison.OrdinalIgnoreCase))
            ? new GuardrailResult(false, "SQL injection detected.")
            : new GuardrailResult(true);
    }
}
```

### Fluent Builder

The fluent builder provides an alternative to attributes and to the constructor approach. Every `With*` method returns `this` for chaining. `Build()` validates and freezes the definition.

```csharp
public class AgentBuilder
{
    private readonly Agent _agent = new();

    public static AgentBuilder Create(string name) => new() { _agent = { Name = name } };

    public AgentBuilder WithModel(string model)                     { _agent.Model = model; return this; }
    public AgentBuilder WithInstructions(string instructions)       { _agent.Instructions = instructions; return this; }
    public AgentBuilder WithInstructions(PromptTemplate template)   { _agent.PromptTemplateInstructions = template; return this; }
    public AgentBuilder WithTools(params ToolDef[] tools)           { _agent.Tools.AddRange(tools); return this; }
    public AgentBuilder WithAgents(params Agent[] agents)           { _agent.Agents.AddRange(agents); return this; }
    public AgentBuilder WithStrategy(Strategy strategy)             { _agent.Strategy = strategy; return this; }
    public AgentBuilder WithRouter(Agent router)                    { _agent.Router = router; return this; }
    public AgentBuilder WithOutputType<T>()                         { _agent.OutputType = typeof(T); return this; }
    public AgentBuilder WithGuardrails(params Guardrail[] guards)   { _agent.Guardrails.AddRange(guards); return this; }
    public AgentBuilder WithMemory(ConversationMemory memory)       { _agent.Memory = memory; return this; }
    public AgentBuilder WithMaxTurns(int turns)                     { _agent.MaxTurns = turns; return this; }
    public AgentBuilder WithMaxTokens(int tokens)                   { _agent.MaxTokens = tokens; return this; }
    public AgentBuilder WithTemperature(double temp)                { _agent.Temperature = temp; return this; }
    public AgentBuilder WithTimeout(int seconds)                    { _agent.TimeoutSeconds = seconds; return this; }
    public AgentBuilder WithExternal(bool external = true)          { _agent.External = external; return this; }
    public AgentBuilder WithStopWhen(Func<List<object>, bool> fn)   { _agent.StopWhen = fn; return this; }
    public AgentBuilder WithTermination(TerminationCondition cond)  { _agent.Termination = cond; return this; }
    public AgentBuilder WithHandoffs(params HandoffCondition[] h)   { _agent.Handoffs.AddRange(h); return this; }
    public AgentBuilder WithAllowedTransitions(Dictionary<string, List<string>> t) { _agent.AllowedTransitions = t; return this; }
    public AgentBuilder WithIntroduction(string intro)              { _agent.Introduction = intro; return this; }
    public AgentBuilder WithMetadata(Dictionary<string, object> m)  { _agent.Metadata = m; return this; }
    public AgentBuilder WithCallbacks(params CallbackHandler[] cb)  { _agent.Callbacks.AddRange(cb); return this; }
    public AgentBuilder WithPlanner(bool planner = true)            { _agent.Planner = planner; return this; }
    public AgentBuilder WithIncludeContents(string mode)            { _agent.IncludeContents = mode; return this; }
    public AgentBuilder WithThinkingBudget(int tokens)              { _agent.ThinkingBudgetTokens = tokens; return this; }
    public AgentBuilder WithRequiredTools(params string[] tools)    { _agent.RequiredTools = tools.ToList(); return this; }
    public AgentBuilder WithGate(GateCondition gate)                { _agent.Gate = gate; return this; }
    public AgentBuilder WithCodeExecution(CodeExecutionConfig cfg)  { _agent.CodeExecutionConfig = cfg; return this; }
    public AgentBuilder WithCliConfig(CliConfig cfg)                { _agent.CliConfig = cfg; return this; }
    public AgentBuilder WithCredentials(params object[] creds)      { _agent.Credentials = creds.ToList(); return this; }

    public Agent Build()
    {
        if (string.IsNullOrWhiteSpace(_agent.Name))
            throw new ConfigurationException("Agent name is required.");
        if (_agent.Agents.Count > 0 && _agent.Strategy is null)
            throw new ConfigurationException("Strategy required when sub-agents are present.");
        return _agent;
    }
}
```

**Usage:**

```csharp
var agent = AgentBuilder.Create("draft_writer")
    .WithModel("openai/gpt-4o")
    .WithInstructions("Write a comprehensive article draft.")
    .WithTools(recallPastArticles)
    .WithMemory(new ConversationMemory(maxMessages: 50))
    .WithCallbacks(new PublishingCallbackHandler())
    .Build();
```

### Source Generators (Advanced)

For production use, a Roslyn source generator can scan `[Tool]` and `[AgentDef]` attributes at compile time and emit JSON Schema, Conductor task definitions, and worker registration code. This eliminates runtime reflection cost and provides compile-time validation.

```csharp
// Source generator emits this at compile time:
// [GeneratedCode("Agentspan.SourceGen")]
// public static partial ToolDef ResearchDatabase_ToolDef();
```

---

## 4. Async Model

### Async-First Design

The SDK is async-native. Every I/O method returns `Task<T>` and accepts an optional `CancellationToken`. Sync wrappers exist for convenience but delegate to the async path.

```csharp
// --- Async (preferred) ---
AgentResult result = await runtime.RunAsync(agent, prompt, cancellationToken);

AgentHandle handle = await runtime.StartAsync(agent, prompt, cancellationToken);
AgentStatus status = await handle.GetStatusAsync(cancellationToken);

await foreach (var evt in runtime.StreamAsync(agent, prompt, cancellationToken))
{
    Console.WriteLine($"[{evt.Type}] {evt.Content}");
}

// --- Sync wrapper (convenience, wraps async) ---
AgentResult result = runtime.Run(agent, prompt);
// Internally: RunAsync(agent, prompt).GetAwaiter().GetResult();
```

### IAsyncEnumerable for Streaming

Streaming returns `IAsyncEnumerable<AgentEvent>`, consumed with `await foreach`. This integrates naturally with LINQ via `System.Linq.Async` and supports cancellation.

```csharp
public interface IAgentStream : IAsyncEnumerable<AgentEvent>, IAsyncDisposable
{
    string ExecutionId { get; }
    List<AgentEvent> Events { get; }

    Task<AgentResult> GetResultAsync(CancellationToken ct = default);
    Task ApproveAsync(CancellationToken ct = default);
    Task RejectAsync(string? reason = null, CancellationToken ct = default);
    Task SendAsync(string message, CancellationToken ct = default);
    Task RespondAsync(object output, CancellationToken ct = default);
}
```

### CancellationToken for Timeouts

Use `CancellationTokenSource` with timeout for deadline enforcement. This is idiomatic .NET and integrates with all async APIs.

```csharp
using var cts = new CancellationTokenSource(TimeSpan.FromSeconds(300));
try
{
    var result = await runtime.RunAsync(agent, prompt, cts.Token);
}
catch (OperationCanceledException)
{
    Console.WriteLine("Agent execution timed out.");
}
```

### Resource Management with `using`

`AgentRuntime` implements `IAsyncDisposable`. The `await using` pattern ensures workers shut down cleanly.

```csharp
await using var runtime = new AgentRuntime();

// ... use runtime ...

// Dispose is called automatically, stopping workers, closing HTTP connections.
```

For synchronous contexts:

```csharp
using var runtime = new AgentRuntime(); // IDisposable, calls sync shutdown
```

---

## 5. Worker Implementation

Workers poll Conductor for tasks, execute the registered tool/guardrail/callback function, and report results. The implementation uses `Channel<T>` as a bounded producer/consumer queue and `PeriodicTimer` for the poll loop.

### Complete Worker Implementation

```csharp
public sealed class WorkerPollLoop : IAsyncDisposable
{
    private readonly HttpClient _http;
    private readonly string _serverUrl;
    private readonly string _taskName;
    private readonly Func<JsonElement, CancellationToken, Task<object>> _handler;
    private readonly Channel<JsonElement> _taskChannel;
    private readonly CancellationTokenSource _cts = new();
    private readonly ILogger _logger;
    private Task? _pollTask;
    private Task? _executeTask;

    private readonly int _pollIntervalMs;
    private readonly int _threadCount;

    public WorkerPollLoop(
        HttpClient http,
        string serverUrl,
        string taskName,
        Func<JsonElement, CancellationToken, Task<object>> handler,
        int pollIntervalMs = 100,
        int threadCount = 1,
        ILogger? logger = null)
    {
        _http = http;
        _serverUrl = serverUrl;
        _taskName = taskName;
        _handler = handler;
        _pollIntervalMs = pollIntervalMs;
        _threadCount = threadCount;
        _logger = logger ?? NullLogger.Instance;
        _taskChannel = Channel.CreateBounded<JsonElement>(new BoundedChannelOptions(100)
        {
            FullMode = BoundedChannelFullMode.Wait,
        });
    }

    public void Start()
    {
        _pollTask = Task.Run(() => PollLoopAsync(_cts.Token));
        _executeTask = Task.Run(() => ExecuteLoopAsync(_cts.Token));
    }

    private async Task PollLoopAsync(CancellationToken ct)
    {
        using var timer = new PeriodicTimer(TimeSpan.FromMilliseconds(_pollIntervalMs));

        while (await timer.WaitForNextTickAsync(ct))
        {
            try
            {
                var url = $"{_serverUrl}/tasks/poll/{_taskName}";
                var response = await _http.GetAsync(url, ct);

                if (!response.IsSuccessStatusCode) continue;

                var body = await response.Content.ReadAsStringAsync(ct);
                if (string.IsNullOrWhiteSpace(body) || body == "null") continue;

                var task = JsonSerializer.Deserialize<JsonElement>(body, AgentspanJson.Options);
                await _taskChannel.Writer.WriteAsync(task, ct);
            }
            catch (OperationCanceledException) { break; }
            catch (Exception ex)
            {
                _logger.LogWarning(ex, "Poll error for task {TaskName}", _taskName);
            }
        }
    }

    private async Task ExecuteLoopAsync(CancellationToken ct)
    {
        await foreach (var task in _taskChannel.Reader.ReadAllAsync(ct))
        {
            try
            {
                var taskId = task.GetProperty("taskId").GetString()!;
                var inputData = task.GetProperty("inputData");

                // Extract ToolContext from __agentspan_ctx__
                ToolContext? ctx = null;
                if (inputData.TryGetProperty("__agentspan_ctx__", out var ctxJson))
                {
                    ctx = JsonSerializer.Deserialize<ToolContext>(
                        ctxJson.GetRawText(), AgentspanJson.Options);
                }

                // Resolve credentials if declared
                if (ctx is not null)
                {
                    await ResolveCredentialsAsync(ctx, ct);
                }

                // Execute the handler
                var result = await _handler(inputData, ct);

                // Report success
                var updatePayload = new
                {
                    taskId,
                    workflowInstanceId = task.GetProperty("workflowInstanceId").GetString(),
                    status = "COMPLETED",
                    outputData = new { result },
                };

                var json = JsonSerializer.Serialize(updatePayload, AgentspanJson.Options);
                await _http.PostAsync(
                    $"{_serverUrl}/tasks",
                    new StringContent(json, System.Text.Encoding.UTF8, "application/json"),
                    ct);
            }
            catch (Exception ex)
            {
                _logger.LogError(ex, "Worker execution error for {TaskName}", _taskName);
                await ReportFailureAsync(task, ex, ct);
            }
        }
    }

    private async Task ResolveCredentialsAsync(ToolContext ctx, CancellationToken ct)
    {
        // Call POST /api/credentials/resolve with execution token
        // Inject resolved values into environment or tool context
    }

    private async Task ReportFailureAsync(JsonElement task, Exception ex, CancellationToken ct)
    {
        try
        {
            var taskId = task.GetProperty("taskId").GetString();
            var payload = new
            {
                taskId,
                workflowInstanceId = task.GetProperty("workflowInstanceId").GetString(),
                status = "FAILED",
                reasonForIncompletion = ex.Message,
            };
            var json = JsonSerializer.Serialize(payload, AgentspanJson.Options);
            await _http.PostAsync(
                $"{_serverUrl}/tasks",
                new StringContent(json, System.Text.Encoding.UTF8, "application/json"),
                ct);
        }
        catch { /* swallow reporting errors */ }
    }

    public async ValueTask DisposeAsync()
    {
        _cts.Cancel();
        _taskChannel.Writer.Complete();
        if (_pollTask is not null) await _pollTask;
        if (_executeTask is not null) await _executeTask;
        _cts.Dispose();
    }
}
```

### Worker Manager

The `WorkerManager` registers all tool/guardrail/callback workers discovered from the agent tree and manages their lifecycle.

```csharp
public sealed class WorkerManager : IAsyncDisposable
{
    private readonly List<WorkerPollLoop> _workers = [];
    private readonly HttpClient _http;
    private readonly string _serverUrl;

    public void RegisterTool(string taskName, Func<JsonElement, CancellationToken, Task<object>> handler)
    {
        var worker = new WorkerPollLoop(_http, _serverUrl, taskName, handler);
        _workers.Add(worker);
        worker.Start();
    }

    public async ValueTask DisposeAsync()
    {
        foreach (var w in _workers)
            await w.DisposeAsync();
    }
}
```

---

## 6. SSE Client

The SSE client connects to the server's event stream endpoint, parses the SSE wire format line by line, and yields `AgentEvent` objects as an `IAsyncEnumerable`.

### Complete SSE Implementation

```csharp
public sealed class SseClient : IAsyncDisposable
{
    private readonly HttpClient _http;
    private readonly string _baseUrl;
    private readonly ILogger _logger;

    private string? _lastEventId;
    private CancellationTokenSource? _cts;

    public SseClient(HttpClient http, string baseUrl, ILogger? logger = null)
    {
        _http = http;
        _baseUrl = baseUrl;
        _logger = logger ?? NullLogger.Instance;
    }

    public async IAsyncEnumerable<AgentEvent> StreamEventsAsync(
        string executionId,
        [System.Runtime.CompilerServices.EnumeratorCancellation] CancellationToken ct = default)
    {
        _cts = CancellationTokenSource.CreateLinkedTokenSource(ct);
        var token = _cts.Token;

        while (!token.IsCancellationRequested)
        {
            HttpResponseMessage? response = null;
            try
            {
                var request = new HttpRequestMessage(HttpMethod.Get,
                    $"{_baseUrl}/agent/stream/{executionId}");
                request.Headers.Accept.Add(
                    new System.Net.Http.Headers.MediaTypeWithQualityHeaderValue("text/event-stream"));

                // Reconnection: send Last-Event-ID
                if (_lastEventId is not null)
                    request.Headers.Add("Last-Event-ID", _lastEventId);

                response = await _http.SendAsync(
                    request, HttpCompletionOption.ResponseHeadersRead, token);
                response.EnsureSuccessStatusCode();

                using var stream = await response.Content.ReadAsStreamAsync(token);
                using var reader = new StreamReader(stream);

                string? eventType = null;
                string? eventId = null;
                string? dataBuffer = null;

                while (!reader.EndOfStream && !token.IsCancellationRequested)
                {
                    var line = await reader.ReadLineAsync(token);

                    if (line is null) break; // Stream ended

                    // Heartbeat: lines starting with ':'
                    if (line.StartsWith(':'))
                        continue;

                    // Blank line = end of event, dispatch
                    if (line.Length == 0)
                    {
                        if (dataBuffer is not null)
                        {
                            if (eventId is not null)
                                _lastEventId = eventId;

                            var agentEvent = JsonSerializer.Deserialize<AgentEvent>(
                                dataBuffer, AgentspanJson.Options);

                            if (agentEvent is not null)
                            {
                                yield return agentEvent;

                                if (agentEvent.Type == EventType.Done)
                                    yield break;
                            }
                        }
                        eventType = null;
                        eventId = null;
                        dataBuffer = null;
                        continue;
                    }

                    // Parse SSE fields
                    if (line.StartsWith("event:"))
                        eventType = line[6..].Trim();
                    else if (line.StartsWith("id:"))
                        eventId = line[3..].Trim();
                    else if (line.StartsWith("data:"))
                        dataBuffer = (dataBuffer is null)
                            ? line[5..].Trim()
                            : dataBuffer + "\n" + line[5..].Trim();
                }

                // Stream ended without a done event -- may reconnect
                _logger.LogInformation("SSE stream ended for {ExecutionId}, attempting reconnect", executionId);
            }
            catch (OperationCanceledException) { yield break; }
            catch (HttpRequestException ex)
            {
                _logger.LogWarning(ex, "SSE connection error, reconnecting in 1s");
                await Task.Delay(1000, token);
            }
            finally
            {
                response?.Dispose();
            }
        }
    }

    public async ValueTask DisposeAsync()
    {
        _cts?.Cancel();
        _cts?.Dispose();
    }
}
```

### AgentStream Wrapper

The `AgentStream` wraps the SSE client and provides HITL methods alongside event enumeration.

```csharp
public sealed class AgentStream : IAgentStream
{
    private readonly SseClient _sse;
    private readonly HttpClient _http;
    private readonly string _baseUrl;
    private readonly string _executionId;
    private readonly List<AgentEvent> _events = [];

    public string ExecutionId => _executionId;
    public List<AgentEvent> Events => _events;

    public async IAsyncEnumerator<AgentEvent> GetAsyncEnumerator(
        CancellationToken ct = default)
    {
        await foreach (var evt in _sse.StreamEventsAsync(_executionId, ct))
        {
            _events.Add(evt);
            yield return evt;
        }
    }

    public async Task<AgentResult> GetResultAsync(CancellationToken ct = default)
    {
        // Drain the stream
        await foreach (var _ in this.WithCancellation(ct)) { }

        var doneEvent = _events.LastOrDefault(e => e.Type == EventType.Done);
        return new AgentResult
        {
            ExecutionId = _executionId,
            Output = doneEvent?.Output as Dictionary<string, object>,
            Status = Status.Completed,
            Events = _events,
        };
    }

    public async Task ApproveAsync(CancellationToken ct = default)
    {
        var payload = JsonSerializer.Serialize(new { approved = true }, AgentspanJson.Options);
        await _http.PostAsync(
            $"{_baseUrl}/agent/{_executionId}/respond",
            new StringContent(payload, System.Text.Encoding.UTF8, "application/json"), ct);
    }

    public async Task RejectAsync(string? reason = null, CancellationToken ct = default)
    {
        var payload = JsonSerializer.Serialize(
            new { approved = false, reason }, AgentspanJson.Options);
        await _http.PostAsync(
            $"{_baseUrl}/agent/{_executionId}/respond",
            new StringContent(payload, System.Text.Encoding.UTF8, "application/json"), ct);
    }

    public async Task SendAsync(string message, CancellationToken ct = default)
    {
        var payload = JsonSerializer.Serialize(new { message }, AgentspanJson.Options);
        await _http.PostAsync(
            $"{_baseUrl}/agent/{_executionId}/respond",
            new StringContent(payload, System.Text.Encoding.UTF8, "application/json"), ct);
    }

    public async Task RespondAsync(object output, CancellationToken ct = default)
    {
        var payload = JsonSerializer.Serialize(output, AgentspanJson.Options);
        await _http.PostAsync(
            $"{_baseUrl}/agent/{_executionId}/respond",
            new StringContent(payload, System.Text.Encoding.UTF8, "application/json"), ct);
    }

    public ValueTask DisposeAsync() => _sse.DisposeAsync();
}
```

### Polly Retry Policy (Optional)

For production resilience, wrap the SSE connection in a Polly retry policy with exponential backoff:

```csharp
var retryPolicy = Policy
    .Handle<HttpRequestException>()
    .Or<TaskCanceledException>()
    .WaitAndRetryForeverAsync(
        retryAttempt => TimeSpan.FromSeconds(Math.Min(Math.Pow(2, retryAttempt), 30)),
        (exception, timeSpan) =>
        {
            _logger.LogWarning("SSE reconnecting in {Delay}s: {Message}", timeSpan.TotalSeconds, exception.Message);
        });
```

---

## 7. Error Handling

### Exception Hierarchy

```csharp
/// <summary>Base exception for all Agentspan errors.</summary>
public class AgentspanException : Exception
{
    public AgentspanException(string message) : base(message) { }
    public AgentspanException(string message, Exception inner) : base(message, inner) { }
}

/// <summary>Server returned an HTTP error.</summary>
public class AgentApiException : AgentspanException
{
    public int StatusCode { get; }
    public string? ResponseBody { get; }

    public AgentApiException(int statusCode, string message, string? body = null)
        : base($"API error {statusCode}: {message}")
    {
        StatusCode = statusCode;
        ResponseBody = body;
    }
}

/// <summary>Invalid agent configuration.</summary>
public class ConfigurationException : AgentspanException
{
    public ConfigurationException(string message) : base(message) { }
}

/// <summary>Agent not found on server.</summary>
public class AgentNotFoundException : AgentspanException
{
    public string AgentName { get; }
    public AgentNotFoundException(string agentName)
        : base($"Agent not found: {agentName}") => AgentName = agentName;
}

// --- Credential exceptions ---

public class CredentialNotFoundException : AgentspanException
{
    public string CredentialName { get; }
    public CredentialNotFoundException(string name)
        : base($"Credential not found: {name}") => CredentialName = name;
}

public class CredentialAuthException : AgentspanException
{
    public CredentialAuthException(string message) : base(message) { }
}

public class CredentialRateLimitException : AgentspanException
{
    public CredentialRateLimitException()
        : base("Credential resolution rate limit exceeded (120 calls/min)") { }
}

public class CredentialServiceException : AgentspanException
{
    public CredentialServiceException(string message, Exception? inner = null)
        : base(message, inner!) { }
}
```

### Error Propagation in IAsyncEnumerable

SSE errors are surfaced as `AgentEvent` with `EventType.Error` so consumers can handle them in the `await foreach` loop without an exception unwinding the iterator. For fatal errors (connection loss, deserialization failure), the iterator throws and the caller catches.

```csharp
await foreach (var evt in runtime.StreamAsync(agent, prompt))
{
    switch (evt.Type)
    {
        case EventType.Error:
            Console.WriteLine($"[error] {evt.Content}");
            break;
        case EventType.Done:
            Console.WriteLine("[done]");
            break;
        default:
            Console.WriteLine($"[{evt.Type}] {evt.Content}");
            break;
    }
}
```

For fatal connection errors:

```csharp
try
{
    await foreach (var evt in runtime.StreamAsync(agent, prompt))
    {
        // ...
    }
}
catch (AgentApiException ex) when (ex.StatusCode == 404)
{
    Console.WriteLine("Workflow not found.");
}
catch (TaskCanceledException)
{
    Console.WriteLine("Timed out.");
}
catch (AgentspanException ex)
{
    Console.WriteLine($"Agentspan error: {ex.Message}");
}
```

### CancellationToken Timeout Pattern

Every async method propagates `CancellationToken`. Use `CancellationTokenSource.CreateLinkedTokenSource` to combine user cancellation with SDK-level timeouts:

```csharp
public async Task<AgentResult> RunAsync(Agent agent, string prompt, CancellationToken ct = default)
{
    var timeout = agent.TimeoutSeconds > 0
        ? TimeSpan.FromSeconds(agent.TimeoutSeconds)
        : Timeout.InfiniteTimeSpan;

    using var linkedCts = CancellationTokenSource.CreateLinkedTokenSource(ct);
    linkedCts.CancelAfter(timeout);

    try
    {
        return await ExecuteInternalAsync(agent, prompt, linkedCts.Token);
    }
    catch (OperationCanceledException) when (!ct.IsCancellationRequested)
    {
        // SDK timeout, not user cancellation
        throw new AgentspanException($"Agent '{agent.Name}' timed out after {agent.TimeoutSeconds}s");
    }
}
```

---

## 8. Testing Framework

### Test Harness

The test project uses xUnit for structure and FluentAssertions for expressive assertions. A `MockRun` utility executes agents without a live server.

```csharp
public static class MockRun
{
    /// <summary>
    /// Execute an agent without a server connection. Tools run locally,
    /// guardrails execute inline, and a mock LLM returns canned responses.
    /// </summary>
    public static async Task<AgentResult> ExecuteAsync(
        Agent agent,
        string prompt,
        Dictionary<string, string>? mockResponses = null,
        CancellationToken ct = default)
    {
        var mockRuntime = new MockAgentRuntime(mockResponses ?? new());
        return await mockRuntime.RunAsync(agent, prompt, ct);
    }

    public static AgentResult Execute(Agent agent, string prompt,
        Dictionary<string, string>? mockResponses = null)
        => ExecuteAsync(agent, prompt, mockResponses).GetAwaiter().GetResult();
}
```

### FluentAssertions-Style Expect API

Custom assertion extensions provide a fluent `Expect(result).` chain. These wrap FluentAssertions underneath.

```csharp
public static class AgentAssertions
{
    public static AgentResultAssertions Expect(AgentResult result) => new(result);
}

public class AgentResultAssertions
{
    private readonly AgentResult _result;

    public AgentResultAssertions(AgentResult result) => _result = result;

    public AgentResultAssertions ToBeCompleted()
    {
        _result.Status.Should().Be(Status.Completed,
            "expected agent to complete successfully");
        return this;
    }

    public AgentResultAssertions ToBeFailed()
    {
        _result.Status.Should().Be(Status.Failed);
        return this;
    }

    public AgentResultAssertions ToContainOutput(string text)
    {
        var output = _result.Output?["result"]?.ToString() ?? "";
        output.Should().Contain(text,
            $"expected output to contain '{text}'");
        return this;
    }

    public AgentResultAssertions ToHaveUsedTool(string toolName)
    {
        _result.Events.Should().Contain(
            e => e.Type == EventType.ToolCall && e.ToolName == toolName,
            $"expected tool '{toolName}' to have been called");
        return this;
    }

    public AgentResultAssertions ToHavePassedGuardrail(string guardrailName)
    {
        _result.Events.Should().Contain(
            e => e.Type == EventType.GuardrailPass && e.GuardrailName == guardrailName,
            $"expected guardrail '{guardrailName}' to pass");
        return this;
    }

    public AgentResultAssertions ToHaveTokenUsage()
    {
        _result.TokenUsage.Should().NotBeNull("expected token usage to be tracked");
        _result.TokenUsage!.TotalTokens.Should().BeGreaterThan(0);
        return this;
    }

    public AgentResultAssertions ToHaveFinishReason(FinishReason reason)
    {
        _result.FinishReason.Should().Be(reason);
        return this;
    }
}
```

**Usage in tests:**

```csharp
public class IntakeRouterTests
{
    [Fact]
    public async Task ClassifiesTechArticle()
    {
        var result = await MockRun.ExecuteAsync(
            KitchenSink.IntakeRouter,
            "Write about quantum computing advances");

        Expect(result)
            .ToBeCompleted()
            .ToContainOutput("tech")
            .ToHaveFinishReason(FinishReason.Stop);
    }
}
```

### Record/Replay

Capture a live execution's events for deterministic replay in CI:

```csharp
public static class RecordReplay
{
    public static async Task RecordAsync(Agent agent, string prompt, string filePath,
        CancellationToken ct = default)
    {
        await using var runtime = new AgentRuntime();
        var stream = runtime.StreamAsync(agent, prompt, ct);
        var events = new List<AgentEvent>();

        await foreach (var evt in stream)
            events.Add(evt);

        var json = JsonSerializer.Serialize(events, AgentspanJson.Options);
        await File.WriteAllTextAsync(filePath, json, ct);
    }

    public static async Task<AgentResult> ReplayAsync(string filePath,
        CancellationToken ct = default)
    {
        var json = await File.ReadAllTextAsync(filePath, ct);
        var events = JsonSerializer.Deserialize<List<AgentEvent>>(json, AgentspanJson.Options)!;
        // Build result from replayed events
        var doneEvent = events.LastOrDefault(e => e.Type == EventType.Done);
        return new AgentResult
        {
            Events = events,
            Status = doneEvent is not null ? Status.Completed : Status.Failed,
            Output = doneEvent?.Output as Dictionary<string, object>,
        };
    }
}
```

### Validation Runner

The validation runner is a separate test project that reads a TOML config file and runs examples concurrently against multiple models. It follows the same structure as the Python validation framework.

```csharp
// Run via: dotnet test --filter "Category=Validation"
[Trait("Category", "Validation")]
public class ValidationRunner
{
    [Theory]
    [InlineData("kitchen_sink", "openai/gpt-4o")]
    [InlineData("kitchen_sink", "anthropic/claude-sonnet-4-20250514")]
    public async Task RunExample(string example, string model)
    {
        // Load TOML config, execute, assert
    }
}
```

---

## 9. Kitchen Sink Translation

This section translates the Python kitchen sink (`sdk/python/examples/kitchen_sink.py`) to idiomatic C#. The key stages are shown below with C#-specific patterns highlighted.

### Operator Overloads: `>>` for Pipeline, `&`/`|` for Termination

```csharp
public partial class Agent
{
    // >> creates a sequential pipeline
    public static Agent operator >>(Agent left, Agent right)
    {
        return new Agent
        {
            Name = $"{left.Name}_then_{right.Name}",
            Agents = [left, right],
            Strategy = Strategy.Sequential,
        };
    }
}

public abstract class TerminationCondition
{
    public abstract Dictionary<string, object> Serialize();

    // | for OR composition
    public static TerminationCondition operator |(TerminationCondition a, TerminationCondition b)
        => new OrTermination(a, b);

    // & for AND composition
    public static TerminationCondition operator &(TerminationCondition a, TerminationCondition b)
        => new AndTermination(a, b);
}

public class OrTermination(TerminationCondition left, TerminationCondition right) : TerminationCondition
{
    public override Dictionary<string, object> Serialize() =>
        new() { ["type"] = "or", ["conditions"] = new[] { left.Serialize(), right.Serialize() } };
}

public class AndTermination(TerminationCondition left, TerminationCondition right) : TerminationCondition
{
    public override Dictionary<string, object> Serialize() =>
        new() { ["type"] = "and", ["conditions"] = new[] { left.Serialize(), right.Serialize() } };
}
```

### Stage 1: Intake & Classification (Router, PromptTemplate, Structured Output)

```csharp
// Structured output type
public record ClassificationResult
{
    [JsonPropertyName("category")] public string Category { get; init; } = "";
    [JsonPropertyName("priority")] public int Priority { get; init; }
    [JsonPropertyName("metadata")] public Dictionary<string, object>? Metadata { get; init; }
}

// Sub-agents via fluent builder
var techClassifier = AgentBuilder.Create("tech_classifier")
    .WithModel(settings.LlmModel)
    .WithInstructions("Classifies tech articles.")
    .Build();

var businessClassifier = AgentBuilder.Create("business_classifier")
    .WithModel(settings.LlmModel)
    .WithInstructions("Classifies business articles.")
    .Build();

var creativeClassifier = AgentBuilder.Create("creative_classifier")
    .WithModel(settings.LlmModel)
    .WithInstructions("Classifies creative articles.")
    .Build();

var intakeRouter = new Agent
{
    Name = "intake_router",
    Model = settings.LlmModel,
    Instructions = new PromptTemplate("article-classifier",
        Variables: new() { ["categories"] = "tech, business, creative" }),
    Agents = [techClassifier, businessClassifier, creativeClassifier],
    Strategy = Strategy.Router,
    Router = new Agent
    {
        Name = "category_router",
        Model = settings.LlmModel,
        Instructions = "Route to the appropriate classifier based on the article topic.",
    },
    OutputType = typeof(ClassificationResult),
};
```

### Stage 3: Writing Pipeline (Sequential `>>`, Memory, Callbacks)

```csharp
var semanticMem = new SemanticMemory(maxResults: 3);
foreach (var article in MockPastArticles)
    semanticMem.Add($"Past article: {article.Title}");

// Callback handler with all 6 positions
public class PublishingCallbackHandler : CallbackHandler
{
    public override void OnAgentStart(string? agentName, Dictionary<string, object>? kwargs)
        => CallbackLog.Log("before_agent", agentName);

    public override void OnAgentEnd(string? agentName, Dictionary<string, object>? kwargs)
        => CallbackLog.Log("after_agent", agentName);

    public override void OnModelStart(List<object>? messages, Dictionary<string, object>? kwargs)
        => CallbackLog.Log("before_model", messageCount: messages?.Count ?? 0);

    public override void OnModelEnd(string? llmResult, Dictionary<string, object>? kwargs)
        => CallbackLog.Log("after_model", resultLength: llmResult?.Length ?? 0);

    public override void OnToolStart(string? toolName, Dictionary<string, object>? kwargs)
        => CallbackLog.Log("before_tool", toolName);

    public override void OnToolEnd(string? toolName, Dictionary<string, object>? kwargs)
        => CallbackLog.Log("after_tool", toolName);
}

var draftWriter = new Agent
{
    Name = "draft_writer",
    Model = settings.LlmModel,
    Instructions = "Write a comprehensive article draft based on research findings.",
    Tools = [recallPastArticlesTool],
    Memory = new ConversationMemory(maxMessages: 50),
    Callbacks = [new PublishingCallbackHandler()],
};

var editor = new Agent
{
    Name = "editor",
    Model = settings.LlmModel,
    Instructions = "Review and edit the article. Fix grammar, improve clarity. " +
                   "When done, include ARTICLE_COMPLETE.",
    StopWhen = (messages) =>
    {
        if (messages.LastOrDefault() is Dictionary<string, object> last
            && last.TryGetValue("content", out var content)
            && content?.ToString()?.Contains("ARTICLE_COMPLETE") == true)
            return true;
        return false;
    },
};

// Sequential pipeline via >> operator
var writingPipeline = draftWriter >> editor;
```

### Stage 7: Publishing Pipeline (Composable Termination, Gate)

```csharp
var publishingPipeline = new Agent
{
    Name = "publishing_pipeline",
    Model = settings.LlmModel,
    Instructions = "Manage the publishing workflow from formatting to publication.",
    Agents = [formatter, externalPublisher],
    Strategy = Strategy.Handoff,
    Handoffs =
    [
        new OnToolResult("external_publisher", "format_check"),
        new OnCondition("external_publisher", ShouldHandoffToPublisher),
    ],
    // Composable termination: OR and AND with operator overloads
    Termination =
        new TextMentionTermination("PUBLISHED")
        | (new MaxMessageTermination(50) & new TokenUsageTermination(maxTotalTokens: 100000)),
    Gate = new TextGate("APPROVED"),
};
```

### Stage 9: Execution Modes (Streaming, HITL, Async)

```csharp
const string Prompt =
    "Write a comprehensive tech article about quantum computing " +
    "advances in 2026, get it reviewed, translate to Spanish, and publish.";

if (Agentspan.IsTracingEnabled())
    Console.WriteLine("[tracing] OpenTelemetry tracing is enabled");

await using var runtime = new AgentRuntime();

// --- Deploy ---
Console.WriteLine("=== Deploy ===");
var deployments = await runtime.DeployAsync(fullPipeline);
foreach (var dep in deployments)
    Console.WriteLine($"  Deployed: {dep.WorkflowName} ({dep.AgentName})");

// --- Plan (dry-run) ---
Console.WriteLine("\n=== Plan (dry-run) ===");
var plan = await runtime.PlanAsync(fullPipeline);
Console.WriteLine("  Plan compiled successfully");

// --- Stream with HITL ---
Console.WriteLine("\n=== Stream Execution ===");
var agentStream = await runtime.StreamAsync(fullPipeline, Prompt);
Console.WriteLine($"  Execution: {agentStream.ExecutionId}\n");

var hitlState = new { Approved = 0, Rejected = 0, Feedback = 0 };

await foreach (var evt in agentStream)
{
    switch (evt.Type)
    {
        case EventType.Thinking:
            Console.WriteLine($"  [thinking] {evt.Content?[..Math.Min(80, evt.Content.Length)]}...");
            break;
        case EventType.ToolCall:
            Console.WriteLine($"  [tool_call] {evt.ToolName}({evt.Args})");
            break;
        case EventType.ToolResult:
            Console.WriteLine($"  [tool_result] {evt.ToolName} -> {evt.Result?.ToString()?[..Math.Min(80, evt.Result.ToString()!.Length)]}...");
            break;
        case EventType.Handoff:
            Console.WriteLine($"  [handoff] -> {evt.Target}");
            break;
        case EventType.GuardrailPass:
            Console.WriteLine($"  [guardrail_pass] {evt.GuardrailName}");
            break;
        case EventType.GuardrailFail:
            Console.WriteLine($"  [guardrail_fail] {evt.GuardrailName}: {evt.Content}");
            break;
        case EventType.Message:
            Console.WriteLine($"  [message] {evt.Content?[..Math.Min(80, evt.Content.Length)]}...");
            break;
        case EventType.Waiting:
            Console.WriteLine("\n  --- HITL: Approval required ---");
            if (hitlState.Feedback == 0)
            {
                await agentStream.SendAsync("Please add more details about quantum error correction.");
                Console.WriteLine("  Sent feedback (revision request)\n");
            }
            else if (hitlState.Rejected == 0)
            {
                await agentStream.RejectAsync("Title needs improvement");
                Console.WriteLine("  Rejected (title needs work)\n");
            }
            else
            {
                await agentStream.ApproveAsync();
                Console.WriteLine("  Approved\n");
            }
            break;
        case EventType.Error:
            Console.WriteLine($"  [error] {evt.Content}");
            break;
        case EventType.Done:
            Console.WriteLine("\n  [done] Pipeline complete");
            break;
    }
}

var result = await agentStream.GetResultAsync();
result.PrintResult();

// --- Token tracking ---
if (result.TokenUsage is not null)
{
    Console.WriteLine($"\nTotal tokens: {result.TokenUsage.TotalTokens}");
    Console.WriteLine($"  Prompt: {result.TokenUsage.PromptTokens}");
    Console.WriteLine($"  Completion: {result.TokenUsage.CompletionTokens}");
}

// --- Start + Polling ---
Console.WriteLine("\n=== Start + Polling ===");
var handle = await runtime.StartAsync(fullPipeline, Prompt);
Console.WriteLine($"  Started: {handle.ExecutionId}");
var status = await handle.GetStatusAsync();
Console.WriteLine($"  Status: {status.StatusValue}, Running: {status.IsRunning}");

// --- Async streaming ---
Console.WriteLine("\n=== Async Streaming ===");
var asyncStream = await runtime.StreamAsync(fullPipeline, Prompt);
await foreach (var evt in asyncStream)
{
    if (evt.Type == EventType.Done)
    {
        Console.WriteLine("  [async done] Pipeline complete");
        break;
    }
    if (evt.Type == EventType.Waiting)
        await asyncStream.ApproveAsync();
}
var asyncResult = await asyncStream.GetResultAsync();
Console.WriteLine($"  Async result status: {asyncResult.Status}");

// --- Top-level convenience ---
Console.WriteLine("\n=== Top-Level Convenience API ===");
Agentspan.Configure(AgentspanOptions.FromEnvironment());
var simpleAgent = AgentBuilder.Create("simple_test")
    .WithModel(settings.LlmModel)
    .WithInstructions("Say hello.")
    .Build();
var simpleResult = await Agentspan.RunAsync(simpleAgent, "Hello!");
Console.WriteLine($"  run() status: {simpleResult.Status}");

// --- Discover agents ---
Console.WriteLine("\n=== Discover Agents ===");
try
{
    var agents = Agentspan.DiscoverAgents("sdk/csharp/examples");
    Console.WriteLine($"  Discovered {agents.Count} agents");
}
catch (Exception ex)
{
    Console.WriteLine($"  Discovery: {ex.Message}");
}

Console.WriteLine("\n=== Kitchen Sink Complete ===");
```

### Top-Level Convenience Statics

The static `Agentspan` class mirrors Python's module-level functions (`run`, `stream`, `deploy`, etc.) by delegating to a lazily-initialized singleton runtime:

```csharp
public static class Agentspan
{
    private static AgentRuntime? _runtime;
    private static readonly object _lock = new();

    public static void Configure(AgentspanOptions options)
    {
        lock (_lock) { _runtime = new AgentRuntime(options); }
    }

    private static AgentRuntime Runtime
    {
        get
        {
            if (_runtime is null)
                lock (_lock)
                    _runtime ??= new AgentRuntime(AgentspanOptions.FromEnvironment());
            return _runtime;
        }
    }

    public static Task<AgentResult> RunAsync(Agent agent, string prompt,
        CancellationToken ct = default)
        => Runtime.RunAsync(agent, prompt, ct);

    public static AgentResult Run(Agent agent, string prompt)
        => Runtime.Run(agent, prompt);

    public static Task<AgentHandle> StartAsync(Agent agent, string prompt,
        CancellationToken ct = default)
        => Runtime.StartAsync(agent, prompt, ct);

    public static Task<IAgentStream> StreamAsync(Agent agent, string prompt,
        CancellationToken ct = default)
        => Runtime.StreamAsync(agent, prompt, ct);

    public static Task<DeploymentInfo> DeployAsync(Agent agent,
        CancellationToken ct = default)
        => Runtime.DeployAsync(agent, ct);

    public static Task<object> PlanAsync(Agent agent,
        CancellationToken ct = default)
        => Runtime.PlanAsync(agent, ct);

    public static bool IsTracingEnabled()
        => Environment.GetEnvironmentVariable("OTEL_EXPORTER_OTLP_ENDPOINT") is not null;

    public static List<Agent> DiscoverAgents(string path)
        => Runtime.DiscoverAgents(path);

    public static void Shutdown()
    {
        lock (_lock)
        {
            _runtime?.Dispose();
            _runtime = null;
        }
    }
}
```

### Full Pipeline Composition

The full pipeline mirrors the Python reference exactly -- a hierarchical agent tree with all 8 stages composed under a top-level sequential orchestrator:

```csharp
var fullPipeline = new Agent
{
    Name = "content_publishing_platform",
    Model = settings.LlmModel,
    Instructions =
        "You are a content publishing platform. Process article requests " +
        "through all pipeline stages: classification, research, writing, " +
        "review, editorial approval, translation, publishing, and analytics.",
    Agents =
    [
        intakeRouter,          // Stage 1 - Router
        researchTeam,          // Stage 2 - Parallel
        writingPipeline,       // Stage 3 - Sequential (>>)
        reviewAgent,           // Stage 4 - Guardrails
        editorialAgent,        // Stage 5 - HITL
        translationSwarm,      // Stage 6 - Swarm
        publishingPipeline,    // Stage 7 - Handoff
        analyticsAgent,        // Stage 8 - Code + Media + RAG
    ],
    Strategy = Strategy.Sequential,
    Termination =
        new TextMentionTermination("PIPELINE_COMPLETE")
        | new MaxMessageTermination(200),
};
```

This produces an identical `AgentConfig` JSON tree to the Python version, satisfying the primary correctness criterion defined in the base spec.
