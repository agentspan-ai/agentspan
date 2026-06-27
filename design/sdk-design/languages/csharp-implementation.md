# C# SDK — Reference Implementation

**Status:** Created 2026-06-26

**Scope:** This document describes the .NET implementation of the Agentspan SDK as a *reference implementation* of the cross-language SDK contract. It is written from the actual source under `sdk/csharp/src/`. It covers the package layout, the compilation/serialization model, the runtime lifecycle, worker dispatch internals, the streaming/SSE client, guardrails and credentials, the framework adapters (OpenAI / Google ADK / Semantic Kernel), the C#-specific design choices, and the test layout. The SDK contract itself lives in [`../../sdk-design.md`](../../sdk-design.md); the server-side compilation model in [`../../agentspan-design.md`](../../agentspan-design.md); the HTTP control-plane in [`../../api-design.md`](../../api-design.md); framework normalizers in [`../../framework-integration.md`](../../framework-integration.md); and the secret/worker contract in [`../../tool-execution-and-credentials-design.md`](../../tool-execution-and-credentials-design.md). For idiomatic usage and the public surface, see the sibling idiom guide [`csharp.md`](csharp.md). Python is the canonical reference SDK; see [`python-implementation.md`](python-implementation.md) for the structure this document mirrors.

---

## 1. Overview

The C# SDK lets a developer declare an `Agent` (an LLM + tools, or a multi-agent system) and execute it as a durable Conductor workflow. The SDK never interprets the agent locally: it serializes the agent tree to JSON, POSTs it to the server's `/api/agent/*` endpoints, and the server-side Java compiler turns it into a Conductor `WorkflowDef`. The SDK's runtime responsibility is narrow but essential — register and poll **local tool workers**, and poll/stream execution state.

Distribution:

| Package (NuGet `PackageId`) | Assembly / namespace | Purpose |
|---|---|---|
| `conductor-agent-sdk` | `Conductor.AI` | Core SDK — `Agent`, tools, runtime, client, workers |
| `conductor-agent-sdk-openai` | `Conductor.AI.OpenAI` | OpenAI Agents SDK shape adapter |
| `conductor-agent-sdk-google-adk` | `Conductor.AI.GoogleADK` | Google ADK shape adapter |
| `conductor-agent-sdk-semantic-kernel` | `Conductor.AI.SemanticKernel` | Microsoft Semantic Kernel plugin bridge |

- **Target framework:** `net10.0` (all projects). `Nullable` and `ImplicitUsings` enabled; `LangVersion=latest`.
- **Core dependencies:** `conductor-csharp` 1.1.4 (brings `Conductor.Client.Configuration`, `TaskResourceApi`, Newtonsoft.Json, and `Microsoft.Extensions.Logging.Abstractions` transitively) and `Newtonsoft.Json` 13.0.3 pinned. `System.Text.Json` and `System.Threading.Channels` are in-box on .NET 10.
- **Design principles** (shared with the reference SDK): everything is an `Agent`; server-first execution; compile-don't-interpret; zero-config for simple cases; Conductor-native mapping.

---

## 2. Package & source layout

All under `sdk/csharp/src/`.

### Core — `Conductor.AI/`

