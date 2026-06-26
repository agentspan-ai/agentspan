# Guide to implementing an SDK for Agentspan

This guide describes how to build an Agentspan SDK in any language. The Java SDK
(`sdk/java`) is the reference implementation; cross-SDK wire formats must match
Python and TypeScript. Be idiomatic to the language — port the *model*, not the API.

# Core principle

**Everything is an Agent.** A single agent wraps an LLM + tools. An agent with
sub-agents *is* a multi-agent system. There is one type to learn.

# Agent Schema

The SDK's only job is to serialize agents into the workflow definition the server
compiles. See `agent-schema.json` / `agent-schema.md` for the wire contract and
`agent-structure.md` for the field-by-field mapping. Serialize to match it exactly.

# Structure

1. Extend the equivalent Conductor SDK. Get the latest release from
   `https://github.com/conductor-oss/{lang}-sdk` (java, go, python, csharp,
   javascript, rust, ruby, …).
2. Do **not** implement custom HTTP transport. Use Conductor's `ApiClient` for all
   remote calls — it owns token management, auth, timeouts, and config.
3. Do **not** redefine connection properties already in the Conductor SDK config.
4. Namespace: `org.conductoross.conductor.ai` (or the language equivalent).
5. Interfaces must be idiomatic. Do not copy APIs verbatim across languages.

Separation of concerns (as in Java):
- The **Conductor client** (`ApiClient`) owns server URL + auth.
- An **SDK config** object (`AgentConfig`) owns *only* worker-runner tuning
  (poll interval, thread count). It carries no connection details.
- `AgentRuntime` takes both and wires them together.

# Authentication & Configuration

1. OSS deployments require no authentication.
2. Orkes deployments use an API key + secret, passed through the Conductor
   `ApiClient` (env vars or explicit).
3. The SDK reads `AGENTSPAN_SERVER_URL`, `AGENTSPAN_AUTH_KEY`,
   `AGENTSPAN_AUTH_SECRET` (defaulting the server URL to `http://localhost:6767`).
   The `CONDUCTOR_SERVER_URL` / `CONDUCTOR_AUTH_KEY` / `CONDUCTOR_AUTH_SECRET`
   variables are **already honored by the Conductor SDK's `ApiClient`** (the
   transport base). Because the SDK builds its client on that `ApiClient`, those
   variables work transitively — do not re-implement them. `AGENTSPAN_*` are the
   SDK-level override read before constructing the client.
4. Worker tuning env vars: `AGENTSPAN_WORKER_POLL_INTERVAL` (ms, default 100),
   `AGENTSPAN_WORKER_THREADS` (default 1).
5. Normalize the URL: strip a trailing `/` and any `/api` suffix, then append `/api`.

# The Agent

An immutable, declarative config built with a fluent builder. Name is required and
must match `^[a-zA-Z_][a-zA-Z0-9_-]*$`. `maxTurns` defaults to 25.

```java
Agent agent = Agent.builder()
    .name("assistant")
    .model("openai/gpt-4o")          // "provider/model"; omit for external agents
    .instructions("You are helpful.")
    .maxTurns(10)
    .build();
```

Notes for implementers:
- **Instructions may be dynamic** — accept a supplier/callable re-evaluated at each
  serialization (so prompts can reflect current state). Resolve at serialize time.
