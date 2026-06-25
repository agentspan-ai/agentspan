# API Reference

The public surface of the `Agentspan` package, one section per type. Snippets in
the other docs show usage; this is the lookup table.

- [AgentRuntime](#agentruntime)
- [AgentRuntimeOptions](#agentruntimeoptions)
- [Agent](#agent)
- [AgentBuilder](#agentbuilder)
- [Strategy](#strategy)
- [Tools: ToolDef and built-ins](#tools-tooldef-and-built-ins)
- [Guardrails](#guardrails)
- [TerminationCondition](#terminationcondition)
- [Handoff](#handoff)
- [TextGate](#textgate)
- [CallbackHandler](#callbackhandler)
- [Schedule / Schedules](#schedule--schedules)
- [Plans](#plans)
- [Results: AgentResult, AgentHandle, AgentEvent, AgentStatus](#results)
- [AgentClient](#agentclient)
- [Exceptions](#exceptions)

## AgentRuntime

`sealed class AgentRuntime : IAsyncDisposable, IDisposable`. Main entry point.

Constructor: `AgentRuntime(AgentRuntimeOptions? options = null)`.

| Member | Signature | Notes |
|---|---|---|
| `Client` | `AgentClient Client { get; }` | The control-plane client. |
| `Schedules` | `Schedules Schedules { get; }` | Cron lifecycle. |
| `WorkerThreadCount` | `int { get; }` | From `AGENTSPAN_WORKER_THREADS`. |
| `WorkerPollIntervalMs` | `int { get; }` | From `AGENTSPAN_WORKER_POLL_INTERVAL`. |
| `RunAsync` | `Task<AgentResult> RunAsync(Agent agent, string prompt, string? sessionId = null, IEnumerable<string>? media = null, Plan? plan = null, CancellationToken ct = default)` | Run + host workers + wait. |
| `Run` | `AgentResult Run(Agent, string, string? = null, IEnumerable<string>? = null)` | Sync wrapper. |
| `StartAsync` | `Task<AgentHandle> StartAsync(Agent, string, string? = null, IEnumerable<string>? = null, Plan? = null, CancellationToken = default)` | Start, return handle. |
| `Start` | `AgentHandle Start(Agent, string, ...)` | Sync wrapper. |
| `RunByNameAsync` / `StartByNameAsync` | `(...)` by workflow name | Pre-deployed agents. |
| `StreamAsync` | `IAsyncEnumerable<AgentEvent> StreamAsync(Agent, string, string? = null, IEnumerable<string>? = null, CancellationToken = default)` | Run + stream events. |
| `DeployAsync` | `Task<DeploymentInfo[]> DeployAsync(params Agent[])` ; `Task<DeploymentInfo> DeployAsync(Agent, IEnumerable<Schedule>?)` | Register without executing; second form reconciles schedules. |
| `Deploy` | `DeploymentInfo[] Deploy(params Agent[])` | Sync. |
| `ServeAsync` | `Task ServeAsync(Agent, CancellationToken = default)` ; `Task ServeAsync(CancellationToken = default, params Agent[])` | Host workers; blocks until cancelled. |
| `PlanAsync` / `Plan` | `Task<JsonNode?> PlanAsync(Agent, CancellationToken = default)` | Dry-run compile. |
| `ResumeAsync` / `Resume` | `Task<AgentHandle> ResumeAsync(string executionId, Agent, CancellationToken = default)` | Reattach + re-register workers across restarts. |
| `SendMessageAsync` | `Task SendMessageAsync(string executionId, object message, CancellationToken = default)` | Push to the Workflow Message Queue. |
| `GetStatusAsync` | `Task<AgentStatus> GetStatusAsync(string executionId, CancellationToken = default)` | |
| `RespondAsync` | `Task RespondAsync(string executionId, object response, CancellationToken = default)` | HITL response by id. |
| `ApproveAsync` / `RejectAsync` / `RespondAsync` (event) | `(AgentEvent waitingEvent, ...)` | Event-targeted HITL (targets the event's execution). |

## AgentRuntimeOptions

`sealed class AgentRuntimeOptions` — `string? ServerUrl`, `string? AuthKey`,
`string? AuthSecret`. Any unset value falls back to the corresponding
`AGENTSPAN_*` env var.

## Agent

`sealed partial class Agent`. Constructor: `Agent(string name)` (name must match
`^[a-zA-Z_][a-zA-Z0-9_-]*$`).

Key settable members:

| Member | Type | Notes |
|---|---|---|
| `Name` | `string` (get-only) | |
| `Model` | `string?` | `"provider/model"`. |
| `Instructions` | `string?` | Static system prompt. |
| `InstructionsFn` | `Func<string>?` | Dynamic; takes precedence over `Instructions`. |
| `PromptTemplateInstructions` | `PromptTemplate?` | Server-side template. |
| `Tools` | `List<ToolDef>` | |
| `Agents` | `List<Agent>` | Sub-agents. |
| `Strategy` | `Strategy?` | Required when `Agents` is non-empty. |
| `Router` | `Agent?` | For `Strategy.Router`. |
| `MaxTurns` / `MaxTokens` / `Temperature` / `TimeoutSeconds` | nullable | |
| `Guardrails` | `List<GuardrailDef>` | |
| `Termination` | `TerminationCondition?` | |
| `Handoffs` | `List<Handoff>` | Swarm triggers. |
| `Gate` | `TextGate?` | Sequential-pipeline stop gate. |
| `AllowedTransitions` | `Dictionary<string, List<string>>?` | Constrained transitions. |
| `Callbacks` | `List<CallbackHandler>` | Composable lifecycle handlers. |
| `BeforeAgentCallback` / `AfterAgentCallback` / `BeforeModelCallback` / `AfterModelCallback` / `BeforeToolCallback` / `AfterToolCallback` | `Func<...>?` | Inline delegate hooks. |
| `OutputType` | `Type?` | Structured output. |
| `Stateful` | `bool` | Domain-routed workers. |
| `EnablePlanning` | `bool` | "Plan first" prompt preamble. |
| `Strategy.PlanExecute` slots | `Planner`, `Fallback`, `FallbackMaxTurns`, `PlannerContext` | |
| `External` | `bool` | |
| `Framework` / `FrameworkConfig` | `string?` / `Dictionary<string,object>?` | Set by framework adapters. |

Operators / statics:

- `operator >>` — `Agent a >> Agent b` builds a `Strategy.Sequential` pipeline.
- `Agent.ScatterGather(name, worker, ...)` — coordinator that fans a worker agent out in parallel.
- `Agent.FromInstance(object)` / `Agent.FromInstance(object, string name)` — resolve `[AgentDef]` methods.

## AgentBuilder

`sealed class AgentBuilder`. Start with `AgentBuilder.Create(string name)`, chain
`With*`, finish with `Build()` (throws `ConfigurationException` if sub-agents have
no strategy).

`WithModel`, `WithInstructions(string)`, `WithInstructions(Func<string>)`,
`WithInstructions(PromptTemplate)`, `WithTools(params ToolDef[])`,
`WithAgents(params Agent[])`, `WithStrategy`, `WithRouter`, `WithOutputType<T>()`,
`WithMaxTurns`, `WithMaxTokens`, `WithTemperature`, `WithTimeout`, `WithExternal`,
`WithEnablePlanning`, `WithPlanner`, `WithFallback`, `WithFallbackMaxTurns`,
`WithPlannerContext(params Context[])` / `(params string[])`, `WithIncludeContents`,
`WithThinkingBudget`, `WithRequiredTools`, `WithIntroduction`, `WithMetadata`,
`WithHandoffs(params Handoff[])`, `WithGate(TextGate)`,
`WithCallbacks(params CallbackHandler[])`, and the four
`WithBefore/AfterAgent/ToolCallback(...)` delegate setters.

## Strategy

`enum Strategy`: `Handoff`, `Sequential`, `Parallel`, `Router`, `RoundRobin`,
`Random`, `Swarm`, `Manual`, `PlanExecute`.

## Tools: ToolDef and built-ins

**`ToolAttribute`** (`[Tool]`) on a method: `Name`, `Description`,
`ApprovalRequired`, `External`, `TimeoutSeconds`, `Credentials` (`string[]`),
`Stateful`, `RetryCount` (2), `RetryDelaySeconds` (2), `RetryPolicy`
(`"linear_backoff"`). Constructors: `ToolAttribute()`, `ToolAttribute(string description)`.

**`ToolDef`** — `Name`, `Description`, `InputSchema` (`JsonObject`),
`ApprovalRequired`, `External`, `TimeoutSeconds`, `Credentials`, `Stateful`,
`RetryCount`, `RetryDelaySeconds`, `RetryPolicy`, `Guardrails`. Method
`WithGuardrails(params GuardrailDef[])` returns a copy with guardrails appended.

**`ToolContext`** (record) — injected into tool methods: `SessionId`,
`ExecutionId`, `AgentName`, `Metadata`, `Dependencies`, `State`, `ExecutionToken`.

**`ToolRegistry.FromInstance(object)`** → `List<ToolDef>` (scans `[Tool]` methods).

**`ToolDefFactory.Create(name, description, handler, inputSchema = null, credentials = null)`**
— sync or async `handler` of shape `(Dictionary<string, JsonElement> args, ToolContext? ctx) -> object?`.

Built-in factories (all return `ToolDef`):

| Factory | Signature highlights |
|---|---|
| `AgentTool.Create` | `(Agent agent, string? name = null, string? description = null, int? retryCount = null, int? retryDelaySeconds = null, bool? optional = null)` |
| `HttpTools.Create` | `(string name, string description, string url, string method = "GET", Dictionary<string,string>? headers = null, JsonObject? inputSchema = null, string[]? credentials = null)` |
| `McpTools.Create` | `(string serverUrl, string? name = null, string? description = null, Dictionary<string,string>? headers = null, List<string>? toolNames = null, int maxTools = 64, string[]? credentials = null)` |
| `RagTools.Index` / `RagTools.Search` | `(string name, string description, string vectorDb, string index, string embeddingModelProvider, string embeddingModel, string namespace = "default_ns", ...)` |
| `MediaTools.Image` / `.Audio` / `.Video` | `(string name, string description, string llmProvider, string model, JsonObject? inputSchema = null, Dictionary<string,object>? extra = null)` |
| `MediaTools.Pdf` | `(string name = "generate_pdf", string description = "...", JsonObject? inputSchema = null, Dictionary<string,object>? extra = null)` |
| `HumanTool.Create` | `(string name = "ask_user", string description = "...", JsonObject? inputSchema = null)` |
| `WaitForMessageTool.Create` | `(string name = "wait_for_message", string description = "...", int batchSize = 1, bool blocking = true)` |
| `ApiTools.Create` | `(string url, string? name = null, string? description = null, Dictionary<string,string>? headers = null, List<string>? toolNames = null, int maxTools = 64, string[]? credentials = null)` |
| `CliTool.Create` | `(IEnumerable<string>? allowedCommands = null, string name = "run_command", int timeoutSeconds = 30, string[]? credentials = null)` |

## Guardrails

**`GuardrailAttribute`** (`[Guardrail]`): `Name`, `Position` (default `Output`),
`OnFail` (default `Raise`), `MaxRetries` (3).

**`GuardrailDef`** — `Name`, `Position`, `OnFail`, `MaxRetries`.

**`GuardrailResult`** (record) — `(bool Passed, string? Message = null, string? FixedOutput = null)`.

**`GuardrailRegistry.FromInstance(object)`** → `List<GuardrailDef>`.

**`RegexGuardrail.Create`** — `(string|IEnumerable<string> pattern(s), string mode = "block", string? name = null, string? message = null, Position position = Output, OnFail onFail = Retry, int maxRetries = 3)`. `mode`: `"block"` (fail on match) or `"allow"` (fail when nothing matches).

**`LLMGuardrail.Create`** — `(string model, string policy, string? name = null, int? maxTokens = null, Position position = Output, OnFail onFail = Retry, int maxRetries = 3, string? apiKey = null)`.

Enums: `Position` { `Input`, `Output` }; `OnFail` { `Retry`, `Raise`, `Fix`, `Human` }.

## TerminationCondition

`abstract class TerminationCondition` with `operator &` (AND) and `operator |` (OR).

- `TextMentionTermination(string text, bool caseSensitive = false)`
- `StopMessageTermination(string stopMessage)`
- `MaxMessageTermination(int maxMessages)`
- `TokenUsageTermination(int? maxTotalTokens = null, int? maxPromptTokens = null, int? maxCompletionTokens = null)`
- `AndTermination` / `OrTermination` — produced by the operators.

## Handoff

`abstract class Handoff` — `Target` (get-only), `abstract bool ShouldHandoff(IReadOnlyDictionary<string, object?> context)`.

- `OnTextMention(string text, string target)` ; static `OnTextMention.Of(text, target)`.
- `OnToolResult(string toolName, string target, string? resultContains = null)` ; static `.Of(toolName, target)` and `.Of(toolName, target, resultContains)`.
- `OnCondition(string target, Func<IReadOnlyDictionary<string, object?>, bool> condition)`.

Context keys: `result`, `messages`, `tool_name`, `tool_result`.

## TextGate

`sealed class TextGate` — `TextGate(string text, bool caseSensitive = true)`;
properties `Text`, `CaseSensitive`. Stops a sequential pipeline after the agent if
its output contains `Text`.

## CallbackHandler

`abstract class CallbackHandler`. Override any of:
`OnAgentStart`, `OnAgentEnd`, `OnModelStart`, `OnModelEnd`, `OnToolStart`,
`OnToolEnd` — each `Dictionary<string, object>? On...(Dictionary<string, JsonElement> kwargs)`.
A non-empty return overrides / short-circuits. Register a list via
`Agent.Callbacks`; handlers run in order, first non-empty return wins.

Positions map to server task names: `before_agent`, `after_agent`,
`before_model`, `after_model`, `before_tool`, `after_tool`.

## Schedule / Schedules

`namespace Agentspan.Scheduling`.

**`Schedule`** (init-only): `Name` (required), `Cron` (required, 6-field Quartz),
`Timezone` (`"UTC"`), `Input` (`IReadOnlyDictionary<string, object?>`), `Catchup`,
`Paused`, `StartAt`, `EndAt`, `Description`. `Validate()` throws on bad input.

**`ScheduleInfo`** (record) — server view: `Name` (wire), `ShortName`, `Agent`,
`Cron`, `Timezone`, `Input`, `Paused`, `PausedReason`, `Catchup`, `StartAt`,
`EndAt`, `Description`, `NextRun`, `CreateTime`, `UpdateTime`, `CreatedBy`,
`UpdatedBy`.

**`Schedules`** — `SaveAsync(Schedule, agentName)`, `GetAsync(wireName)`,
`ListAsync(agentName)`, `PauseAsync(wireName, reason?)`, `ResumeAsync(wireName)`,
`DeleteAsync(wireName)`, `RunNowAsync(ScheduleInfo)`,
`PreviewNextAsync(cron, n = 5, startAt?, endAt?)`,
`ReconcileAsync(agentName, IEnumerable<Schedule>?)`. Statics: `Prefix`, `Unprefix`,
`CheckUniqueNames`.

## Plans

`namespace Agentspan.Plans`. For `Strategy.PlanExecute`.

- **`Plan`** — `Steps` (`List<Step>`), `Validation`, `OnSuccess`, `OnFailure`. `ToJson()`.
- **`Step(string id)`** — `Operations` (`List<Op>`), `DependsOn` (`List<string>`), `Parallel`.
- **`Op(string tool, Dictionary<string, object?> args)`** (literal) ; `Op.WithGenerate(string tool, Generate)` (LLM-driven). Exactly one of args/generate.
- **`Generate`** — `Instructions` (required), `OutputSchema` (required), `MaxTokens?`, `Context` (string or `Ref`).
- **`Ref(string stepId)`** — wires a prior step's output (`{"$ref": "stepId"}`); the step must be in `DependsOn`.
- **`Context.FromText(string)`** / **`Context.FromUrl(url, headers? = null, required = true, maxBytes = 16384)`** — planner reference context.
- **`Validation(string tool)`** — `Args`, `SuccessCondition`. **`Action(string tool)`** — `Args`.

## Results

**`AgentResult`** (record): `ExecutionId`, `CorrelationId`, `Output`
(`Dictionary<string, object>?`; final text usually `Output["result"]`), `Messages`,
`ToolCalls`, `Status`, `FinishReason`, `Error`, `TokenUsage`, `Metadata`, `Events`,
`SubResults`. Convenience: `IsSuccess`, `IsFailed`, `IsRejected`, and
`PrintResult()`.

**`AgentHandle`** — `ExecutionId`, `RunId`, `WaitAsync(ct)`, `StreamAsync(ct)`,
`GetStatusAsync(ct)`, `RespondAsync(object)`, `ApproveAsync()` /
`ApproveAsync(string comment)`, `RejectAsync(string? reason)`, the event-targeted
overloads `ApproveAsync(AgentEvent, ...)` / `RejectAsync(AgentEvent, reason)` /
`RespondAsync(AgentEvent, object)`, `IsWaitingAsync(ct)`,
`WaitUntilWaitingAsync(timeout, pollInterval? = null, ct)`, `StopAsync()` /
`Stop()`, `CancelAsync(reason)` / `Cancel(reason)`.

**`AgentEvent`** (record): `Type` (`EventType`), `Content`, `ToolName`, `Args`,
`Result`, `Target`, `Output`, `ExecutionId`, `GuardrailName`, `Timestamp`, `Status`.

**`AgentStatus`** (record): `ExecutionId`, `IsComplete`, `IsRunning`, `IsWaiting`,
`Output`, `StatusValue`, `Reason`, `CurrentTask`, `PendingTool`, `TokenUsage`.

Enums: `EventType` { `Thinking`, `ToolCall`, `ToolResult`, `GuardrailPass`,
`GuardrailFail`, `Waiting`, `Handoff`, `Message`, `Error`, `Done` };
`Status` { `Completed`, `Failed`, `Terminated`, `TimedOut` };
`FinishReason` { `Stop`, `Length`, `ToolCalls`, `Error`, `Cancelled`, `Timeout`,
`Guardrail`, `Rejected` }.

Other records: `TokenUsage(PromptTokens, CompletionTokens, TotalTokens)`,
`DeploymentInfo(RegisteredName, AgentName)`.

## AgentClient

`sealed class AgentClient : IDisposable` (formerly `AgentHttpClient`). Constructor:
`AgentClient(string serverUrl, string? authKey = null, string? authSecret = null)`.
Obtain the runtime's instance via `runtime.Client`.

Control-plane convenience: `RunAsync(Agent, ...)`, `StartAsync(Agent, ...)`,
`DeployAsync(params Agent[])`, `ScheduleAsync(Agent, IEnumerable<Schedule>, ct)`,
`Schedules` (property). Run is control-plane only — no local tool workers.

Lower level: `StartAsync(JsonObject)`, `DeployAsync(JsonObject)`,
`CompileAsync(JsonObject)`, `GetStatusAsync`, `GetExecutionAsync`, `RespondAsync`,
`StreamEventsAsync`, `StartWorkflowByNameAsync`, `SendWorkflowMessageAsync`,
`StopAgentAsync`, `CancelAgentAsync`, `GetWorkflowAsync`,
`ResolveCredentialsAsync(executionToken, names)`.

## Exceptions

`ConfigurationException` (invalid agent config, e.g. sub-agents without strategy),
`AgentApiException` (HTTP error from the agent API; carries the status code and
body). Credential resolution throws `CredentialNotFoundException`,
`CredentialAuthException`, `CredentialRateLimitException`, or
`CredentialServiceException`. Scheduling throws `ScheduleException` and subtypes
`ScheduleNotFound`, `ScheduleNameConflict`, `InvalidCronExpression`.
</content>