| File | Responsibility |
|---|---|
| `Agent.cs` | The `Agent` primitive, `Strategy` enum, `AgentBuilder` fluent builder, `Agent.ScatterGather`, and the `>>` sequential-pipeline operator. |
| `AgentConfigSerializer.cs` | `internal static` — serializes the `Agent` tree to the server wire JSON. The heart of compile-don't-interpret. |
| `AgentRuntime.cs` | Primary entry point. Owns worker orchestration + control-plane client. `IAsyncDisposable`. |
| `AgentClient.cs` | Control-plane HTTP client for `/agent/*` (compile/deploy/start/status/respond/stream) and `/workflow/*`. |
| `AgentAuth.cs` | `AgentAuthHandler` — `DelegatingHandler` that mints/caches a JWT and attaches `X-Authorization`. |
| `WorkerManager.cs` | `WorkerPollLoop` (per-task-type poller) + `WorkerManager` (registers all workers from an agent tree). |
| `Tool.cs` | `ToolAttribute`, `ToolDef`, `ToolContext`, reflection-based `ToolRegistry`, and tool factories (`HttpTools`, `McpTools`, `RagTools`, `MediaTools`, `HumanTool`, `WaitForMessageTool`, `ApiTools`, `CliTool`, `AgentTool`, `ToolDefFactory`). |
| `Result.cs` | `AgentResult`, `AgentStatus`, `AgentEvent`, `AgentHandle`, value records (`TokenUsage`, `DeploymentInfo`, …), and the `EventType`/`Status`/`FinishReason`/`OnFail`/`Position` enums. |
| `CredentialInjection.cs` | Process-wide-lock env-var injection for tier-2 credential passthrough. |
| `Guardrail.cs`, `Handoff.cs`, `Termination.cs`, `Gate.cs`, `Callback.cs`, `Skill.cs`, `Plans.cs`, `SemanticMemory.cs`, `Tracing.cs`, `CredentialInjection.cs`, `Exceptions.cs`, `AgentDef.cs`, `GPTAssistantAgent.cs` | Feature modules: guardrail defs, SWARM handoff triggers, termination conditions, sequential gate, lifecycle callback handlers, skills, deterministic plans (PLAN_EXECUTE), memory, tracing, exception hierarchy, declarative `[AgentDef]` discovery. |
| `Scheduling/` | `Schedule`, `Schedules` (cron lifecycle: save/list/pause/resume/delete/runNow/preview/reconcile), `ScheduleException`. |

### Adapters

Each adapter is a thin project that references `Conductor.AI` and produces an `Agent` with a `Framework` tag set:

- `Conductor.AI.OpenAI/OpenAIAgent.cs` — builder producing `Framework = "openai"`.
- `Conductor.AI.GoogleADK/GoogleADKAgent.cs` — builder producing `Framework = "google_adk"`.
- `Conductor.AI.SemanticKernel/SemanticKernelAgent.cs` — references `Microsoft.SemanticKernel` 1.76.0; produces a *plain* `Agent` (no framework tag) whose tools wrap `[KernelFunction]` methods.

---

## 3. Compilation & serialization

`Agent` objects are **never executed locally**. `AgentConfigSerializer` (in `AgentConfigSerializer.cs`) walks the agent tree and emits the JSON the server consumes; the server's Java `AgentCompiler` produces a Conductor `WorkflowDef`. See [`../../agentspan-design.md`](../../agentspan-design.md) for the server compilation model and [`../../api-design.md`](../../api-design.md) for the endpoints.

```
Agent  ──AgentConfigSerializer.Serialize()──►  JSON payload
                                                  │
        POST /api/agent/start    (run/start)      ▼
        POST /api/agent/compile  (plan, dry-run)  Server AgentCompiler
        POST /api/agent/deploy   (deploy, no exec)   ──►  Conductor WorkflowDef
```

### Two entry shapes

`Serialize(agent, prompt, sessionId, media)` produces the **start** payload, and `SerializeAgent(agent)` produces the bare **agentConfig** used by `deploy`/`compile`. There are two wire envelopes:

1. **Default envelope** — `{ agentConfig, prompt, sessionId, media }`. Used for plain agents.
2. **Framework envelope** — when `agent.Framework` is `"openai"`, `"google_adk"`, or `"skill"`, the start payload becomes `{ framework, rawConfig, prompt[, sessionId] }`, routed server-side to the matching normalizer (`OpenAINormalizer`, `GoogleADKNormalizer`). For `deploy`/`compile`, `AgentClient.FrameworkAwarePayload` inspects a `_framework` marker and wraps as `{ framework, rawConfig }`, else `{ agentConfig }`.

### What `SerializeAgent` emits (selected, verify against source)