- **An agent with no model is *external*** — it references a deployed workflow.
- **Sequential sugar:** `a.then(b)` returns a new `SEQUENTIAL` agent (Python's `>>`).
- See `agent-structure.md` for the full field → JSON-key table and serialization
  rules (e.g. `strategy` is emitted only when sub-agents/PLAN_EXECUTE slots exist;
  `synthesize` only when `false`).

# AgentRuntime

The execution surface. `AutoCloseable` — shut down workers and release the HTTP
pool on close. Provide both sync and async (future/promise) variants of each.

| Method | Purpose |
|---|---|
| `run(agent, prompt)` | Execute synchronously → `AgentResult` |
| `start(agent, prompt)` | Fire-and-forget → `AgentHandle` |
| `stream(agent, prompt)` | Execute and stream events → `AgentStream` |
| `plan(agent)` | Compile to a workflow def without executing |
| `deploy(agents…)` | Compile + register (CI/CD); no workers, no execution |
| `deploy(agent, schedules)` | Deploy and reconcile cron schedules declaratively |
| `serve(agents…)` | Register workers and poll until interrupted |
| `resume(executionId, agent)` | Re-attach to a running execution, re-register workers |
| `schedules()` | Accessor for the cron-schedule lifecycle API |

`run` = `start` then wait. Workers register inside `start` so they bind to the
correct queue (see domain note below).

## Workers

Local tool functions, callbacks, guardrails, and termination conditions are
registered as Conductor workers that poll for tasks. Walk the agent tree
(sub-agents, router, agent-tools) and register every local handler.

**Stateful agents** get a per-execution domain (a `runId` UUID) used as
`taskToDomain`; register their workers under that domain so concurrent runs don't
dequeue each other's tasks. An agent is stateful if `stateful=true`, any tool is
stateful, or any descendant is.

# Control-plane API

All calls go through the Conductor `ApiClient`. Map transport errors to typed SDK
exceptions (e.g. not-found vs. generic API error).

| Method | Endpoint |
|---|---|
| compile | `POST /api/agent/compile` |
| deploy | `POST /api/agent/deploy` |
| start | `POST /api/agent/start` |
| status | `GET /api/agent/{executionId}/status` |
| respond (HITL) | `POST /api/agent/{executionId}/respond` |
| stream | `GET /api/agent/stream/{executionId}` (SSE) |

The start payload carries the compiled `agentConfig` (or `framework`+`rawConfig`),
the `prompt`, and optional `sessionId`, `runId`, `static_plan`.

# Streaming & HITL

The server streams events over SSE at the stream endpoint. Expose an iterable
`AgentStream` of typed events plus HITL controls.

Event types: `THINKING, TOOL_CALL, TOOL_RESULT, HANDOFF, WAITING, MESSAGE, ERROR,
DONE, GUARDRAIL_PASS, GUARDRAIL_FAIL`.

HITL: when the agent pauses for human input it emits a `WAITING` event carrying the
pending tool (`taskRefName`, tool name, parameters, optional response/UI schema).
Respond via the stream or handle:
- `approve()` / `approve(comment)` / `reject(reason)` / `respond(map)`.
- **Route to the right execution.** Under HANDOFF/SEQUENTIAL/PARALLEL the HUMAN
  task lives in a *sub-execution*. Pass the `WAITING` event to the approve/reject
  call so it targets that event's `executionId`, not the root.
- After approving a sub-execution, the resumed agent may emit on a separate SSE
  channel; provide a `waitForResult(timeout, poll)` that polls workflow status
  rather than blocking on the original stream.

`AgentHandle` mirrors this without streaming: `waitForResult`, `isWaiting`,
`waitUntilWaiting(timeout)`, `approve`/`reject`/`respond`.

`AgentResult` exposes: `output` (raw or typed via a class), `status`
(`COMPLETED/FAILED/TERMINATED/TIMED_OUT`), `toolCalls`, `tokenUsage`
(prompt/completion/total), `error`, `isSuccess`, `printResult`. Token usage and
tool calls are enriched from the completed workflow via the Conductor workflow client.

# Strategies

Multi-agent orchestration is selected by `strategy` over the `agents` list:

`HANDOFF` (default), `SEQUENTIAL`, `PARALLEL`, `ROUTER`, `ROUND_ROBIN`, `RANDOM`,
`SWARM`, `MANUAL`, `PLAN_EXECUTE`.

Some strategies need locally-registered workers the server expects by name:
- **SWARM** — `{src}_transfer_to_{dst}`, `{name}_check_transfer`,
  `{name}_handoff_check` (compute next active agent from transfer tool calls).
- **MANUAL** — `{name}_process_selection` (map selected agent name → index).
- **PLAN_EXECUTE** — uses named `planner` (required) and `fallback` (optional)
  slots, *not* positional `agents`.

# Built-in tools

Provide factories/builders for each. All produce the same `ToolDef` model.

| Tool | Constructor shape |
|---|---|
| HTTP | `HttpTool.builder().name().url().method().header()/headers().credentials()…` |
| MCP | `McpTool.builder().name().serverUrl().toolName().headers().credentials()…` |
| Human (HITL) | `HumanTool.create(name, description[, inputSchema])` |
| Media (image/audio/video) | `MediaTools.imageTool(name, desc, provider, model[, schema])` (+audio/video) |
| PDF | `PdfTool.create([name, description, inputSchema, defaults])` |
| Wait-for-message | `WaitForMessageTool.create(name, description[, batchSize, blocking])` |
| Agent-as-tool | `AgentTool.from(agent[, description])` |
| RAG | `RagTools.searchTool(…)` / `RagTools.indexTool(…)` |

# Tools (custom)

Two ways to define a local tool:
1. **Annotation/decorator** — mark a method `@Tool(name, description, …)` and
   discover it via reflection (`ToolRegistry.fromInstance(obj)` → `List<ToolDef>`).
2. **Builder** — construct a `ToolDef` directly.

`ToolDef` carries: `name`, `description`, in/out `schema`, the local `func`,
`toolType` (default `worker`), `approvalRequired` (HITL gate), `credentials`,
`timeoutSeconds`, retry policy, `maxCalls`, `guardrails`, `agentRef`, `stateful`.
`@Tool` attributes mirror these (`approvalRequired`, `external`, `timeoutSeconds`,
`maxCalls`, `credentials`, `retryCount`, `retryDelaySeconds`, `retryPolicy`).

# Guardrails

Input/output validation attached to an agent (or a tool). All produce a
`GuardrailDef` with `position` (`INPUT`/`OUTPUT`), `onFail`
(`RETRY`/`RAISE`/`FIX`/`HUMAN`), `maxRetries`, and a `guardrailType`.

- **Custom** — `Guardrail.of(name, fn)` where `fn: String → GuardrailResult`
  (local worker `{agent}_output_guardrail`).
- **External** — `Guardrail.external(name)` references a server-side worker.
- **Regex** — `RegexGuardrail.builder().patterns(…).mode("block"|"allow")…`.
- **LLM** — `LLMGuardrail.builder().model(…).policy(…)…`.
- Also discoverable via an `@GuardrailDef` annotation (method `String →
  GuardrailResult`).

# Termination & Gate

**Termination conditions** are composable with `and`/`or`:
- `MaxMessageTermination.of(n)`
- `TextMentionTermination.of(text[, caseSensitive])`
- `StopMessageTermination.of(text)`
- `TokenUsageTermination.ofTotal/ofPrompt/ofCompletion(n)`

```java
MaxMessageTermination.of(10).or(TextMentionTermination.of("DONE"))
```

**Gate** stops a sequential pipeline when an agent's output contains a sentinel:
`new TextGate(text[, caseSensitive])`, attached via `.gate(...)`.

# Handoffs

SWARM transfer triggers, each naming a target agent:
- `OnTextMention.of(text, target)` — output contains text.
- `OnToolResult.of(tool, target[, resultContains])` — after a tool runs.
- `OnCondition(target, predicate)` — local predicate worker
  (`{agent}_handoff_{target}`).

Restrict reachability with `allowedTransitions` (source → allowed targets).

# Plans (PLAN_EXECUTE)

A deterministic plan can be passed to `run(agent, prompt, plan)` to skip the
planner LLM (forwarded as `static_plan`; the server takes it as highest priority).

Build: `Plan.builder().step(Step.builder(id).operation(Op.builder(tool).args(…)
| .generate(Generate…)).dependsOn(…).parallel(…)).validation(…).onSuccess/onFailure(…)`.

- `Op` takes literal `args` **or** a `Generate` (per-op LLM call with
  `instructions` + `outputSchema`).
- `Ref(stepId)` wires an upstream step's output into a downstream arg
  (serializes to `{"$ref": stepId}`).
- `Context.text(...)` / `Context.url(...)` supply planner reference material
  (URLs fetched per run; support credential placeholders `${CRED_NAME}`).

# Schedules

Declarative cron via `deploy(agent, schedules)`:

```java
Schedule.builder().name("weekday-9am").cron("0 0 9 * * MON-FRI")
    .timezone("America/Los_Angeles").input(Map.of("channel", "#eng")).build()
```

Tri-state reconcile: `null` = leave untouched, empty list = purge, non-empty =
upsert + prune others. Lifecycle via `runtime.schedules()`: `save`, `get`, `list`,
`pause`, `resume`, `delete`, `runNow`, `previewNext(cron, n)`, `reconcile`.

# Callbacks

Lifecycle hooks registered on the agent and run as local workers. Either single
functions (`beforeModelCallback`, `afterModelCallback`, `beforeAgentCallback`,
`afterAgentCallback`) or a composable `CallbackHandler` overriding any of:
`onAgentStart/End`, `onModelStart/End`, `onToolStart/End`. Returning a non-empty
map short-circuits / overrides at that position. Multiple handlers run in order.

# Skills as Agents

Load a skill directory (`SKILL.md` + scripts/resources) as an agent:
`Skill.skill(path, model[, agentModels, params, searchPath])`, or
`Skill.loadSkills(dir, model)` for all sub-skills. Skill scripts/resources run as
local workers (`createSkillWorkers`). Skill agents take the framework path
(`framework="skill"`).

# Agent methods (annotations)

Allow defining agents declaratively from annotated methods. `@AgentDef` on a
method (attributes: `name`, `model`, `instructions`, `tools`, `guardrails`,
`agents`, `strategy`, `maxTurns`, `maxTokens`, `temperature`, `credentials`,
`contextWindowBudget`). Resolve with `Agent.fromInstance(obj)` /
`Agent.fromInstance(obj, name)`. `@Tool`/`@GuardrailDef` methods on the same object
attach to the agents (all by default). Return type controls behavior: `void` (attrs
only), `String` (dynamic instructions), `PromptTemplate`, `Agent.Builder` (decorate
then build), or `Agent` (full factory).

# Framework bridges

Adapt native framework objects into the `Agent` model and send them via the
`framework` + `rawConfig` path so the server's matching normalizer handles them.
The runtime's `run/start/stream/deploy/serve/plan/resume` should also accept the
raw native object and coerce it (detect by fully-qualified type name so the core
never hard-references an optional dependency).

Reference bridges: OpenAI Agents SDK, Google ADK (`BaseAgent`), LangChain4j /
LangGraph4j.

# Reference docs

- `agent-schema.md` / `agent-schema.json` — wire contract
- `agent-structure.md` — Agent field → JSON-key mapping and serialization rules
- `agent-client-api.md` — control-plane client (compile/deploy/start/status/respond)
- `agent-runtime-api.md` — runtime, streaming, and HITL semantics
