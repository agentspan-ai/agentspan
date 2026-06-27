# TypeScript SDK — Reference Implementation

**Status:** Refreshed 2026-06-26

**Scope:** This document describes the TypeScript SDK *as built* — the shipped code under `sdk/typescript/`, published to npm as **`@conductoross/conductor-agent-sdk`**. It is a reference for how the SDK is structured and how it behaves at runtime, not a plan for future work. It is present-tense and maps directly to source files. For the cross-language contract and feature set, see the shared design docs ([`../../sdk-design.md`](../../sdk-design.md), [`../../agentspan-design.md`](../../agentspan-design.md), [`../../api-design.md`](../../api-design.md), [`../../framework-integration.md`](../../framework-integration.md), [`../../tool-execution-and-credentials-design.md`](../../tool-execution-and-credentials-design.md)). For language idioms and ergonomics, see the sibling guide [`typescript.md`](./typescript.md). For the validation harness, see [`../../validation/typescript-validation.md`](../../validation/typescript-validation.md).

---

## 1. Overview

The TypeScript SDK lets you define agents, tools, guardrails, memory, and multi-agent strategies in TypeScript, compile them to the Agentspan wire format (`AgentConfig` JSON), and run them on Agentspan's durable Conductor-backed runtime. It also runs native framework agents — Vercel AI SDK, LangGraph.js, LangChain.js, OpenAI Agents, Google ADK — on the same runtime via auto-detection and drop-in wrappers.

### 1.1 Design choices (as built)

| Aspect | Decision |
|--------|----------|
| Language | TypeScript-first (`.ts` source, compiled to ESM + CJS) |
| Package | `@conductoross/conductor-agent-sdk` |
| Runtime | Node.js 18+ (native `fetch`, `AbortController`, `ReadableStream`, `crypto.randomUUID`) |
| Schema | **Superset** — accepts both Zod schemas and raw JSON Schema, auto-detecting format; Zod is an optional peer |
| Framework integration | Auto-detecting runtime (`detectFramework`) plus drop-in `./vercel-ai`, `./langgraph`, `./langchain` wrappers |
| Conductor client | Worker polling runs on `@io-orkes/conductor-javascript`'s `TaskManager`; all `/agent/*` control-plane calls use a raw `fetch` client (`AgentClient`) that mints/refreshes an Orkes JWT |
| Build | `tsup` → ESM + CJS dual output with `.d.ts` declarations, multiple entry points |
| Test runner | Vitest (unit + e2e suites) |
| API style | Options-object pattern; composition via `.and()`/`.or()`/`.pipe()` methods (no operator overloading) |

> **Worker transport note:** Earlier drafts proposed dropping `@io-orkes/conductor-javascript` and polling with raw `fetch`. The shipped implementation keeps the Conductor JS client for *task polling* (`WorkerManager` wraps its `TaskManager`), because it provides lease extension, concurrency control, and retry handling for free. The Agentspan-specific middleware (ToolContext extraction, credential injection, state capture, circuit breaker, error mapping) runs inside each worker's `execute()` callback. The control plane (`/agent/start`, `/agent/compile`, status, respond, schedules) uses the SDK's own `fetch`-based `AgentClient`.

### 1.2 Runtime contracts (intentional, kept stable)

- **Environment variables** are `AGENTSPAN_*` (see §9).
- **Credential routing context** key in task input is `__agentspan_ctx__`.

---

## 2. Package & source layout

### 2.1 Dependencies

| Dependency | Type | Purpose |
|-----------|------|---------|
| `@io-orkes/conductor-javascript` | runtime | Worker task polling (`TaskManager`, `createConductorClient`) |
| `dotenv` | runtime | `.env` loading on import |
| `zod` | peer (optional) | Schema validation + type inference |
| `zod-to-json-schema` | peer (optional) | Convert Zod → JSON Schema at serialization time |
| `ai` | peer (optional) | Vercel AI SDK passthrough/wrapper |
| `@langchain/core` | peer (optional) | LangChain.js passthrough/wrapper |
| `@langchain/langgraph` | peer (optional) | LangGraph.js passthrough/wrapper |

All framework peers and `zod`/`zod-to-json-schema` are marked optional in `peerDependenciesMeta`; the SDK works without any of them installed (detection and serialization use duck-typing).

### 2.2 package.json highlights