- Scalar config: `model`, resolved `instructions` (via `Agent.ResolveInstructions()`, which evaluates `InstructionsFn` at serialize time), `maxTurns`, `maxTokens`, `temperature`, `timeoutSeconds`, `thinkingBudgetTokens`, `includeContents`, `introduction`, `external`, `enablePlanning`.
- PLAN_EXECUTE slots: `planner`, `fallback`, `fallbackMaxTurns`, and `plannerContext` (the latter *throws* `InvalidOperationException` at serialize time if set on a non-`PlanExecute` strategy — the last line of defence for that guard).
- `codeExecution` block when `LocalCodeExecution`/`CodeExecution`/`AllowedLanguages`/`AllowedCommands` is set, plus an injected `{agent.Name}_execute_code` worker tool so the LLM sees a callable function.
- `outputType` — `{ schema, className }` where the schema is produced by `System.Text.Json.Schema.JsonSchemaExporter.GetJsonSchemaAsNode(...)` over the CLR `Type`.
- `tools` (each via `SerializeTool`), `guardrails`, `agents` (recursive), `strategy` (via `StrategyToWire`, e.g. `RoundRobin → "round_robin"`, `PlanExecute → "plan_execute"`), `router`, `termination`, `allowedTransitions`, `metadata`, `handoffs`, `gate`, and lifecycle `callbacks` (one `{position, taskName}` per active hook, deduped).

### Tool serialization (`SerializeTool`)

Each `ToolDef` emits `{ name, description, inputSchema, toolType }`. `toolType` defaults to `"worker"` (or `"external"` when `External`). Notable rules verified in source:

- Stateful routing: `stateful=true` is emitted when the agent or the tool is stateful, but only for `worker`/`external` tool types.
- Retry tuning is only emitted when it diverges from defaults (`retryCount != 2`, `retryDelaySeconds != 2`, `retryPolicy != "linear_backoff"`).
- **Credentials always land inside `config.credentials`** (never top-level) because the server's `AgentService.extractDeclaredCredentials` reads `tool.getConfig().get("credentials")`. The serializer merges credentials into the config object for every tool type.
- `agent_tool` embeds the child agent under `config.agentConfig` (and, for skill children, `config.workerNames`).

---

## 4. Runtime lifecycle — `AgentRuntime` + `AgentClient`

The SDK has two execution surfaces. **`AgentRuntime` is the primary entry point** — it owns local tool-worker orchestration *and* a backing `AgentClient`. **`AgentClient` is control-plane only**: its `RunAsync`/`StartAsync` compile + start + poll but do **not** register or poll local tool workers. Use the client directly only for LLM-only agents, remote tools (HTTP/MCP), or pre-deployed workflows; any agent with local `[Tool]` functions must run through `AgentRuntime`.

`AgentRuntime` is `IAsyncDisposable`/`IDisposable` and is intended to be created with `await using`.

### Configuration

The constructor reads options or environment:

| Setting | Env var | Default |
|---|---|---|
| Server URL | `AGENTSPAN_SERVER_URL` | `http://localhost:6767/api` |
| Auth key | `AGENTSPAN_AUTH_KEY` | (none → OSS anonymous) |
| Auth secret | `AGENTSPAN_AUTH_SECRET` | (none) |
| Worker poll interval (ms) | `AGENTSPAN_WORKER_POLL_INTERVAL` | 100 (min 1) |
| Worker thread count | `AGENTSPAN_WORKER_THREADS` | 1 (min 1) |

It builds a `conductor-csharp` `Configuration` for worker polling; when key+secret are present it attaches `OrkesAuthenticationSettings` (JWT exchange). Connection/auth for the control plane is owned by the `AgentClient` via `AgentAuthHandler`.

### Async API + sync wrappers

The async methods are the source of truth; synchronous wrappers call `.GetAwaiter().GetResult()`:

