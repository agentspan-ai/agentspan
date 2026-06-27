# Java SDK — Reference Implementation

**Status:** Created 2026-06-26

**Scope:** This document describes the internal architecture of the **Java SDK** as a *reference implementation* of the Agentspan SDK contract — written from the actual source under `sdk/java/`. It mirrors the structure of the Python reference doc ([`python-implementation.md`](python-implementation.md)) and covers package layout, the compile-and-execute model, the runtime/worker internals, streaming, guardrails, credentials, framework bridges, the Spring Boot adapter, and Java-specific design choices. For the language-agnostic contract see [`../../sdk-design.md`](../../sdk-design.md); for the server-side compilation model see [`../../agentspan-design.md`](../../agentspan-design.md); for the wire endpoints see [`../../api-design.md`](../../api-design.md); for tools and secrets see [`../../tool-execution-and-credentials-design.md`](../../tool-execution-and-credentials-design.md); for frameworks see [`../../framework-integration.md`](../../framework-integration.md). The companion idiom/translation guide is [`java.md`](java.md).

---

## 1. Overview

The Java SDK lets you declare `Agent` objects in Java and run them as durable Conductor workflows. Like every Agentspan SDK, it follows the **compile-don't-interpret** model: the SDK serializes an `Agent` tree to an `AgentConfig` JSON payload and POSTs it to the server, which compiles it into a Conductor workflow definition. The SDK then runs the agent's tool functions as Conductor *workers* and polls/streams the execution. The SDK never interprets the agent loop locally — that lives on the server.

**Maven coordinates** (`sdk/java/build.gradle`, group `org.conductoross.conductor`):

| Artifact | Module | Purpose |
|---|---|---|
| `org.conductoross.conductor:conductor-agent-sdk` | `sdk/java` (root) | Core SDK |
| `org.conductoross.conductor:conductor-agent-sdk-spring` | `sdk/java/spring` | Spring Boot auto-configuration |

