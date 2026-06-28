# Advanced

- [Runtime initialization and options](#runtime-initialization-and-options)
- [Worker tuning](#worker-tuning)
- [The AgentClient control plane](#the-agentclient-control-plane)
- [Deploy vs serve vs run vs plan](#deploy-vs-serve-vs-run-vs-plan)
- [Schedules](#schedules)
- [Structured output](#structured-output)
- [Credentials and secrets](#credentials-and-secrets)
- [Plans and PLAN_EXECUTE](#plans-and-plan_execute)

## Runtime initialization and options

`new AgentRuntime()` reads connection settings from the environment
(`AGENTSPAN_SERVER_URL`, `AGENTSPAN_AUTH_KEY`, `AGENTSPAN_AUTH_SECRET`). Override
any of them with `AgentRuntimeOptions`:

```csharp
await using var runtime = new AgentRuntime(new AgentRuntimeOptions
{
    ServerUrl  = "https://my-server.example.com/api",
    AuthKey    = "...",     // optional; with AuthSecret enables Orkes auth (JWT exchange)
    AuthSecret = "...",
});
```

When both `AuthKey` and `AuthSecret` are set, the runtime configures Orkes
authentication for worker polling automatically. With neither set, it runs in
no-auth mode (local / OSS Conductor).

The runtime is both `IAsyncDisposable` and `IDisposable`; `await using` (or
`using`) shuts down any local tool workers it started.

## Worker tuning

Local `[Tool]` methods are served by worker poll loops the runtime owns. Two
environment variables tune them (read once at construction):

| Variable | Default | Meaning |
|---|---|---|
| `AGENTSPAN_WORKER_THREADS` | `1` | Worker threads per task type. |
| `AGENTSPAN_WORKER_POLL_INTERVAL` | `100` | Poll interval in milliseconds. |

```csharp
using var runtime = new AgentRuntime();
int threads = runtime.WorkerThreadCount;     // reflects AGENTSPAN_WORKER_THREADS
int pollMs  = runtime.WorkerPollIntervalMs;  // reflects AGENTSPAN_WORKER_POLL_INTERVAL
```

## The AgentClient control plane

`AgentClient` is the control-plane client for the `/agent/*` API (compile, deploy,
start, status, respond, stream) plus convenience `RunAsync` / `StartAsync` /
`DeployAsync` / `ScheduleAsync`. It was previously named `AgentHttpClient`.

The runtime exposes its own client as `runtime.Client`:

```csharp
await using var runtime = new AgentRuntime();
AgentClient client = runtime.Client;
```

**Run is control-plane only.** `client.RunAsync(...)` starts the agent and polls to
a result but does **not** register or poll local tool workers. Use it for LLM-only
agents, agents with server-side tools (HTTP/MCP/media/RAG), or pre-deployed
workflows. Agents with local `[Tool]` functions must run through `AgentRuntime`,
which owns worker orchestration.

```csharp
// control-plane run (no local workers)
var result = await runtime.Client.RunAsync(llmOnlyAgent, "Summarize this.");

// or stand up a client directly
using var standalone = new AgentClient("http://localhost:6767/api");
var handle = await standalone.StartAsync(agent, "Hello");
```

`AgentClient` also exposes lower-level helpers used by the runtime:
`CompileAsync`, `GetStatusAsync`, `GetExecutionAsync`, `RespondAsync`,
`StreamEventsAsync`, `StartWorkflowByNameAsync`, `SendWorkflowMessageAsync`,
`StopAgentAsync`, `CancelAgentAsync`, and `ResolveCredentialsAsync`.

## Deploy vs serve vs run vs plan

These are the four ways to get an agent onto the server, ordered roughly from
"just run it" to "CI/CD pipeline":

| Verb | What it does | When |
|---|---|---|
| `RunAsync` / `StartAsync` | Compile + register + start (+ host local workers), then wait or stream. | Day-to-day execution. |
| `DeployAsync` | Compile + register the workflow on the server. No execution, no workers. | CI/CD: push agent definitions. |
| `ServeAsync` | Register local tool workers for already-deployed agents and block until cancelled. | Long-running worker service. |
| `PlanAsync` / `Plan` | Compile to a Conductor `WorkflowDef` and return it. No registration, no execution. | Inspect/debug/validate the compiled workflow. |

**Deploy** (returns one `DeploymentInfo` per agent):

```csharp
var results = await runtime.DeployAsync(docAssistant, opsBot);
foreach (var info in results)
    Console.WriteLine($"{info.AgentName} -> {info.RegisteredName}");
```

**Serve** a deployed agent's local tools (blocks until the token is cancelled):

```csharp
using var cts = new CancellationTokenSource();
Console.CancelKeyPress += (_, e) => { e.Cancel = true; cts.Cancel(); };

await using var runtime = new AgentRuntime();
await runtime.ServeAsync(cts.Token, docAssistant);   // params Agent[]
```

**Run a pre-deployed agent by name** (no agentConfig payload, no local workers
unless you also serve them):

```csharp
var handle = await runtime.StartByNameAsync(agent.Name, "Validate change CHG-901.");
var result = await runtime.RunByNameAsync(agent.Name, "Validate change CHG-901.");
```

A common deploy-then-serve recovery pattern:

```csharp
await runtime.DeployAsync(agent);
var handle = await runtime.StartByNameAsync(agent.Name, prompt);

using var cts = new CancellationTokenSource();
var serveTask = runtime.ServeAsync(cts.Token, agent);   // worker service comes up after start
// ... poll runtime.GetStatusAsync(handle.ExecutionId) until complete ...
cts.Cancel();
var result = await handle.WaitAsync();
```

**Plan** (dry-run compile):

```csharp
var workflowDef = await runtime.PlanAsync(agent);   // JsonNode? — the compiled WorkflowDef
```

## Schedules

Cron triggers attach to a deployed agent. The lifecycle API is `runtime.Schedules`
(equivalently `runtime.Client.Schedules`).

```csharp
using Conductor.AI.Scheduling;

var agent = new Agent("eng_digest") { Model = "anthropic/claude-sonnet-4-6", Instructions = "..." };

// Declarative deploy: upsert these schedules, prune any others for this agent.
await runtime.DeployAsync(agent, new[]
{
    new Schedule
    {
        Name        = "weekday-9am",
        Cron        = "0 0 9 * * MON-FRI",          // 6-field Quartz (seconds precision)
        Timezone    = "America/Los_Angeles",
        Input       = new Dictionary<string, object?> { ["channel"] = "#eng" },
        Description = "Weekday morning digest",
    },
});
```

`DeployAsync(agent, schedules)` reconciliation semantics: `null` leaves existing
schedules untouched, an **empty** collection purges all schedules for the agent,
and a **non-empty** collection upserts those and prunes the rest. (Pass
`Array.Empty<Schedule>()` to clear.) Schedule `Name`s are unique per agent; the
SDK prefixes the wire name as `{agent}-{name}`.

Manage individual schedules (operations are keyed by the **wire name** returned by
`ListAsync`):

```csharp
IReadOnlyList<ScheduleInfo> infos = await runtime.Schedules.ListAsync(agent.Name);
var wire = infos[0].Name;

await runtime.Schedules.PauseAsync(wire, reason: "cooldown");
var info = await runtime.Schedules.GetAsync(wire);
await runtime.Schedules.ResumeAsync(wire);
string execId = await runtime.Schedules.RunNowAsync(info);
IReadOnlyList<long> nextFires = await runtime.Schedules.PreviewNextAsync("0 0 9 * * MON-FRI", n: 5);
await runtime.Schedules.DeleteAsync(wire);
```

You can also deploy + reconcile in one call on the client:
`await runtime.Client.ScheduleAsync(agent, schedules)`.

## Structured output

Set `Agent.OutputType` to a C# type. The server enforces the JSON schema and the
typed object lands in `result.Output["result"]` as JSON. Use `AgentBuilder` with
`.WithOutputType<T>()`, or the field directly.

```csharp
internal record WeatherReport(
    [property: JsonPropertyName("city")]           string City,
    [property: JsonPropertyName("temperature")]    double Temperature,
    [property: JsonPropertyName("condition")]      string Condition,
    [property: JsonPropertyName("recommendation")] string Recommendation);

var agent = new Agent("weather_reporter")
{
    Model      = "anthropic/claude-sonnet-4-6",
    Tools      = ToolRegistry.FromInstance(new WeatherTools()),
    OutputType = typeof(WeatherReport),
};

var result = await runtime.RunAsync(agent, "What's the weather in NYC?");

if (result.Output?.TryGetValue("result", out var raw) == true && raw is not null)
{
    var jsonStr = raw is JsonElement je
        ? (je.ValueKind == JsonValueKind.String ? je.GetString() : je.GetRawText())
        : raw.ToString();
    var report = JsonSerializer.Deserialize<WeatherReport>(jsonStr!, AgentspanJson.Options);
}
```

> `AgentspanJson.Options` is the SDK's shared `JsonSerializerOptions`
> (camelCase, snake_case enums) — handy when deserializing agent output yourself.

## Credentials and secrets

Tools declare the credential names they need; the server resolves them at run time
and injects them so the value never lives in your agent definition. Reference a
secret with the `${NAME}` placeholder in HTTP/MCP/API headers, or list names on a
`[Tool]`.

Server-side HTTP tool — the placeholder is filled in by the server when it makes
the call:

```csharp
var listRepos = HttpTools.Create(
    name:        "list_github_repos",
    description: "List public GitHub repositories for a user.",
    url:         "https://api.github.com/users/agentspan-ai/repos?per_page=5",
    headers:     new()
    {
        ["Authorization"]        = "Bearer ${GITHUB_TOKEN}",
        ["X-GitHub-Api-Version"] = "2022-11-28",
        ["User-Agent"]           = "agentspan-sdk",
    },
    credentials: ["GITHUB_TOKEN"]);
```

Local `[Tool]` worker — names listed in `Credentials` are resolved and made
available to the tool process for the call:

```csharp
[Tool("List public repositories for a GitHub user.", Credentials = ["GITHUB_TOKEN"])]
public async Task<Dictionary<string, object>> ListGithubRepos(string username, ToolContext? ctx = null)
{
    var token = Environment.GetEnvironmentVariable("GITHUB_TOKEN") ?? "";
    // ...
}
```

The same `${NAME}` mechanism applies to `McpTools`, `ApiTools`, `CliTool`, and to
PLAN_EXECUTE `Context.FromUrl(...)` headers. Programmatic resolution is available
via `runtime.Client.ResolveCredentialsAsync(executionToken, names)` (it throws
`CredentialNotFoundException` / `CredentialAuthException` /
`CredentialRateLimitException` / `CredentialServiceException` rather than silently
returning empty values).

## Plans and PLAN_EXECUTE

`Strategy.PlanExecute` builds a plan-and-compile harness: a `Planner` agent
produces a JSON plan that the server executes deterministically, with an optional
`Fallback` agent for recovery.

```csharp
var planner = new Agent("planner") { Model = "anthropic/claude-sonnet-4-6", Instructions = "..." };

var harness = new Agent("onboarding")
{
    Model    = "anthropic/claude-sonnet-4-6",
    Strategy = Strategy.PlanExecute,
    Planner  = planner,
    Fallback = fallback,            // optional; absent => plan failures terminate
    FallbackMaxTurns = 3,
    Tools    = ToolRegistry.FromInstance(new OnboardingTools()),
};
```

**Planner context** grounds the planner in domain rules on every invocation —
inline text and/or fetched URLs (with credentialed headers). Only valid with
`Strategy.PlanExecute`:

```csharp
using Conductor.AI.Plans;

harness.PlannerContext =
[
    Context.FromText("Onboarding phases in order: validate_kyc, create_account, send_welcome_email."),
    Context.FromUrl("https://docs.example.com/onboarding.md",
        headers: new() { ["Authorization"] = "Bearer ${CONFLUENCE_TOKEN}" },
        required: true, maxBytes: 8192),
];
// builder: .WithPlannerContext("rule one", "rule two") or .WithPlannerContext(Context.FromUrl(...))
```

**Supplying a deterministic plan** skips the planner LLM entirely. Build a `Plan`
of `Step`s; wire one step's whole output into another with `new Ref("step_id")`
(the referenced step must be in `DependsOn`). Pass it to `RunAsync(..., plan: ...)`:

```csharp
using Conductor.AI.Plans;

var plan = new Plan
{
    Steps =
    {
        new Step("produce")
        {
            Operations = { new Op("produce", new() { ["record_id"] = "r-001" }) },
        },
        new Step("enrich")
        {
            DependsOn  = { "produce" },
            Operations = { new Op("enrich", new() { ["record"] = new Ref("produce") }) },
        },
        new Step("report")
        {
            DependsOn  = { "produce", "enrich" },
            Operations =
            {
                new Op("report", new()
                {
                    ["record"]   = new Ref("produce"),
                    ["enriched"] = new Ref("enrich"),
                }),
            },
        },
    },
};

var result = await runtime.RunAsync(harness, "demo", plan: plan);
```

An `Op` either calls a tool with literal `Args` (as above) or generates its args
at run time with an LLM via `Op.WithGenerate(tool, new Generate { Instructions = ..., OutputSchema = ... })`.
A `Plan` may also carry top-level `Validation`, `OnSuccess`, and `OnFailure`
actions.

The simpler `Agent.EnablePlanning = true` is unrelated: it just augments the
system prompt with a "plan first, then execute" preamble (a Google ADK feature),
without the PLAN_EXECUTE harness.
</content>