- `RunAsync(agent, prompt, …)` → `StartInternalAsync` → `handle.WaitAsync` → stop workers → `AgentResult`.
- `StartAsync(...)` → `AgentHandle` (for streaming / HITL).
- `RunByNameAsync` / `StartByNameAsync` — execute a pre-deployed workflow by name (no agentConfig payload; posts to `/workflow`).
- `StreamAsync(...)` — start then yield `AgentEvent`s, then stop workers.
- `DeployAsync(params Agent[])` and `DeployAsync(agent, schedules)` — CI/CD: compile + register without executing, optionally reconciling cron schedules.
- `ServeAsync(agent, ct)` — register local workers and block on `Task.Delay(Timeout.Infinite, ct)` until cancelled (the workflow must already be deployed).
- `PlanAsync(agent)` — dry-run compile (`POST /agent/compile`), returns the raw `JsonNode` WorkflowDef.
- `ResumeAsync(executionId, agent)` — re-attach across process restarts (see §5).
- HITL/WMQ: `GetStatusAsync`, `RespondAsync`, `ApproveAsync`/`RejectAsync` (both root and event-targeted), `SendMessageAsync` (Workflow Message Queue).
- `Schedules` — cron lifecycle, delegated to the client.

### `StartInternalAsync` (the core path)

1. If the agent (or any sub-agent / tool / router) is stateful (`HasStatefulTools`), generate a fresh per-execution domain `runId = Guid.NewGuid().ToString("N")`. This mirrors the Python runtime's `_has_stateful_tools` + `run_id = uuid.uuid4()`.
2. Lazily create the `WorkerManager`, `RegisterAgentTools(agent, runId)`, and `Start()`.
3. Serialize the start payload; attach `runId` and (for PLAN_EXECUTE) `static_plan`.
4. `POST /agent/start`; wrap the returned executionId in an `AgentHandle` (carrying the runId for domain-routed polling).

After `RunAsync` completes, workers are disposed; `StartAsync`/`StreamAsync` leave them running for the caller's session.

### Result polling — `AgentHandle.WaitAsync`

`AgentHandle` polls `GET /agent/{id}/status` every **500 ms** until `COMPLETED`/`FAILED`/`TERMINATED`/`TIMED_OUT`, then fetches the full execution record (`GET /agent/execution/{id}`) for `tokenUsage` and `finishReason`, and builds an `AgentResult`. `finishReason` strings map to the `FinishReason` enum (e.g. `TOOL_CALL`/`TOOL_CALLS → ToolCalls`).

---

## 5. Worker & dispatch internals

Unlike Python (which has a single universal `dispatch_worker`), the C# SDK registers **one poll loop per task type** and lets the server route tool calls. Tools execute as Conductor worker tasks polled locally.

### `WorkerManager.RegisterAgentTools(agent, domain?)`

Recursively walks the agent tree and registers:

- **Tool workers** — for every `ToolDef` whose `Handler` is non-null (`RegisterTools`). Remote/server-side tools (HTTP, MCP, RAG, media, human, WMQ) have no handler and are skipped — the server executes them.
- **Guardrail workers** — local guardrail functions, wrapped to emit the `{passed, message, on_fail, fixed_output, guardrail_name, should_continue}` contract (`RegisterGuardrails`); also per-tool guardrails.
- **Callback workers** — `before/after_model` (bespoke signatures) and the generic kwargs-based `before/after_agent`, `before/after_tool`, plus any `CallbackHandler` overrides (`RegisterCallbacks`).
- **Local code execution worker** — `{agent.Name}_execute_code`, which writes the code to a temp file and runs `python3`/`bash`/`node` with a timeout (`ExecuteLocalCodeAsync`).
- **Strategy workers** — SWARM transfer + `_check_transfer` + `_handoff_check` workers; MANUAL `_process_selection`; skill workers.

### `WorkerPollLoop`