- **Namespace:** `org.conductoross.conductor.ai`
- **Java toolchain:** Java **21** (`JavaLanguageVersion.of(21)`); compiled with `-parameters` so reflective tool-parameter names survive.
- **Key dependencies:** the official Conductor Java client `org.conductoross:conductor-client:5.0.1` (`api` scope — its `ApiClient`/`ConductorClient` are part of the SDK's public surface), Jackson 2.17 (`api`), SLF4J. LangChain4j (1.0.0), Google ADK (1.3.0), and LangGraph4j (1.6.0-beta5) are **`compileOnly`** — bridges link only at runtime when a user passes a native object.

> Design note: connection details (server URL, auth key/secret) are *not* SDK config — they live entirely on the Conductor `ApiClient`. The SDK's own `AgentConfig` carries only worker-runner tuning. This differs from the Python SDK's monolithic `AgentConfig`.

---

## 2. Package & source layout

Root package `org.conductoross.conductor.ai` (99 main source files):

| Package | Contents |
|---|---|
| *(root)* | `Agent`, `Agent.Builder`, `AgentRuntime`, `AgentConfig`, `CallbackHandler` |
| `tools` | Server-side tool factories: `HttpTool`, `McpTool`, `AgentTool`, `HumanTool`, `MediaTools`, `PdfTool`, `RagTools`, `WaitForMessageTool` |
| `annotations` | `@Tool`, `@AgentDef`, `@GuardrailDef` (declarative POJO style) |
| `guardrail` | `Guardrail`, `LLMGuardrail`, `RegexGuardrail` (server-side built-ins) |
| `model` | DTOs/value types: `AgentResult`, `AgentHandle`, `AgentStream`, `AgentEvent`, `ToolDef`, `GuardrailDef`, `GuardrailResult`, `ToolContext`, `ConversationMemory`, `PromptTemplate`, `TokenUsage`, `CompileResponse`, `DeploymentInfo`, `PendingToolCall`, `PrefillToolCall`, `CredentialFile` |
| `enums` | `Strategy`, `EventType`, `AgentStatus`, `OnFail`, `Position`, `Framework` |
| `internal` | The plumbing: `AgentConfigSerializer`, `AgentClient`, `AgentRequest`, `WorkerManager`, `ToolRegistry`, `AgentRegistry`, `SseClient`, `JsonMapper`, `WorkerCredentialFetcher`, `CredentialContext`, response DTOs (`StartResponse`, `CompileResponse`, `AgentStatusResponse`), `RespondBody`, `PendingTool` |
| `handoff` | `Handoff`, `OnTextMention`, `OnToolResult`, `OnCondition` (SWARM triggers) |
| `termination` | `TerminationCondition` + `MaxMessageTermination`, `StopMessageTermination`, `TextMentionTermination`, `TokenUsageTermination`, `AndTermination`, `OrTermination`, `TerminationResult` |
| `plans` | `Plan` and supporting types (`Step`, `Action`, `Op`, `Ref`, `Generate`, `Validation`, `Context`, `PlanValues`) — deterministic PLAN_EXECUTE |
| `schedule` | `Schedule`, `Schedules`, `ScheduleInfo` (cron lifecycle) |
| `skill` | `Skill`, `SkillLoadError` (Agent Skills: `SKILL.md` directories) |
| `gate` | `TextGate` (sequential-pipeline sentinel gate) |
| `execution` | `CliCommandExecutor`, `CliConfig`, `CodeExecutor`, `DockerCodeExecutor`, `ExecutionResult` (local CLI / code execution) |
| `frameworks` | `AdkBridge`, `LangChainBridge`, `LangChain4jAgent`, `OpenAIAgent` |
| `openai` | `GPTAssistantAgent` (OpenAI Assistants API wrapper) |
| `exceptions` | `AgentspanException`, `AgentAPIException`, `AgentNotFoundException`, and credential errors (`CredentialNotFound/Auth/RateLimit/Service`) |

The `spring/` module (3 main classes) holds the Spring Boot adapter (§9).

---

## 3. Compilation & serialization

An `Agent` is an immutable value object built with a fluent `Agent.Builder` (§10). It is never compiled locally — the SDK serializes it and the server compiles it.

### Serialization (`internal/AgentConfigSerializer`)

`AgentConfigSerializer.serialize(Agent)` walks the agent tree and produces a **camelCase `Map<String,Object>`** matching the server's `AgentConfig` DTO. Notable behaviors verified in source:

- **Native vs framework path.** A `framework` of `"skill"`, `"openai"`, or `"google_adk"` takes a dedicated branch emitting the raw framework config (e.g. `_framework`, OpenAI's `instructions` vs ADK's singular `instruction`, the `_worker_ref` tool shape framework normalizers expect). All other agents take the native path.
- **Dynamic instructions** are supplier-backed (`Supplier<String>`) and resolved exactly once per serialization, so callable instructions re-evaluate on every run submission (matching Python).
- **Strategy** is emitted only when `agents` is non-empty *or* a PLAN_EXECUTE named slot (`planner`/`fallback`) is set — otherwise the server would default to `handoff` and reject the named slots with HTTP 400.
- **Injected tools.** Enabling `localCodeExecution` injects a `{name}_execute_code` worker tool; a `CliConfig` injects a `{name}_run_command` worker tool — both mirror the Python SDK's `_attach_*` helpers.
- **Credentials** declared on a tool are nested under `config.credentials` so the server includes them in the execution token's `declared_names`.
- `enablePlanning` (plan-first preamble) is deliberately a separate boolean key from the `planner` slot, because the server reused the `planner` JSON key for the PLAN_EXECUTE sub-agent.

The serializer is also exposed as a Jackson `JsonSerializer` (`AgentConfigSerializer.AsJson`) so `Agent`-typed fields serialize correctly without callers pre-converting to a `Map`.

### Request shape (`internal/AgentRequest`)

`compile`, `deploy`, and `start` share one server DTO. `AgentRequest` carries the `Agent`, an optional `Framework`, and execution fields (`prompt`, `sessionId`, `runId`, `staticPlan`, `media`, `context`, `idempotencyKey`, `credentials`, `timeoutSeconds`). Its custom `Serializer` writes **mutually-exclusive** keys:

- Native agent → `"agentConfig": {…}`
- Framework agent → `"framework": "<wireValue>", "rawConfig": {…}`

A deterministic `Plan` is forwarded as `"static_plan"` (server reads it as the highest-priority Case-0 plan, skipping the planner LLM). See [`../../agentspan-design.md`](../../agentspan-design.md) for the server-side compilation pipeline (single/tools/multi-agent/hybrid dispatch).

---

## 4. Runtime lifecycle — `AgentRuntime` + `AgentClient`

`AgentRuntime` (`AutoCloseable`) is the entry point. Unlike Python's module-level singleton, the Java SDK uses **explicit `AgentRuntime` instances** (try-with-resources friendly). See the API reference at `sdk/java/docs/agent-runtime-api.md` and `sdk/java/docs/agent-client-api.md`.

### Construction

The runtime owns **one** native Conductor `ApiClient` (server URL + auth), shared by every typed client: `AgentClient` (control plane), `WorkflowClient` (token/tool enrichment), `WorkerManager`, `SseClient`, and the lazy `Schedules`. Factory helpers build the client:

```java
AgentRuntime.clientFromEnv();            // AGENTSPAN_SERVER_URL / _AUTH_KEY / _AUTH_SECRET
AgentRuntime.client(url);                // unauthenticated
AgentRuntime.client(url, key, secret);   // native key/secret → token
```

The `/api` base path is appended automatically; explicit connect/read/write timeouts (10s/30s/30s) bound a slow server.

### Operations

`run`, `start`, `stream` (each with async `…Async` variants), plus `plan`, `deploy`, `serve`, `resume`, and the `schedules()` accessor. `run` is `start` + `waitForResult`; `stream` is `start` + an SSE connection.

```
startAsync(agent, prompt, plan)
   |
   +-- runId = hasStatefulTools(agent) ? uuid : null      # per-execution domain
   +-- prepareWorkers(agent, runId)                       # register local workers
   +-- workerManager.startAll()                           # build/rebuild task runner
   +-- agentClient.startAgent(AgentRequest…)              # POST /api/agent/start
   +-- return AgentHandle(executionId, agentClient, workflowClient)
```

`runAsync` intentionally does **not** pre-register workers before `startAsync` — for stateful agents, registration must happen under the per-execution domain (`runId`), or the worker would poll the default queue while the server enqueues under `runId` (a real bug that was fixed and regression-tested).

### Control plane (`internal/AgentClient`)

Strictly five endpoints, all routed through the shared `ConductorClient` (native HTTP + auth + serialization; no hand-rolled HTTP):

| Method | Endpoint |
|---|---|
| `compileAgent` | `POST /api/agent/compile` |
| `deployAgent` | `POST /api/agent/deploy` |
| `startAgent` | `POST /api/agent/start` |
| `getAgentStatus` | `GET /api/agent/{executionId}/status` |
| `respond` | `POST /api/agent/{executionId}/respond` |

Conductor's `ConductorClientException` is mapped to the SDK's typed `AgentNotFoundException` (404) / `AgentAPIException`. Standard Conductor endpoints (`/api/workflow/*`, `/api/tasks`, `/api/scheduler/*`) use the Conductor SDK's own typed clients.

### Result & handle (`model/AgentHandle`, `model/AgentResult`)

`AgentHandle.waitForResult()` polls `getAgentStatus` (2s interval, 10-min default timeout) until a terminal status (`COMPLETED`/`FAILED`/`TERMINATED`/`TIMED_OUT`), escalating log level after 3 consecutive poll errors and giving up after 10. On completion it walks the workflow tasks once via `WorkflowClient` to aggregate `TokenUsage` (from `LLM_CHAT_COMPLETE` tasks) and `toolCalls` (tasks whose ref name starts with `call_`), since the server doesn't aggregate these on the status response. HITL methods: `approve()/approve(comment)/reject(reason)/respond(Map)/send`, plus `isWaiting()` / `waitUntilWaiting(timeoutMs)`.

---

## 5. Worker & dispatch internals

### `internal/WorkerManager`

Rather than a hand-rolled poll loop, the SDK drives workers with the official Conductor client's `TaskRunnerConfigurer` + `Worker`, which provides battle-tested polling, backoff, managed threads, and — crucially — **automatic lease extension (heartbeat)** (every worker returns `leaseExtendEnabled() == true`), so a handler that blocks for minutes keeps its lease instead of being reclaimed.

- **Incremental registration vs fixed runner.** Agentspan registers workers per-run (sometimes under a per-execution domain), but `TaskRunnerConfigurer` is built from a fixed worker set. The bridge: `startAll()` (re)builds the configurer only when a *new* task type appeared since the last build (`workerSetChanged`). Re-registering an existing task only swaps the handler (looked up live in `Worker.execute`) — no rebuild — *unless* its domain changed (which is baked into `taskToDomain` at build time and forces a rebuild).
- **Task-def sizing.** Each new task registers a `TaskDef` whose `responseTimeoutSeconds` = `effectiveTaskTimeout(handlerTimeout)` (floor 300s, plus 60s slack) so the server's patience never drifts below the handler's blocking timeout.
- **Thread count** = `max(config.workerThreadCount, 1 × workerCount)` — at least one thread per worker type so a blocking handler can't starve others.
- **Output mapping:** a handler returning a `Map` becomes `outputData` directly; any other value is wrapped as `{"result": value}`.

### What `prepareWorkers` registers (`AgentRuntime.prepareWorkers`)

Walking the agent tree, the runtime registers local Java handlers for:

- **`@Tool` worker tools** (`toolType == "worker"`) — with declared credentials and timeout.
- **`agent_tool`** child agents (recursively).
- **Callbacks** — legacy `before/after_model` functions and `CallbackHandler` lists (chained per position: `before/after_agent/model/tool`).
- **Combined output guardrail** worker (`{name}_output_guardrail`) — runs all custom guardrail functions, returns `passed/on_fail/fixed_output/should_continue`.
- **Termination** worker (`{name}_termination`) — evaluates the composable `TerminationCondition`.
- **Local code execution** (`{name}_execute_code`) and **CLI** (`{name}_run_command`) workers.
- **SWARM** workers (`{src}_transfer_to_{peer}`, `{name}_check_transfer`, `{name}_handoff_check`) and **MANUAL** `{name}_process_selection`.
- **Skill** workers for `framework == "skill"` agents.

### How `@Tool` becomes a worker (`internal/ToolRegistry`)

`ToolRegistry.fromInstance(Object)` reflects over `@Tool`-annotated public methods. For each it: reads annotation metadata (name/description/credentials/retry); generates a JSON Schema from the method parameters (`-parameters`-retained names, `typeToJsonSchema`); wraps the method in a `Function<Map,Object>` that coerces inputData → args, injects `ToolContext` if declared, and returns the result; and builds a `ToolDef` with **`toolType = "worker"`**. The server compiles each into a Conductor `SIMPLE` task; the SDK's `WorkerManager` polls and runs the handler. See [`../../tool-execution-and-credentials-design.md`](../../tool-execution-and-credentials-design.md).

**Tool types** (the `toolType` wire strings): `worker`, `http`, `mcp`, `agent_tool`, `human`, `generate_image`/`generate_audio`/`generate_video`/`generate_pdf`, `rag_search`/`rag_index`, `pull_workflow_messages`. Only `worker` (and injected code/CLI workers) execute locally; the rest are server-side task types.

---

## 6. Streaming / SSE client

`stream(agent, prompt)` starts the agent, then opens `GET /api/agent/stream/{executionId}` via `internal/SseClient`. The request is built with `ApiClient.buildCall` so it rides the shared OkHttp client and the token-refresh auth interceptor — exactly like every other client (no separate HTTP stack).

- A daemon thread reads the response body line-by-line, parsing standard SSE framing (`event:` / `data:` / `id:` / `:` comments), buffering multi-line `data:`, and on a blank line dispatches the accumulated event.
- Parsed events become `AgentEvent` (via `AgentEvent.fromMap`) and are placed on a `LinkedBlockingQueue`; consumers call `nextEvent()` (blocking) or iterate `AgentStream` (`Iterable<AgentEvent>` + `AutoCloseable`).
- `[DONE]` or an event of type `done` enqueues a `DONE_SENTINEL` ending the stream.

`AgentStream` also supports event-targeted HITL (`approve(event)`/`reject(event, reason)`) and a `waitForResult` fallback that aggregates from captured events. Event types (`enums/EventType`): `THINKING`, `TOOL_CALL`, `TOOL_RESULT`, `HANDOFF`, `WAITING`, `MESSAGE`, `ERROR`, `DONE`, `GUARDRAIL_PASS`, `GUARDRAIL_FAIL`.

---

## 7. Guardrails & credentials (SDK-side)

### Guardrails

Four `guardrailType` values:

- **`custom`** — a local `Function<String, GuardrailResult>` (from `@GuardrailDef` or `Guardrail.of(...)`). Compiled into a single combined `{name}_output_guardrail` worker.
- **`external`** — references an existing Conductor worker by name (no local function).
- **`llm`** — `LLMGuardrail`: server-side LLM policy evaluation.
- **`regex`** — `RegexGuardrail`: server-side pattern match (block/allow mode).

`GuardrailResult` is `pass()`, `fail(message)`, or `fix(fixedOutput)`. `OnFail` (`RETRY`/`RAISE`/`FIX`/`HUMAN`) drives the server's post-guardrail switch; `Position` is `INPUT` or `OUTPUT` (default). The combined worker enforces `maxRetries` (downgrading `retry`→`raise` once exhausted, and `fix`→`raise` when no fixed output is present), matching Python.

### Credentials

Tools/agents declare credential names as `List<String>` (e.g. `@Tool(credentials = {...})`, `HttpTool.credentials(...)`, `Agent.Builder.credentials(...)`), serialized so the server's execution token carries the `declared_names`. At runtime, before invoking a handler with declared secrets, `WorkerManager` pulls the execution token from `inputData["__agentspan_ctx__"]["execution_token"]` and calls `internal/WorkerCredentialFetcher` → `POST /api/workers/secrets` (`{token, names}`) → `Map<name,value>`. Resolution failures are **terminal** (`FAILED_WITH_TERMINAL_ERROR`) so Conductor doesn't burn retries on a config problem. Resolved secrets are placed in a **`ThreadLocal`** (`internal/CredentialContext`) for the handler's duration and cleared in a `finally` — they never enter task I/O, and tool code reads them via `ToolContext.getCredential(name)`. Typed errors: `CredentialNotFound/Auth/RateLimit/Service`.

---

## 8. Framework integration

Native framework objects are accepted via `Object`-typed drop-in overloads (`run/start/stream/deploy/serve/plan/resume`) and coerced in `AgentRuntime.coerceAgent`. The core class **never references a `compileOnly` framework type in a signature** — detection is by fully-qualified name walking the type hierarchy (`isInstanceOf`), so the SDK compiles and runs without those frameworks on the classpath; the JVM loads framework classes only when a user actually passes one. See [`../../framework-integration.md`](../../framework-integration.md).

| Framework wire value | Bridge / builder | Notes |
|---|---|---|
| `openai` | `frameworks/OpenAIAgent` (builder), `openai/GPTAssistantAgent` | OpenAI Agents SDK shape; handoffs → `frameworkConfig.handoffs` |
| `google_adk` | `frameworks/AdkBridge` | Native ADK `BaseAgent` (Llm/Sequential/Parallel/Loop) → `frameworkConfig` for `GoogleADKNormalizer` |
| `langchain` | `frameworks/LangChainBridge` + `LangChain4jAgent` | LangChain4j `ChatModel` + `@Tool` POJOs; model → `provider/model` string |
| `langgraph` | `LangChainBridge` (via `AgentExecutor.Builder`) | Recovers `chatModel`/`systemMessage` reflectively; validates `.build()` before shipping |
| `skill` | `skill/Skill` | `SKILL.md` directories; registers skill workers |
| `vercel_ai`, `claude_agent_sdk` | (enum-only wire values) | Routed to server normalizers |

`Framework` (`enums/Framework`) maps each wire value 1:1 to a server-side normalizer; `Framework.of(String)` resolves the agent's framework string and selects the native (`agentConfig`) vs framework (`framework`+`rawConfig`) request path.

---

## 9. Spring Boot adapter (`-spring` module)

`spring/` adds Spring Boot auto-configuration (`org.conductoross.conductor:conductor-agent-sdk-spring`). The `META-INF/spring/…AutoConfiguration.imports` file registers `AgentAutoConfiguration`, which wires three `@ConditionalOnMissingBean` beans:

- **`AgentConfig`** — from `agentspan.*` properties (`AgentProperties`: worker poll interval, thread count).
- **`AgentRuntime`** — built from the injected `ApiClient` + `AgentConfig`.
- **`AgentCatalog`** — discovers agents from the `ApplicationContext`.

Crucially, the `ApiClient` (server URL + auth) is **not** created here — it comes from the Conductor client's own `OrkesConductorClientAutoConfiguration` (pulled in via `conductor-client-spring`), configured under the `conductor.*` namespace (`conductor.root-uri`, `conductor.security.client.key-id/secret`). `@AutoConfiguration(after = OrkesConductorClientAutoConfiguration.class)` orders this correctly. All beans are conditional, so users can override any of them.

---

## 10. Java-specific design choices

- **Immutable value object + fluent `Builder`.** `Agent` is final-field immutable with a `~50`-setter `Agent.Builder`; varargs convenience overloads (`tools(…)`, `agents(…)`, `guardrails(…)`, `handoffs(…)`) accumulate. Validation (`build()`): name matches `^[a-zA-Z_][a-zA-Z0-9_-]*$`, `maxTurns >= 1`, `plannerContext` only with `PLAN_EXECUTE`.
- **Dual declarative styles.** Imperative builders *and* annotation-driven POJOs (`@AgentDef` methods resolved by `Agent.fromInstance` / `AgentRegistry`; `@Tool` and `@GuardrailDef` methods reflected by `ToolRegistry`). `@AgentDef` methods may return `String`, `PromptTemplate`, `Agent.Builder`, or `Agent`.

  > The idiom guide [`java.md`](java.md) frames the SDK for *both* Java 16+ (records, sealed types) and Java 8+ (POJOs). The shipped reference SDK targets the **Java 21** toolchain; user tool/output POJOs can be records or classes — `AgentConfigSerializer.generateJsonSchema` reflects declared fields either way, and `-parameters` preserves tool-parameter names.

- **Supplier-backed dynamic instructions** — `instructions(Supplier<String>)` re-evaluates per serialization (the closest Java analogue to Python's callable instructions).
- **Explicit runtime instances over a global singleton** — `AgentRuntime implements AutoCloseable`; `close()`/`shutdown()` releases the OkHttp dispatcher + connection pool (which otherwise leak idle threads across test suites).
- **Separation of transport and tuning** — `ApiClient` owns connectivity; `AgentConfig` owns only worker-runner tuning. This is a deliberate divergence from Python's combined config.
- **Lean control-plane client** — `AgentClient` is scoped to exactly five proprietary endpoints; everything standard reuses the Conductor SDK's typed clients, riding one shared auth/HTTP stack.
- **No hard framework coupling** — `compileOnly` framework deps + FQN-based coercion keep the core dependency-free at runtime.
- **Async via `CompletableFuture`** — every sync op has a `…Async` variant; `run = start + waitForResult`.

---

## 11. Testing

Test layout under `sdk/java/`:

| Location | Files | Approx. `@Test` |
|---|---|---|
| `src/test/java` (unit) | 24 test classes | ~241 |
| `e2e/` (integration, live server) | 26 files | ~162 |
| `spring/src/test/java` | 2 (`AgentAutoConfigurationTest`, `AgentCatalogTest`) | — |

- **Unit tests** are organized by package (`internal`, `model`, `tools`, `termination`, `plans`, `handoff`, `exceptions`, `execution`, `schedule`, `frameworks`) and run with JUnit 5 — no server required.
- **E2E suites** (`e2e/SuiteNN*.java`, e.g. `Suite8Guardrails`, `Suite14StatefulDomain`, `Suite18ToolTypes`, `Suite4McpTools`) are tagged `@Tag("e2e")` and **excluded by default**; run with `-Pe2e` (which also sets `maxParallelForks = 3`). They require a live Conductor server. Per project convention, e2e validation avoids using an LLM to judge correctness except where the test is specifically about output/eval quality.
- **Tooling:** Gradle (`java-library`), JaCoCo coverage (`jacocoTestReport`), Spotless with `palantirJavaFormat`.

---

## Uncertainties / flagged in-doc

- **`vercel_ai` / `claude_agent_sdk`** appear as `Framework` enum wire values but have no dedicated Java bridge class in `frameworks/`/`openai/` — documented as enum-only/server-normalizer routing rather than a first-class SDK builder. Verify against the server normalizer set if a Java-side bridge is expected.
- **Test `@Test` counts** are derived from raw `grep` of `@Test` occurrences (241 unit / 162 e2e) and class-file counts; treat as approximate, not authoritative per-method tallies.