```jsonc
{
  "name": "@conductoross/conductor-agent-sdk",
  "type": "module",
  "main": "./dist/index.cjs",
  "module": "./dist/index.js",
  "types": "./dist/index.d.ts",
  "exports": {
    ".":           { "import": "./dist/index.js",            "require": "./dist/index.cjs" },
    "./testing":   { "import": "./dist/testing/index.js",    "require": "./dist/testing/index.cjs" },
    "./vercel-ai": { "import": "./dist/wrappers/ai.js",      "require": "./dist/wrappers/ai.cjs" },
    "./langgraph": { "import": "./dist/wrappers/langgraph.js","require": "./dist/wrappers/langgraph.cjs" },
    "./langchain": { "import": "./dist/wrappers/langchain.js","require": "./dist/wrappers/langchain.cjs" }
  },
  "engines": { "node": ">=18.0.0" }
}
```

### 2.3 Source map (`sdk/typescript/src/`)

```
src/
  index.ts                  # Public re-exports (single barrel)
  agent.ts                  # Agent, PromptTemplate, scatterGather, agent(), @AgentDec, agentsFrom
  tool.ts                   # tool(), server-side tool ctors, @Tool, toolsFrom, waitForMessageTool
  guardrail.ts              # guardrail(), RegexGuardrail, LLMGuardrail, @Guardrail
  termination.ts            # TerminationCondition + TextMention/StopMessage/MaxMessage/TokenUsageCondition, And/Or
  handoff.ts                # OnToolResult, OnTextMention, OnCondition, TextGate, gate()
  memory.ts                 # ConversationMemory, SemanticMemory, InMemoryStore
  credentials.ts            # getCredential, resolveCredentials, execution-token + credential-context plumbing
  callback.ts               # CallbackHandler (6 lifecycle positions) + worker-name helpers
  code-execution.ts         # CodeExecutor + Local/Docker/Jupyter/Serverless + CommandValidator
  cli-config.ts             # makeCliTool() — run_command CLI tool
  claude-code.ts            # ClaudeCode model wrapper, PermissionMode, resolveClaudeCodeModel
  skill.ts                  # skill(), loadSkills(), createSkillWorkers (Agent Skills from SKILL.md)
  plans.ts                  # Plan/Step/Op/Generate/Validation/Action/Ref/Context (PLAN_EXECUTE builders)
  schedule.ts               # Schedule, ScheduleClient (cron schedules for deployed agents)
  schedules-api.ts          # module-function facade over ScheduleClient (singleton)
  ext.ts                    # GPTAssistantAgent
  discovery.ts              # discoverAgents(path)
  tracing.ts                # isTracingEnabled() (OTel env probe)
  types.ts                  # Shared interfaces/enums, AgentResult helpers, event/output normalizers
  errors.ts                 # AgentspanError hierarchy
  config.ts                 # AgentConfig — env loading + URL normalization
  serializer.ts             # AgentConfigSerializer — Agent tree → AgentConfig JSON
  worker.ts                 # WorkerManager (wraps Conductor TaskManager) + coercion/circuit-breaker/state-capture
  runtime.ts                # AgentRuntime — run/start/stream/deploy/plan/serve/shutdown + system-worker registration
  agent-client.ts           # AgentClient — /agent/* control-plane client, Orkes JWT auth, ClientHandle
  workflow-client.ts        # WorkflowClient — read-only Conductor execution + token-usage aggregation
  stream.ts                 # AgentStream — SSE client (AsyncIterable) + HITL + polling fallback
  frameworks/
    detect.ts               # detectFramework() — duck-typing
    serializer.ts           # serializeFrameworkAgent() — generic deep object → rawConfig + WorkerInfo[]
    langgraph-serializer.ts # serializeLangGraph() — CompiledStateGraph extraction
    langchain-serializer.ts # serializeLangChain() — AgentExecutor extraction
  wrappers/
    ai.ts                   # ./vercel-ai — drop-in generateText/streamText
    langgraph.ts            # ./langgraph — drop-in createReactAgent
    langchain.ts            # ./langchain — drop-in createAgentExecutor / runnable metadata
  testing/
    index.ts, mock.ts, expect.ts, assertions.ts, eval.ts, strategy.ts, recording.ts
cli-bin/
  deploy.ts, discover.ts, shared.ts   # Node scripts (deploy/discover agents from a directory)
```

### 2.4 Build entry points (`tsup.config.ts`)