Each loop spawns `_threadCount` concurrent `PollLoopAsync` tasks (so a slow handler doesn't stall siblings of the same type), each driven by a `PeriodicTimer` at the poll interval. It uses the `conductor-csharp` `TaskResourceApi.PollAsync(taskName, workerid: Environment.MachineName, domain)`. On a task:

1. `ConvertInputData` bridges Newtonsoft → `System.Text.Json` `JsonElement`.
2. `ExtractToolContext` pulls `__agentspan_ctx__` (a `ToolContext`) and `_agent_state`; internal keys are stripped from the handler-visible args.
3. If the tool declares credentials, resolve them (`AgentClient.ResolveCredentialsAsync`) and run the handler inside `CredentialInjection.InjectViaEnvAsync` (§7).
4. Wrap primitives as `{ result: … }`; merge shared-state updates as `_state_updates`.
5. Report via `TaskResult` (Newtonsoft dict): `COMPLETED`, or `FAILED_WITH_TERMINAL_ERROR` for `TerminalToolException` and credential failures (configuration errors are non-retryable), or `FAILED` otherwise.

### Reflection-based tool definition — `ToolRegistry.FromInstance`

Scans an object's public methods for `[Tool]`. For each it builds a `ToolDef` with a name (`Attr.Name` or `ToSnakeCase(methodName)`), a JSON Schema inferred from parameters (`BuildInputSchema`), and a handler that coerces JSON args to CLR parameter types (`CoerceArg`, incl. string→int/bool/double coercion), injects `ToolContext` if a parameter matches, invokes the method, and unwraps `Task`/`Task<T>`. External tools are skipped (no local handler).

---

## 6. Streaming / SSE client

`AgentClient.StreamEventsAsync(executionId, ct)` opens `GET /agent/stream/{id}` with `Accept: text/event-stream` and `HttpCompletionOption.ResponseHeadersRead`, then parses the SSE wire format line-by-line:

- `:`-prefixed heartbeats are skipped.
- `event:` / `id:` / `data:` lines accumulate; a blank line flushes an event block.
- `ParseEvent` maps the `event:` name + JSON `data` to a typed `AgentEvent`.

Event mapping (verified in `ParseEvent`):

| SSE `event:` | `AgentEvent.Type` | Notable fields |
|---|---|---|
| `thinking` | `Thinking` | `Content` |
| `tool_call` | `ToolCall` | `ToolName` |
| `tool_result` | `ToolResult` | `ToolName` |
| `guardrail_pass` / `guardrail_fail` | `GuardrailPass` / `GuardrailFail` | `GuardrailName`, `Content` |
| `waiting` | `Waiting` | (HITL pause) |
| `handoff` | `Handoff` | `Target` |
| `done` | `Done` | `Status` (finishReason), `Content` |
| `error` | `Error` | `Content` |

Iteration ends on a `done` event (`yield break`). The async iterator surfaces through `AgentHandle.StreamAsync` and `AgentRuntime.StreamAsync`. Events carry the emitting `ExecutionId`, which the event-targeted HITL helpers use so a sub-execution's HUMAN task is answered on its own execution rather than the root.

---

## 7. Guardrails & credentials (SDK-side)

### Guardrails

`GuardrailDef` (in `Guardrail.cs`) carries `Name`, `Position` (`Input`/`Output`), `OnFail` (`Retry`/`Raise`/`Fix`/`Human`), `MaxRetries`, and an optional local `Handler`. The serializer emits `{ name, position, onFail, maxRetries, guardrailType: "custom", taskName }` (Conductor task name = guardrail name). Local guardrails register as workers; external guardrails (no handler) are referenced by name and run remotely. The worker wrapper enforces escalation: an `OnFail.Retry` that has reached `MaxRetries` (or `OnFail.Fix` with no `FixedOutput`) downgrades to `Raise`. The full guardrail compilation model is in [`../../guardrails-design.md`](../../guardrails-design.md).

### Credentials & secret injection

The SDK never hard-codes secrets. Declared credential names travel inside `config.credentials` (§3). At dispatch time the worker resolves them and injects them for exactly one invocation:

- **Resolution** — `AgentClient.ResolveCredentialsAsync(executionToken, names)` POSTs `{ token, names }` to `/workers/secrets`. The error contract is strict and matches Python's `WorkerCredentialFetcher`: empty names → empty dict (no HTTP); missing token → `CredentialNotFoundException`; 401 → `CredentialAuthException`; 429 → `CredentialRateLimitException`; 5xx/network → `CredentialServiceException`; a 200 missing any requested name → `CredentialNotFoundException`. It never silently returns empty values.
- **Injection (tier 2)** — `CredentialInjection.InjectViaEnvAsync` holds a single **process-wide `SemaphoreSlim`** across mutation + invocation + restoration, so concurrent framework workers serialize instead of clobbering shared process-env. It is strictly serial within one process; scale by adding worker processes. Tier 1 (explicit-key passthrough into a model client) needs no lock. See [`../../tool-execution-and-credentials-design.md`](../../tool-execution-and-credentials-design.md).

### Control-plane auth — `AgentAuthHandler`

`AgentClient` wraps a `DelegatingHandler` that attaches the control-plane auth header to every `/agent/*` request, mirroring the Python/TS SDKs:

- No credentials → no header (OSS anonymous).
- Explicit key, no secret → the key is treated as a ready token.
- Key + secret → `POST {server}/token` mints a JWT, cached until ~30 s before its decoded `exp` (`DecodeJwtExp`), and sent as `X-Authorization`. The token mint uses a *separate* `HttpClient` so minting never recurses through the auth handler, and a `SemaphoreSlim` guards concurrent refresh.

The e2e/test assembly is granted `InternalsVisibleTo("AgentspanE2eTests")` specifically so it can exercise `AgentAuthHandler`.

---

## 8. Framework integration

Adapters convert a framework-shaped declaration into an Agentspan `Agent`; the server normalizers (`OpenAINormalizer`, `GoogleADKNormalizer`) consume the resulting wire shape. See [`../../framework-integration.md`](../../framework-integration.md).

- **OpenAI** (`Conductor.AI.OpenAI`) — `OpenAIAgent.Builder()` / `.From(...)` builds an `Agent` with `Framework = "openai"`. `Handoffs(...)` → `FrameworkConfig["handoffs"]`; `OutputType(name)` → `output_type`. Tools come from `[Tool]`-annotated objects via `ToolRegistry.FromInstance`. Models without a provider prefix are auto-prefixed `openai/` server-side.
- **Google ADK** (`Conductor.AI.GoogleADK`) — `GoogleADKAgent.Builder()` builds `Framework = "google_adk"`. Wire differences from OpenAI: `instruction` (singular, mapped by the serializer), `sub_agents` not `handoffs`, and bare models prefixed `google_gemini/` server-side.
- **Semantic Kernel** (`Conductor.AI.SemanticKernel`) — `SemanticKernelAgent.From(name, model, instructions, plugins…)` produces a *plain* `Agent` (no framework tag). It extracts tools from `KernelPlugin` instances or `[KernelFunction]` methods (`KernelPluginFactory.CreateFromObject`), builds schemas from `KernelFunctionMetadata`, and the tool handler invokes the `KernelFunction` against a bare `Kernel`. Because the result is a plain Agentspan agent, these tools run as ordinary Conductor worker tools.

### Framework tool wire shape

For `openai`/`google_adk`, `SerializeFrameworkAgent` emits tools as `{ _worker_ref, description, parameters }` (the normalizers drop the default `{name, inputSchema, toolType}` shape). Agent-as-tool emits `{ _type: "AgentTool", name, description, agent }` so the normalizer compiles a SUB_WORKFLOW.

---

## 9. C#-specific design choices

- **Async-first, sync wrappers.** Every network operation is `async`/`await` with `CancellationToken` support; the streaming API is `IAsyncEnumerable<AgentEvent>` with `[EnumeratorCancellation]`. Synchronous overloads (`Run`, `Start`, `Deploy`, `GetStatus`, …) exist for scripts and delegate to the async path via `.GetAwaiter().GetResult()`.
- **Records for data, classes for behaviour.** DTOs (`AgentResult`, `AgentStatus`, `AgentEvent`, `ToolContext`, `TokenUsage`, `GuardrailResult`, …) are `record`s with `init`-only members and `with`-expression updates (e.g. `ToolContext with { State = … }`). Mutable behavioural types (`Agent`, `AgentRuntime`, `AgentClient`) are classes.
- **Nullable reference types** are enabled across all projects; optional config uses `T?`/`Nullable<T>`, and "absent" is consistently distinguished from "default" at serialization.
- **Two JSON stacks, bridged deliberately.** The SDK uses `System.Text.Json` (`AgentspanJson.Options`: camelCase, ignore-null, snake_case enum converter) for its own wire format and JSON-Schema export, while `conductor-csharp` uses Newtonsoft.Json for task I/O. `WorkerPollLoop` bridges the two (`ConvertInputData` / `ToNewtonsoftDict`).
- **Dependency on `conductor-csharp`.** Worker polling reuses the official client's `Configuration`, `TaskResourceApi`, `TaskResult`, and (for Orkes) `OrkesAuthenticationSettings` rather than reimplementing the task protocol. The agent control plane (`/agent/*`) is bespoke (`AgentClient`) because those endpoints are Agentspan-specific.
- **Operator + factory ergonomics.** `a >> b` builds a sequential pipeline (`Strategy.Sequential`), extending an existing pipeline in place; `Agent.ScatterGather(...)` and the tool factories (`HttpTools`, `McpTools`, `MediaTools`, `RagTools`, `ApiTools`, `CliTool`, `HumanTool`, `WaitForMessageTool`, `AgentTool`) provide one-call construction.
- **Schema from CLR types.** Structured output uses `System.Text.Json.Schema.JsonSchemaExporter` over the `OutputType` CLR `Type`, so the schema is generated, not hand-written.

---

## 10. Testing

Tests live under `sdk/csharp/tests/`, split by concern (xUnit `[Fact]`/`[Theory]`):

| Project | Scope | Approx. test count |
|---|---|---|
| `Agentspan.OpenAI.Tests` | OpenAI adapter + `CliTool` (`OpenAIAgentTests`, `CliToolTests`) | ~13 |
| `Agentspan.GoogleADK.Tests` | Google ADK adapter (`GoogleADKAgentTests`) | ~5 |
| `Agentspan.SemanticKernel.Tests` | Semantic Kernel bridge (`SemanticKernelAgentTests`) | ~5 |
| `AgentspanE2eTests` | End-to-end against a live server — ~20 suites (`Suite1_BasicValidation` … `Suite19_AuthHeader`, plus `Plans_*`, `ScheduleTests`, `CredentialInjectionConcurrentTest`) | ~62 |

> **Counts are approximate** — derived from `[Fact]`/`[Theory]` occurrences at doc-creation time and will drift; treat the suite list as the durable signal.

**Assembly name `AgentspanE2eTests` is intentionally kept** even though the namespaces were renamed `Agentspan → Conductor.AI`: the core `Conductor.AI.csproj` grants `InternalsVisibleTo("AgentspanE2eTests")` so the e2e suite can reach internal types (notably `AgentAuthHandler`). Renaming the assembly would break that grant.

The E2E suites cover basic validation, tool calling, guardrails, termination, strategies, callbacks, credentials, coding/code-execution agents, MCP/HTTP/CLI/PDF/media tools, skills, stateful-domain routing, PLAN_EXECUTE refs, schedules, SDK parity, the `AgentClient` control plane, and the auth header. Per the project testing convention, e2e validation avoids using an LLM to judge output except where the test exists specifically to evaluate quality.

---

## Cross-references

- [`../../sdk-design.md`](../../sdk-design.md) — the cross-language SDK contract this implements.
- [`../../agentspan-design.md`](../../agentspan-design.md) — server-side compilation model.
- [`../../api-design.md`](../../api-design.md) — the `/agent/*` HTTP control plane.
- [`../../framework-integration.md`](../../framework-integration.md) — framework normalizers.
- [`../../tool-execution-and-credentials-design.md`](../../tool-execution-and-credentials-design.md) — worker + secret contract.
- [`csharp.md`](csharp.md) — C# idiom guide / public surface.
- [`python-implementation.md`](python-implementation.md) — the reference SDK implementation.
</content>
