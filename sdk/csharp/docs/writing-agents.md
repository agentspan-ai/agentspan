# Writing Agents

Everything you need to author agents with the native Agentspan API. For agents
written against the OpenAI / Google ADK / Semantic Kernel shapes, see
[framework-agents.md](framework-agents.md).

- [Defining an agent](#defining-an-agent)
- [Instructions](#instructions)
- [Tools](#tools)
- [Multi-agent strategies and pipelines](#multi-agent-strategies-and-pipelines)
- [Handoffs](#handoffs)
- [Guardrails](#guardrails)
- [Termination](#termination)
- [Text gates](#text-gates)
- [Callbacks](#callbacks)
- [Streaming](#streaming)
- [Human-in-the-loop](#human-in-the-loop)
- [Schedules](#schedules)
- [Agents from methods (`[AgentDef]`)](#agents-from-methods-agentdef)
- [Stateful agents](#stateful-agents)

## Defining an agent

`Agent` is the single orchestration primitive — an LLM with optional tools and/or
sub-agents. The name must match `^[a-zA-Z_][a-zA-Z0-9_-]*$`.

Object-initializer style:

```csharp
var agent = new Agent("assistant")
{
    Model        = "openai/gpt-4o-mini",
    Instructions = "You are helpful.",
    Tools        = tools,             // optional: List<ToolDef>
    Agents       = [subAgent],        // optional: sub-agents (multi-agent)
    Strategy     = Strategy.Handoff,  // required when Agents is non-empty
    MaxTurns     = 10,                // optional
    Temperature  = 0.2,               // optional
    MaxTokens    = 2048,              // optional
};
```

Fluent builder style (`AgentBuilder`):

```csharp
var agent = AgentBuilder.Create("assistant")
    .WithModel("openai/gpt-4o-mini")
    .WithInstructions("You are helpful.")
    .WithTools(tools.ToArray())
    .WithMaxTurns(10)
    .Build();
```

`Build()` throws `ConfigurationException` if sub-agents are present but no `Strategy` is set.

## Instructions

A static system prompt:

```csharp
var agent = new Agent("a") { Instructions = "You are helpful." };
```

Dynamic instructions — a `Func<string>` re-evaluated every time the agent is
submitted to the server, so the prompt can reflect current state (date, flags,
fetched context). `InstructionsFn` takes precedence over `Instructions`:

```csharp
var agent = new Agent("a")
{
    InstructionsFn = () => $"You are helpful. Today is {DateTime.UtcNow:yyyy-MM-dd}.",
};

// builder:
AgentBuilder.Create("a").WithInstructions(() => $"Today is {DateTime.UtcNow:d}").Build();
```

Server-side prompt templates are also supported via `PromptTemplate`:

```csharp
agent.PromptTemplateInstructions =
    new PromptTemplate("support_prompt", Variables: new() { ["tone"] = "warm" });
```

## Tools

### `[Tool]` methods + `ToolRegistry.FromInstance`

Decorate public methods with `[Tool]` and scan an instance. Method names become
`snake_case` tool names (`GetWeather` → `get_weather`). Parameters become the
input schema; a `ToolContext` parameter (if present) is injected, not exposed to
the LLM.

```csharp
internal sealed class WeatherTools
{
    [Tool("Get the current weather for a city.")]
    public Dictionary<string, object> GetWeather(string city)
        => new() { ["city"] = city, ["temp_f"] = 72, ["condition"] = "Sunny" };

    [Tool("Send an email.", ApprovalRequired = true, TimeoutSeconds = 60)]
    public Dictionary<string, object> SendEmail(string to, string subject, string body)
        => new() { ["sent"] = true };
}

var tools = ToolRegistry.FromInstance(new WeatherTools());
var agent = new Agent("assistant") { Tools = tools };
```

`[Tool]` attribute knobs: `Name`, `Description`, `ApprovalRequired`, `External`,
`TimeoutSeconds`, `Credentials` (string[]), `Stateful`, `RetryCount` (default 2),
`RetryDelaySeconds` (default 2), `RetryPolicy` (`"fixed"` / `"linear_backoff"` /
`"exponential_backoff"`). Local `[Tool]` methods run in a worker the runtime
hosts for you — so agents with local tools must run via `AgentRuntime`, not the
bare `AgentClient`.

Mix scanned tools with built-ins via list spreads:

```csharp
var agent = new Agent("a") { Tools = [.. tools, httpTool, askUser] };
```

### Custom tool defs without attributes

```csharp
var t = ToolDefFactory.Create(
    name:        "submit_answer",
    description: "Submit the final answer.",
    handler:     (args, ctx) => new { ok = true });   // sync or async
```

### Built-in tool factories

All of the following are server-side (no local worker process) unless noted.

**HTTP** — the Conductor server makes the call:

```csharp
var reverse = HttpTools.Create(
    name:        "reverse_string",
    description: "Reverse a string via the HTTP API.",
    url:         "http://localhost:3001/api/string/reverse",
    method:      "POST",
    headers:     new() { ["Authorization"] = "Bearer ${HTTP_TEST_API_KEY}" },
    credentials: ["HTTP_TEST_API_KEY"]);
```

**MCP** — tools discovered from an MCP server:

```csharp
var mcp = McpTools.Create(
    serverUrl:   "http://localhost:3001/mcp",
    name:        "weather_mcp",
    description: "Weather tools via MCP.",
    headers:     new() { ["Authorization"] = "Bearer ${MCP_TEST_API_KEY}" },
    credentials: ["MCP_TEST_API_KEY"]);
```

**HumanTool** — pauses the workflow for human input when the LLM calls it:

```csharp
var askUser = HumanTool.Create(
    name:        "ask_user",
    description: "Ask the user a question when you need clarification.");
```

**MediaTools** — image / audio / video / PDF generation:

```csharp
var image = MediaTools.Image("generate_image", "Generate an image.", llmProvider: "openai", model: "dall-e-3");
var audio = MediaTools.Audio("text_to_speech", "Convert text to speech.", llmProvider: "openai", model: "tts-1");
var video = MediaTools.Video("generate_video", "Generate a video.", llmProvider: "...", model: "...");
var pdf   = MediaTools.Pdf();   // generate_pdf from markdown; sensible defaults
```

> `PdfTool` is `MediaTools.Pdf(...)`.

**WaitForMessageTool** — dequeues messages from the Workflow Message Queue
(server-side). Pair with `runtime.SendMessageAsync(...)` and `Stateful = true`
(see [Stateful agents](#stateful-agents)):

```csharp
var receive = WaitForMessageTool.Create(
    name: "wait_for_message",
    description: "Wait for the next external message, then return its content.");
```

**AgentTool** — wrap an `Agent` as a callable tool (runs as a sub-workflow, called
inline like a function — distinct from handoff delegation):

```csharp
var manager = new Agent("manager")
{
    Tools = [ AgentTool.Create(researcher), .. ToolRegistry.FromInstance(new CalculatorTools()) ],
};
```

**RagTools** — vector-DB index and search (server-side embedding + storage):

```csharp
var index  = RagTools.Index("index_docs", "Index documents.",
                vectorDb: "pinecone", index: "kb",
                embeddingModelProvider: "openai", embeddingModel: "text-embedding-3-small");
var search = RagTools.Search("search_docs", "Search the knowledge base.",
                vectorDb: "pinecone", index: "kb",
                embeddingModelProvider: "openai", embeddingModel: "text-embedding-3-small",
                maxResults: 5);
```

Other built-ins: `ApiTools.Create(...)` (tools from an OpenAPI/Swagger/Postman
spec) and `CliTool.Create(...)` (a local `run_command` worker tool with a command
whitelist).

## Multi-agent strategies and pipelines

Set `Agents` and a `Strategy`. Strategies:

| Strategy | Behavior |
|---|---|
| `Handoff` | Parent LLM delegates to a sub-agent. |
| `Sequential` | Agents run in order; each output feeds the next. |
| `Parallel` | All sub-agents run concurrently; results aggregated. |
| `Router` | A dedicated `Router` agent classifies and routes to one specialist. |
| `RoundRobin` | Sub-agents take turns. |
| `Random` | A sub-agent is picked at random. |
| `Swarm` | Collaborative swarm with handoff triggers. |
| `Manual` | Caller selects the next agent. |
| `PlanExecute` | Plan-and-execute harness (see [advanced.md](advanced.md)). |

Handoff team:

```csharp
var support = new Agent("support")
{
    Model        = "openai/gpt-4o-mini",
    Instructions = "Route requests to the right specialist: billing, technical, or sales.",
    Agents       = [billingAgent, technicalAgent, salesAgent],
    Strategy     = Strategy.Handoff,
};
```

Router with a dedicated classifier:

```csharp
var team = new Agent("dev_team")
{
    Agents   = [planner, coder, reviewer],
    Strategy = Strategy.Router,
    Router   = selector,   // a classifier Agent
};
```

Sequential pipeline with the `>>` operator (equivalent to a `Strategy.Sequential`
parent over `[a, b, c]`):

```csharp
var pipeline = researcher >> writer >> editor;
var result   = await runtime.RunAsync(pipeline, "AI agents in 2025");
```

Constrain who may transition to whom with `AllowedTransitions`:

```csharp
var team = new Agent("code_review")
{
    Agents   = [developer, reviewer, approver],
    Strategy = Strategy.RoundRobin,
    MaxTurns = 6,
    AllowedTransitions = new()
    {
        ["developer"] = ["reviewer"],
        ["reviewer"]  = ["developer", "approver"],
        ["approver"]  = ["developer"],
    },
};
```

## Handoffs

In a `Swarm`, `Handoff` triggers transfer control to another agent when no
explicit transfer tool was called. Build them with the three trigger types and
attach via `Agent.Handoffs` (or `.WithHandoffs(...)`):

```csharp
var agent = new Agent("triage")
{
    Strategy = Strategy.Swarm,
    Agents   = [refundSpecialist, supervisor],
    Handoffs =
    [
        OnTextMention.Of("refund", "refund_specialist"),
        OnToolResult.Of("check_eligibility", "refund_specialist", "eligible"),
        new OnCondition("supervisor",
            ctx => ctx.TryGetValue("result", out var r) && (r?.ToString()?.Length ?? 0) > 500),
    ],
};
```

- `OnTextMention.Of(text, target)` — fires when the agent output contains `text`.
- `OnToolResult.Of(toolName, target)` / `OnToolResult.Of(toolName, target, resultContains)` — fires when a tool returns (optionally containing a substring).
- `new OnCondition(target, predicate)` — fires when your predicate over the context map returns true. The context carries `result`, `messages`, `tool_name`, `tool_result`.

## Guardrails

Guardrails validate input or output and can retry, raise, fix, or escalate to a
human. `Position` is `Input` or `Output`; `OnFail` is `Retry`, `Raise`, `Fix`, or
`Human`.

`[Guardrail]` methods + `GuardrailRegistry.FromInstance`:

```csharp
internal sealed class PiiGuardrails
{
    [Guardrail(Position = Position.Output, OnFail = OnFail.Retry, MaxRetries = 3)]
    public GuardrailResult NoPii(string content)
    {
        if (CcPattern.IsMatch(content) || SsnPattern.IsMatch(content))
            return new GuardrailResult(false, "Redact card numbers and SSNs before responding.");
        return new GuardrailResult(true);
    }
}

var agent = new Agent("support_agent")
{
    Guardrails = GuardrailRegistry.FromInstance(new PiiGuardrails()),
};
```

Regex guardrail (`mode: "block"` fails on a match, `"allow"` fails when nothing matches):

```csharp
var noEmails = RegexGuardrail.Create(
    pattern:    @"[\w.+\-]+@[\w\-]+\.[\w.\-]+",
    mode:       "block",
    name:       "no_email_addresses",
    message:    "Response must not contain email addresses.",
    position:   Position.Output,
    onFail:     OnFail.Retry,
    maxRetries: 3);
```

LLM guardrail — a model judges content against a policy and returns `{passed, reason}`:

```csharp
var safety = LLMGuardrail.Create(
    model:  "openai/gpt-4o-mini",
    policy: "Reject medical/legal advice presented as fact, guarantees, or PII.",
    name:   "content_safety",
    position: Position.Output,
    onFail:   OnFail.Retry);
```

Scope a guardrail to a single tool (input or output of that tool):

```csharp
var t = someToolDef.WithGuardrails(noEmails);
```

## Termination

Composable stop conditions on `Agent.Termination`. Combine with `&` (AND) and `|` (OR).

```csharp
var agent = new Agent("researcher")
{
    Termination = new TextMentionTermination("DONE"),
};

// composed
var term = new MaxMessageTermination(10) | new TextMentionTermination("DONE");
var budget = new TokenUsageTermination(maxTotalTokens: 50_000);
```

Available: `TextMentionTermination`, `StopMessageTermination`,
`MaxMessageTermination`, `TokenUsageTermination`, and the `AndTermination` /
`OrTermination` composites produced by the operators.

## Text gates

A `TextGate` stops a sequential pipeline after the agent if its output contains
the sentinel text (compiled server-side, no worker round-trip):

```csharp
var checker = new Agent("checker") { Model = "openai/gpt-4o", Gate = new TextGate("STOP") };
var fixer   = new Agent("fixer")   { Model = "openai/gpt-4o" };
var pipeline = checker >> fixer;   // halts after checker if its output contains "STOP"
```

`new TextGate(text, caseSensitive: true)` — set `caseSensitive: false` to match loosely.

## Callbacks

Two equivalent ways to hook the lifecycle.

**Inline delegate fields** — quick, per-agent:

```csharp
var agent = new Agent("monitored")
{
    BeforeModelCallback = messages =>
    {
        Console.WriteLine($"[before_model] sending {messages?.Count ?? 0} messages");
        return [];   // empty dict = continue normally; non-empty = skip the LLM / override
    },
    AfterModelCallback = llmResult =>
    {
        Console.WriteLine($"[after_model] {llmResult?.Length ?? 0} chars");
        return [];   // empty = keep response; non-empty = override
    },
};
```

There are six delegate slots: `BeforeAgentCallback` / `AfterAgentCallback`,
`BeforeModelCallback` / `AfterModelCallback`, `BeforeToolCallback` /
`AfterToolCallback`. (The before/after-agent/tool variants take a
`Dictionary<string, JsonElement>` kwargs map.)

**`CallbackHandler` subclasses** — composable, reusable across agents. Override
only the hooks you care about; register a list via `Agent.Callbacks`. Handlers run
in list order and the first non-empty return short-circuits.

```csharp
internal sealed class ToolStartLogger : CallbackHandler
{
    public override Dictionary<string, object>? OnToolStart(Dictionary<string, JsonElement> kwargs)
    {
        Console.WriteLine("[before_tool]");
        return null;   // observe only
    }
}

var agent = new Agent("a") { Callbacks = [new ToolStartLogger()] };
// or: AgentBuilder.Create("a").WithCallbacks(new ToolStartLogger()).Build();
```

Hooks: `OnAgentStart` / `OnAgentEnd` / `OnModelStart` / `OnModelEnd` /
`OnToolStart` / `OnToolEnd`.

## Streaming

`StartAsync` returns an `AgentHandle`; iterate its `StreamAsync()`, or use
`runtime.StreamAsync(agent, prompt)` directly:

```csharp
await using var runtime = new AgentRuntime();

await foreach (var ev in runtime.StreamAsync(agent, "Write a haiku about C#."))
{
    switch (ev.Type)
    {
        case EventType.Thinking:    Console.WriteLine($"[thinking] {ev.Content}"); break;
        case EventType.ToolCall:    Console.WriteLine($"[tool_call] {ev.ToolName}({ev.Args})"); break;
        case EventType.ToolResult:  Console.WriteLine($"[tool_result] {ev.ToolName} -> {ev.Result}"); break;
        case EventType.Handoff:     Console.WriteLine($"[handoff] -> {ev.Target}"); break;
        case EventType.Waiting:     Console.WriteLine("[waiting...]"); break;
        case EventType.Done:        Console.WriteLine($"Done: {ev.Content} ({ev.Status})"); break;
        case EventType.Error:       Console.WriteLine($"[error] {ev.Content}"); break;
    }
}
```

Event types: `Thinking`, `ToolCall`, `ToolResult`, `GuardrailPass`,
`GuardrailFail`, `Waiting`, `Handoff`, `Message`, `Error`, `Done`.

## Human-in-the-loop

When a tool has `ApprovalRequired = true` (or the agent calls `HumanTool`), the
execution emits a `Waiting` event and pauses. Respond via the handle.

```csharp
var handle = await runtime.StartAsync(agent, prompt);

await foreach (var ev in handle.StreamAsync())
{
    if (ev.Type == EventType.Waiting)
    {
        await handle.ApproveAsync();                 // approve
        // await handle.ApproveAsync("looks good");  // approve with a comment
        // await handle.RejectAsync("not authorized");
    }
}
```

For a `HumanTool` question, read the pending tool args and send a structured reply:

```csharp
case EventType.Waiting:
    var status = await handle.GetStatusAsync();
    var pending = status.PendingTool ?? new();
    // ...read pending["args"] for the question...
    await handle.RespondAsync(new { answer = Console.ReadLine() });
    break;
```

**Event-targeted HITL.** Under multi-agent strategies the HUMAN task can live in a
sub-execution, so respond to the *event's* execution, not the root. Pass the
`Waiting` event itself:

```csharp
await handle.ApproveAsync(ev);                 // targets ev.ExecutionId
await handle.RejectAsync(ev, "reason");
await handle.RespondAsync(ev, new { answer = "..." });
// the same overloads exist on runtime: runtime.ApproveAsync(ev), runtime.RejectAsync(ev, reason)
```

**Polling instead of streaming.** Wait for the pause without a stream:

```csharp
if (await handle.WaitUntilWaitingAsync(TimeSpan.FromSeconds(30)))
    await handle.ApproveAsync();
// also: await handle.IsWaitingAsync()
```

Stop or cancel a running execution:

```csharp
await handle.StopAsync();           // graceful: finishes the current step, COMPLETED
await handle.CancelAsync("reason"); // immediate: TERMINATED
```

## Schedules

Attach cron triggers to a deployed agent. See [advanced.md](advanced.md#schedules)
for the full lifecycle API; the short version:

```csharp
using Conductor.AI.Scheduling;

await runtime.DeployAsync(agent, schedules:
[
    new Schedule { Name = "daily", Cron = "0 0 9 * * ?", Timezone = "America/New_York" },
]);
```

`Cron` is a 6-field Quartz expression (seconds precision). Names are unique per
agent; the SDK prefixes the wire name as `{agent}-{name}`.

## Agents from methods (`[AgentDef]`)

Define agents declaratively on a host object. `[Tool]` / `[Guardrail]` methods on
the same object are attached automatically (filter with the `Tools` / `Guardrails`
properties). A `[AgentDef]` method may return `void` (attribute-only), `string` (a
no-arg method becomes dynamic instructions), or `Agent` (a full factory).

```csharp
internal sealed class AgentHost
{
    [Tool("Greet the user.")]
    public Dictionary<string, object> SayHi() => new() { ["greeting"] = "hello" };

    // returns string -> becomes InstructionsFn; attaches only the say_hi tool
    [AgentDef(Name = "greeter", Tools = new[] { "say_hi" })]
    public string Greeter() => "Be friendly.";

    // void -> defined entirely by the attribute; wires greeter as a sub-agent
    [AgentDef(Name = "coordinator", Tools = new string[0],
              Agents = new[] { "greeter" }, Strategy = Strategy.Sequential)]
    public void Coordinator() { }
}

var host = new AgentHost();

List<Agent> all   = Agent.FromInstance(host);          // all [AgentDef] methods
Agent       one   = Agent.FromInstance(host, "greeter"); // a single one by name
one.Model = "openai/gpt-4o-mini";                       // supply a model if the attribute left it unset

await using var runtime = new AgentRuntime();
await runtime.RunAsync(one, "Greet the user by calling say_hi.");
```

`[AgentDef]` properties: `Name`, `Model`, `Instructions`, `Tools` (`["*"]` = all,
`[]` = none, or names), `Guardrails`, `Agents` (sub-agent names), `Strategy`,
`MaxTurns`, `MaxTokens`, `Temperature`.

## Stateful agents

Set `Stateful = true` to pin every worker task for an execution to one worker
process (domain-based routing). This is required when a `WaitForMessageTool` runs
alongside local tools, so the worker that waits for messages is the same one that
receives them. Drive it with `StartAsync` + `SendMessageAsync`:

```csharp
var receive = WaitForMessageTool.Create(name: "wait_for_message",
    description: "Wait for the next external message, then return its content.");

var agent = new Agent("listener")
{
    Model    = "openai/gpt-4o-mini",
    Stateful = true,
    MaxTurns = 10_000,
    Tools    = [receive, .. ToolRegistry.FromInstance(new ActionTools())],
    Instructions = "Loop: wait_for_message, act on it, repeat until told to stop.",
};

await using var runtime = new AgentRuntime();
var handle = await runtime.StartAsync(agent, "Start listening.");

await runtime.SendMessageAsync(handle.ExecutionId, new { action = "generate-report" });
// ...
await handle.StopAsync();
var result = await handle.WaitAsync();
```

`WaitForMessageTool` requires `conductor.workflow-message-queue.enabled=true` on
the server. A per-tool `[Tool(Stateful = true)]` flag (or `ToolDef.Stateful`) also
marks the parent agent stateful. Reattach to a durable execution across process
restarts with `runtime.ResumeAsync(executionId, agent)`.
</content>