```ts
entry: ['src/index.ts', 'src/testing/index.ts',
        'src/wrappers/ai.ts', 'src/wrappers/langgraph.ts', 'src/wrappers/langchain.ts'],
format: ['esm', 'cjs'], dts: true, splitting: true, sourcemap: true, target: 'node18'
```

`npm run build` runs `tsup` then `scripts/verify-dist.mjs` to assert the dual-format output is well-formed.

---

## 3. Compilation & serialization

`AgentConfigSerializer` (`serializer.ts`) recursively converts an `Agent` tree into the wire format from [`../../agentspan-design.md`](../../agentspan-design.md). `serialize(agent, prompt?, opts?)` returns the full `POST /api/agent/start` payload; the same serializer feeds `POST /api/agent/compile` (via `plan()`) and `POST /api/agent/deploy`.

Key rules (as built):

- All keys are **camelCase**; `null`/`undefined` values are omitted.
- `agents` holds nested `AgentConfig` objects; `strategy` is only emitted when `agents` is non-empty.
- Zod schemas (tool `inputSchema`/`outputSchema`, agent `outputType`) are converted via `zod-to-json-schema` at serialization time; raw JSON Schema passes through unchanged.
- `instructions` may be a string, a `PromptTemplate`, or a function (functions register as system workers).
- Guardrails, handoffs, termination conditions, gates, callbacks, `codeExecution`, `cliConfig`, and `credentials` each have a dedicated serialization path.
- Skill agents (`_framework: "skill"`) bypass `AgentConfig` and serialize to a framework `rawConfig` (see §7); the runtime pre-deploys them before serialization and replaces the `agent_tool` entry with a `workflowName` reference.
- PLAN_EXECUTE agents emit `planner`/`plannerContext` (and a static plan via `static_plan` when `RunOptions.plan` is supplied — see §6.7).

`frameworks/serializer.ts` (`serializeFrameworkAgent`) is a framework-agnostic deep walker that turns an arbitrary agent object into `[rawConfig, WorkerInfo[]]`: primitives/enums pass through, callables become `{_worker_ref, description, parameters}` stubs, tool objects are extracted, and circular references are caught.

---

## 4. Runtime lifecycle & worker system

### 4.1 AgentRuntime (`runtime.ts`)

```ts
class AgentRuntime {
  constructor(options?: AgentConfigOptions);
  run(agent, prompt, options?): Promise<AgentResult>;     // start, register workers, drain SSE, enrich, return
  start(agent, prompt, options?): Promise<AgentHandle>;   // fire-and-forget; handle with wait/respond/pause/...
  stream(agent, prompt, options?): Promise<AgentStream>;  // start() then handle.stream()
  deploy(agent, { schedules? }?): Promise<DeploymentInfo>;// compile + register; optional schedule reconcile
  plan(agent): Promise<object>;                           // POST /agent/compile (dry run)
  serve(...agents): Promise<void>;                        // register workers, poll, block until SIGINT/SIGTERM
  shutdown(): Promise<void>;                              // stop polling
  get workflows(): WorkflowClient;                        // read-only execution client
  schedulesClient(): ScheduleClient;
}
```

The `agent` argument is `Agent | object`. The runtime calls `detectFramework(agent)` first; framework objects take the passthrough path (`_runFramework`/`_startFramework`), native `Agent` instances take the standard path. Module-level singleton functions (`configure`, `run`, `start`, `stream`, `deploy`, `plan`, `serve`, `shutdown`) delegate to a lazily-created `AgentRuntime`.

**`run()` flow (native agent):**
1. Generate a correlation id (`crypto.randomUUID`).
2. Pre-deploy any nested skill agents (`_preDeployNestedSkills`).
3. If any tool/sub-agent is stateful, mint a `runId` (worker domain) for isolation.
4. Serialize the agent + prompt → payload; attach `timeoutSeconds`/`credentials`/`context`/`runId`/`static_plan` from options.
5. Register tool workers and skill workers (in the run's domain).
6. `POST /agent/start`; read `executionId` and optional `requiredWorkers`.
7. Register **system** workers (only those in `requiredWorkers`, or all on older servers); start polling.
8. Open an `AgentStream`, drain events, build `AgentResult`, then **enrich** it from `GET /agent/execution/{id}` (tool calls, messages, recursively-aggregated token usage, and a non-junk output fallback).
9. `finally` stop polling.

### 4.2 System workers registered by the runtime

`_registerSystemWorkers` walks the agent tree and registers Conductor SIMPLE workers for any feature backed by user code. Naming conventions (collected recursively):

| Worker | Task name |
|--------|-----------|
| Tool | `{tool.name}` |
| Tool / agent guardrail (custom) | `{guardrail.taskName}` |
| Termination condition | `{agentName}_termination` |
| `stopWhen` | `{agentName}_stop_when` |
| Callback (per position) | `{agentName}_{position}` (`before_agent`…`after_tool`) |
| Gate (callable) | `{agentName}_gate` → `{ decision: "continue" \| "stop" }` |
| Router function | `{agentName}_router_fn` → `{ selected_agent }` |
| Swarm transfer (no-op / blocked-error) | `{source}_transfer_to_{target}` |
| Check transfer | `{agentName}_check_transfer` → `{ is_transfer, transfer_to }` |
| Handoff check (swarm) | `{agentName}_handoff_check` → `{ active_agent, handoff }` |
| Manual selection | `{agentName}_process_selection` → `{ selected }` |

### 4.3 WorkerManager (`worker.ts`)

`WorkerManager` is a thin lifecycle wrapper over Conductor's `TaskManager`. `addWorker(taskName, handler, credentials?, domain?)` queues a worker; `startPolling()` builds a `createConductorClient` (overriding `CONDUCTOR_SERVER_URL`, injecting auth headers per request via a `headersProvider` that resolves the Orkes JWT) and starts the `TaskManager`. `(taskName, domain)` pairs are distinct workers, enabling stateful-domain isolation. Each wrapped worker's `execute()` runs the full middleware chain:

1. **Circuit breaker** — 10 consecutive failures opens the breaker (`NonRetryableException` thereafter); any success resets it; `resetCircuitBreaker(name)` / `resetAllCircuitBreakers()` are exported.
2. **ToolContext extraction** — reads `__agentspan_ctx__`, builds a `ToolContext` with a mutable copy of `state`, snapshots state.
3. **Key stripping** — removes `_agent_state`, `method`, `__agentspan_ctx__` from input before the handler sees it.
4. **Credential resolution** — if the worker declares credentials, extracts the execution token and resolves values up-front; injection happens atomically inside `injectSecretsForInvocation` (process-wide lock).
5. **State capture** — diffs `ToolContext.state` before/after and appends `_state_updates` to the result (merged into objects, or wrapped as `{ result, _state_updates }` for primitives).
6. **Output shaping** — non-object results are wrapped as `{ result }` (Conductor requires object `outputData`).
7. **Error mapping** — `TerminalToolError` → `NonRetryableException`; other errors propagate (retryable).

**Type coercion** (`coerceValue`) converts Conductor-typed inputs (string⇄number/boolean, string⇄object/array via `JSON.parse`/`stringify`); all failures are silent and return the original value.

---

## 5. Streaming / SSE client (`stream.ts`)

`AgentStream implements AsyncIterable<AgentEvent>` over `GET /agent/stream/{executionId}`, consumed with `for await...of`.

- **Transport:** native `fetch` + `ReadableStream` (so custom `Authorization`/`X-Authorization` headers work — `EventSource` can't send those). Parses `event:`/`id:`/`data:` fields; `:`-prefixed lines are heartbeats.
- **Timeout:** no real event within 15s → fall through to polling.
- **Reconnection:** on drop, up to 5 retries with linear backoff (`1s * attempt`), resuming with `Last-Event-ID`.
- **Polling fallback:** poll `GET /agent/{id}/status` every 500ms until terminal, emitting a synthetic terminal event.
- **HITL:** `respond(output)`, `approve(output?)`, `reject(reason?)`, `send(message)`.
- **Result:** `getResult()` drains the stream and builds an `AgentResult`; internal event keys are stripped via `stripInternalEventKeys`.

`AgentEvent.type` is `EventType | string` so server-only event types (`context_condensed`, `subagent_start`, `subagent_stop`) pass through to users untouched.

---

## 6. Type system, tools, guardrails, memory, credentials, callbacks, code execution

### 6.1 Type system

Enums are string unions (`Strategy`, `EventType`, `Status`, `FinishReason`, `OnFail`, `Position`, `ToolType`, `GuardrailType`, `FrameworkId`). Core data shapes (`types.ts`): `TokenUsage`, `ToolContext` (with mutable `state`), `GuardrailResult`, `AgentEvent`, `AgentResult`, `AgentStatus`, `DeploymentInfo`, `RunOptions`, `ToolDef`. Helpers `createAgentResult`, `normalizeOutput`, `stripInternalEventKeys` enforce the result/event invariants. `AgentResult.output` is always normalized to a `Record<string, unknown>` (strings wrapped as `{ result }`, COMPLETED null → `{ result: null }`, FAILED null → `{ error }`).

### 6.2 Tools (superset)

`tool(fn, options)` returns a callable `ToolFunction` carrying a hidden `_toolDef`. `inputSchema`/`outputSchema` accept Zod or JSON Schema. `normalizeToolInput` accepts (a) Agentspan `ToolDef`s, (b) Vercel AI SDK `tool()` objects (Zod `inputSchema` + `execute`), and (c) raw `{name, description, inputSchema}` objects — so all three coexist in one `tools` array. `external: true` emits schema only (no local worker). Server-side constructors (no local worker): `httpTool`, `apiTool`, `mcpTool`, `agentTool`, `humanTool`, `imageTool`, `audioTool`, `videoTool`, `pdfTool`, `searchTool`, `indexTool`, `waitForMessageTool`. Class-method form: `@Tool` decorator + `toolsFrom(instance)`.

### 6.3 Guardrails (`guardrail.ts`)

`guardrail(fn, {name, position?, onFail?, maxRetries?})` registers a custom SIMPLE worker. `RegexGuardrail` (server-side inline JS, block/allow) and `LLMGuardrail` (server-side `LLM_CHAT_COMPLETE`) need no worker. `guardrail.external` and the `@Guardrail` decorator + `guardrailsFrom` are also provided. `position` defaults to `output`; `onFail` ∈ `retry|raise|fix|human`.

### 6.4 Memory (`memory.ts`)

`ConversationMemory` (session history, optional `maxMessages` windowing that preserves system messages, serialized as `{messages, maxMessages}`). `SemanticMemory` over a pluggable `MemoryStore`; `InMemoryStore` ships a keyword-overlap similarity with no external deps.

### 6.5 Credentials (`credentials.ts`)

`getCredential(name)`, `resolveCredentials(serverUrl, headers, token, names)`, `extractExecutionToken`, and the `setCredentialContext`/`runWithCredentialContext`/`clearCredentialContext` plumbing that scopes credentials per async invocation so concurrent workers don't clobber each other. The worker extracts the execution token from `__agentspan_ctx__` (with a workflow-input fallback for sub-agents) and resolves credentials via the server before invoking the handler. Errors map to `CredentialNotFoundError` / `CredentialAuthError` / `CredentialRateLimitError` / `CredentialServiceError`.

### 6.6 Callbacks (`callback.ts`)

`CallbackHandler` with six optional async hooks (`onAgentStart`/`End`, `onModelStart`/`End`, `onToolStart`/`End`). Each implemented method registers a SIMPLE worker at `{agentName}_{position}` (`before_agent`…`after_tool`).

### 6.7 Code execution, CLI, Claude Code, plans, skills

- **Code execution** (`code-execution.ts`): abstract `CodeExecutor` (+ `asTool()`) with `Local`, `Docker`, `Jupyter`, `Serverless` implementations and a `CommandValidator`. Agent-level `CodeExecutionConfig` / `CliConfig`.
- **CLI tool** (`cli-config.ts`): `makeCliTool()` produces a `run_command` tool with quoting-aware tokenization, command whitelist, exit-code capture, and context-state persistence.
- **Claude Code** (`claude-code.ts`): `ClaudeCode` model wrapper → `"claude-code/<alias>"`, `PermissionMode` enum, `resolveClaudeCodeModel()` alias mapping.
- **Plans** (`plans.ts`): typed `PLAN_EXECUTE` builders — `Plan`, `Step`, `Op`, `Generate`, `Validation`, `Action`, `Ref`, `Context` — each with `toJSON()`; `coercePlan()` normalizes a `Plan`-or-object. A static plan supplied via `RunOptions.plan` is sent as `static_plan` and wins over the planner LLM.
- **Skills** (`skill.ts`): `skill()` loads an Agent Skill from a `SKILL.md` directory (frontmatter, `*-agent.md` sub-agents, scripts, cross-skill refs), returning an `Agent` marked `_framework: "skill"`. `loadSkills()` batch-loads; `createSkillWorkers()` builds script-execution workers plus a `read_skill_file` tool.

### 6.8 Execution API surface

`RunOptions`: `sessionId`, `media`, `idempotencyKey`, `timeoutSeconds`, `signal` (AbortSignal), `credentials`, `context`, `plan`, `model`. `AgentHandle`: `executionId`, `correlationId`, `getStatus`, `wait(pollIntervalMs?)`, `respond/approve/reject/send`, `pause`, `resume`, `cancel`, `stream`. Control-plane-only execution (no local workers) is available through `AgentClient` → `ClientHandle` (`agent-client.ts`), and read-only execution inspection through `WorkflowClient` (`workflow-client.ts`). Cron scheduling for deployed agents: `Schedule` + `ScheduleClient` (`schedule.ts`) with a declarative `reconcile()`, plus the `schedules` module facade.

---

## 7. Framework auto-detection & integration

See [`../../framework-integration.md`](../../framework-integration.md) for the server-side contract.

### 7.1 Detection (`frameworks/detect.ts`)

`detectFramework(agent)` returns `FrameworkId | null` via duck-typing (no framework imports):

| Result | Signature checked |
|--------|-------------------|
| `"skill"` | `_framework === "skill"` |
| `null` (native) | `instanceof Agent` |
| `"langgraph"` | `.invoke()` + (`.getGraph()` or `.nodes`) |
| `"langchain"` | `.invoke()` + `.lc_namespace` |
| `"openai"` | `name` + `instructions` + `model` + `tools` + `handoffs` + `asTool` |
| `"google_adk"` | `model` + `instruction` + ADK-specific props |

LangGraph, LangChain, OpenAI Agents, Google ADK, and skills are auto-detected and run through the passthrough path. **Vercel AI SDK** integration is delivered through the `./vercel-ai` wrapper rather than runtime auto-detection.

### 7.2 Passthrough path

For framework objects, `run()`/`start()` call `_serializeFramework` → `[rawConfig, WorkerInfo[]]`, register the extracted workers, start polling, then `POST /agent/start { framework, rawConfig, prompt, sessionId?, credentials? }`. The server normalizer compiles a passthrough `WorkflowDef` whose SIMPLE task is served by the registered worker; events stream back over SSE like any native run.

- `serializeLangGraph` (`langgraph-serializer.ts`) has three paths: full extraction (model + ToolNode → AI_MODEL + SIMPLE), graph-structure extraction (custom `StateGraph` nodes/edges/reducers/retry policies, detecting LLM and subgraph nodes by patching `invoke`), and single-SIMPLE passthrough.
- `serializeLangChain` (`langchain-serializer.ts`) checks for `_agentspan` wrapper metadata first, else extracts model + tools, else passes through.
- `serializeFrameworkAgent` (`serializer.ts`) handles OpenAI Agents and Google ADK generically.

### 7.3 Drop-in wrappers (subpath exports)

- **`./vercel-ai`** (`wrappers/ai.ts`): re-exports the `ai` module and wraps `generateText`/`streamText` to intercept model/tools/system/prompt, compile to an `Agent`, run on `AgentRuntime`, and map results back to AI SDK shape.
- **`./langgraph`** (`wrappers/langgraph.ts`): `createReactAgent()` proxies the original and stamps `_agentspan` metadata so the serializer fast-paths it.
- **`./langchain`** (`wrappers/langchain.ts`): `createAgentExecutor()` / runnable-metadata helpers that capture LLM/tools/instructions as `_agentspan` metadata.

Wrappers infer the `provider/model` string from LLM class/model names (Anthropic, Google, Bedrock, OpenAI). Framework packages are lazy-loaded on first use.

---

## 8. Build & packaging

`tsup` produces dual ESM + CJS with `.d.ts` for five entry points (§2.4); `npm run build` verifies the output with `scripts/verify-dist.mjs`. Node 18+ is the supported runtime. The package marks Node-only modules (worker, credentials, code execution) as such; browser consumers can use the REST/SSE surface but not worker polling, tool execution, or credential resolution. Lint/format via ESLint + Prettier; typecheck via `tsc --noEmit`.

---

## 9. Language-specific design choices & gotchas

- **Environment variables** (`config.ts`, all `AGENTSPAN_*`): `SERVER_URL` (default `http://localhost:6767/api`), `API_KEY`, `AUTH_KEY`, `AUTH_SECRET`, `WORKER_POLL_INTERVAL` (100ms), `WORKER_THREADS` (1), `AUTO_START_WORKERS`/`AUTO_START_SERVER`/`DAEMON_WORKERS`/`STREAMING_ENABLED` (true), `CREDENTIAL_STRICT_MODE` (false), `LLM_RETRY_COUNT` (3), `LOG_LEVEL` (`INFO`). `.env` is loaded on import via `dotenv`.
- **URL normalization:** `serverUrl` is stripped of trailing slashes and gets `/api` appended if missing. The Conductor worker client polls the base URL (with `/api` stripped).
- **Composition without operator overloading:** termination uses `.and()`/`.or()`; agent chaining uses `.pipe()` (which flattens `a.pipe(b).pipe(c)` into one sequential agent, not a nested tree).
- **Swarm transfers** are generated server-side from `strategy: 'swarm'`; the SDK only registers the no-op/blocked transfer workers and the `check_transfer`/`handoff_check` workers. Don't add `transfer_to_*` tools manually.
- **State mutation capture** appends `_state_updates`; the server persists state and strips the key from user-visible output.
- **Output "junk" repair:** the runtime treats `{result: null, finishReason: ...}` and `{result: []}` as junk and falls back to the execution's last assistant message / workflow output.
- **Token usage** is aggregated recursively across `SUB_WORKFLOW` tasks (`workflow-client.ts` / `runtime._collectTokensById`).
- **Idempotency:** `RunOptions.idempotencyKey` maps to Conductor `correlationId`; the server dedupes against RUNNING/COMPLETED (never FAILED) executions. `AgentHandle.correlationId` is a fresh UUID per call.
- **Cancellation/timeout:** every network call accepts an `AbortSignal` (`AbortSignal.timeout(ms)` or a manual `AbortController`).
- **`Status` is terminal-only** (`COMPLETED|FAILED|TERMINATED|TIMED_OUT`); `AgentStatus.status` is a `string` and may carry non-terminal Conductor states — prefer the `isComplete`/`isRunning`/`isWaiting` flags.
- **Stateful domains:** when an agent (or any descendant) is stateful, the run mints a `runId` used as the Conductor worker `domain`, so every worker for that execution polls in an isolated domain.
- **Tracing:** `isTracingEnabled()` only probes `OTEL_EXPORTER_OTLP_ENDPOINT`/`OTEL_SERVICE_NAME`; OTel SDK wiring is the caller's responsibility.
- **CLI helper scripts** live in `cli-bin/` (`deploy.ts`, `discover.ts`) and are invoked via `node`/`tsx`; there is no separately published binary.

---

## 10. Testing

> Full validation & e2e design: [typescript-validation.md](../../validation/typescript-validation.md)

Vitest, configured in `vitest.config.ts` (decorator support, 60s timeout, `forks` pool with up to 3 workers, JUnit reporter to `e2e-results/junit-ts.xml`). The package import is aliased to `src/index.ts` for in-tree testing.

- **Unit** (`tests/unit/`, ~45 files): per-module coverage — agent, tool, serializer, worker, runtime, stream, guardrail, termination, handoff, memory, credentials, callback, code-execution, cli-config, schedule, plans, skill, config, result, agent-client-auth, concurrent-injection, context-passing, planner-context, swarm-workers, kitchen-sink-structural, plus `frameworks/`, `wrappers/`, `testing/`, and `validation/` subtrees.
- **E2E** (`tests/e2e/`, ~24 suites, require a running server): basic validation, tool/CLI/MCP/HTTP/PDF/media tools, guardrails (+ matrix), handoffs, multi-agent matrix, LangGraph, termination/gates, callbacks, lease extension, stateful domain, behavioral correctness, skills, streaming, token usage, plan-execute, scheduling, wait-for-message tool, and the agent client. Per-language e2e wiring is documented in [`../../validation/typescript-validation.md`](../../validation/typescript-validation.md).
- **Testing utilities** (`./testing` export): `mockRun()`, `expectResult()` fluent assertions, individual `assert*` helpers, `record()`/`replay()` fixtures, `validateStrategy()`, and a `CorrectnessEval` LLM judge.
- **Fixtures:** `tests/_configs/*.json` hold expected wire-format snapshots; `tests/fixtures/skills/` provide sample SKILL.md trees.
