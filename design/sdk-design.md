# SDK Design

**Status:** Consolidated 2026-06-26

**Scope.** This is the canonical guide to authoring a Agentspan SDK in any language. It defines the contract every SDK must satisfy — the public API surface (Agent, tools, guardrails, strategies, memory, handoffs, termination, results, streaming), the `AgentConfig` JSON wire format, worker registration, the control-plane REST/SSE API, skills, and framework bridges — plus the ~89-feature parity matrix, per-language idiom guides, and acceptance testing. It is authoritative for *what* an SDK must do; it links to siblings ([api-design.md](api-design.md), [agentspan-design.md](agentspan-design.md), [guardrails-design.md](guardrails-design.md), [tool-execution-and-credentials-design.md](tool-execution-and-credentials-design.md), [framework-integration.md](framework-integration.md)) for the wire/platform detail, and to per-language docs for *how* to do it idiomatically.

---

## 1. Scope & Philosophy

### Everything is an Agent

A single `Agent` wraps an LLM + tools. An agent with sub-agents *is* a multi-agent system. There is one type to learn. Simple or complex, every agent is an instance of the same class; orchestration is selected by a `strategy` over its `agents` list.

### Reference implementation + translation guide

We use **Approach 2: a reference implementation plus translation guides.** The **Python SDK is the spec** — it is the executable definition of correct behavior. The **Java SDK (`sdk/java`)** is the reference for record/POJO-shaped languages. Every other SDK (TypeScript, Go, Kotlin, C#, Ruby) must reproduce *behavior* parity, not API shape: port the **model**, be idiomatic to the language.

Each SDK's job is identical:

1. **Define** agents, tools, guardrails as language-native constructs.
2. **Serialize** to the `AgentConfig` JSON the server expects (§3).
3. **Register** tool/guardrail/callback workers the server dispatches to (§3.6).
4. **Execute** via the control-plane REST API — start, deploy, compile, status, respond (§3.7).
5. **Stream** via SSE for real-time events (§2 / §3.8).
6. **Resolve** credentials via execution tokens at runtime (see [tool-execution-and-credentials-design.md](tool-execution-and-credentials-design.md)).

```
┌─────────────────────────────────────────────────┐
│                   SDK (any language)             │
│  Agent Definition → Serialization → AgentConfig  │
│  Worker Poll Loop → Tool Execution → Results     │
│  SSE Client → Event Stream → AgentStream         │
│  Credential Fetcher → Execution Token → Secrets  │
└──────────────────────┬──────────────────────────┘
                       │ REST + SSE (JSON)
┌──────────────────────▼──────────────────────────┐
│          Agentspan Server (Java)          │
│  Compiler → Conductor WorkflowDef                │
│  Executor → Conductor Workflow Engine            │
│  StreamRegistry → SSE Events                     │
│  CredentialService → AES-256-GCM Store           │
└─────────────────────────────────────────────────┘
```

**Correctness criterion:** equivalent agent definitions must produce **identical `AgentConfig` JSON** across SDKs. That is the primary thing the acceptance test (§5) checks.

### Build on the Conductor SDK

Agentspan runs on Conductor. Every SDK extends the equivalent Conductor SDK (`https://github.com/conductor-oss/{lang}-sdk` — java, go, python, csharp, javascript, rust, ruby, …) rather than rolling its own transport.

- Do **not** implement custom HTTP transport. Use Conductor's `ApiClient` for all remote calls — it owns token management, auth, timeouts, and config.
- Do **not** redefine connection properties already in the Conductor SDK config.
- Namespace: `org.conductoross.conductor.ai` (or the language equivalent).

Separation of concerns (as in Java):

- The **Conductor client** (`ApiClient`) owns server URL + auth.
- An **SDK config** object owns *only* worker-runner tuning (poll interval, thread count). It carries no connection details.
- `AgentRuntime` takes both and wires them together.

### Authentication & Configuration

OSS deployments need no auth. Orkes deployments use an API key (preferred) or legacy key/secret, passed through the Conductor `ApiClient`.

| Mode | Headers | Use case |
|------|---------|----------|
| API Key (preferred) | `Authorization: Bearer <api_key>` | Production |
| Legacy Key/Secret | `X-Auth-Key`, `X-Auth-Secret` | Backward compat |

Because the SDK builds on Conductor's `ApiClient`, the `CONDUCTOR_SERVER_URL` / `CONDUCTOR_AUTH_KEY` / `CONDUCTOR_AUTH_SECRET` variables are honored transitively — do not re-implement them. The `AGENTSPAN_*` variables are the SDK-level overrides read before constructing the client.

| Environment Variable | Default | Description |
|---------------------|---------|-------------|
| `AGENTSPAN_SERVER_URL` | `http://localhost:6767/api` | Server API URL |
| `AGENTSPAN_API_KEY` | — | Bearer token / API key |
| `AGENTSPAN_AUTH_KEY` / `AGENTSPAN_AUTH_SECRET` | — | Legacy auth |
| `AGENTSPAN_WORKER_POLL_INTERVAL` | `100` | Worker poll interval (ms) |
| `AGENTSPAN_WORKER_THREADS` | `1` | Threads per worker |
| `AGENTSPAN_LLM_RETRY_COUNT` | `3` | LLM call retry count |
| `AGENTSPAN_AUTO_START_WORKERS` | `true` | Auto-start worker processes |
| `AGENTSPAN_AUTO_START_SERVER` | `true` | Auto-start local server |
| `AGENTSPAN_DAEMON_WORKERS` | `true` | Kill workers on exit |
| `AGENTSPAN_STREAMING_ENABLED` | `true` | Enable SSE streaming |
| `AGENTSPAN_SECRET_STRICT_MODE` | `false` | No env-var fallback for credentials |
| `AGENTSPAN_INTEGRATIONS_AUTO_REGISTER` | `false` | Auto-register LLM integrations |
| `AGENTSPAN_LOG_LEVEL` | `INFO` | Logging level |

**URL normalization:** strip a trailing `/` and any `/api` suffix, then append `/api`.

---

## 2. The SDK Contract

Every SDK must expose the following public surface. Names follow the target language's conventions (`snake_case` in Python/Ruby, `camelCase` in JS/Java/Kotlin, `PascalCase` in C#), but the **semantics must be identical**. This section is the conceptual model; §3 is the wire format it serializes to.

### 2.1 Agent

The single orchestration primitive — an immutable, declarative config built with a fluent builder (or constructor / data class as idiomatic). `name` is required and must match `^[a-zA-Z_][a-zA-Z0-9_-]*$`. `maxTurns` defaults to 25.

```java
Agent agent = Agent.builder()
    .name("assistant")
    .model("openai/gpt-4o")          // "provider/model"; omit for external agents
    .instructions("You are helpful.")
    .maxTurns(10)
    .build();
```

| Field | Type | Default | Notes |
|-------|------|---------|-------|
| `name` | string | required | Unique agent name |
| `model` | string | null | `provider/model`; **omit ⇒ external** (references a deployed workflow) |
| `instructions` | string \| callable \| PromptTemplate | null | System prompt; **callable is re-evaluated at serialize time** |
| `tools` | Tool[] | [] | Tools available to this agent |
| `agents` | Agent[] | [] | Sub-agents (multi-agent) |
| `strategy` | Strategy enum | null | Orchestration; emitted only when `agents` non-empty |
| `router` | Agent \| callable | null | Router for `router` strategy |
| `outputType` | class/schema | null | Structured output type |
| `guardrails` | Guardrail[] | [] | Input/output validators |
| `memory` | ConversationMemory | null | Conversation history |
| `maxTurns` | int | 25 | Max LLM call turns |
| `maxTokens` / `temperature` | int / float | null | LLM params |
| `timeoutSeconds` | int | 0 | Execution timeout (0 = none) |
| `external` | bool | false | Runs elsewhere |
| `stopWhen` / `termination` / `gate` | — | null | Stop conditions (§2.6) |
| `handoffs` / `allowedTransitions` | — | [] / null | Handoff triggers + reachability (§2.7) |
| `introduction` / `metadata` | string / map | null | Self-intro, arbitrary metadata |
| `callbacks` | CallbackHandler[] | [] | Lifecycle hooks (§2.9) |
| `enablePlanning` | bool | false | Plan-first preamble (ADK feature) |
| `includeContents` | string | null | `"default"` full parent context, `"none"` fresh |
| `thinkingBudgetTokens` | int | null | Extended thinking budget |
| `requiredTools` | string[] | null | Tools the LLM must use |
| `codeExecutionConfig` / `cliConfig` | — | null | Sandbox / CLI allowlist |
| `credentials` | (string \| CredentialFile)[] | null | Agent-level credentials |

**Sequential sugar:** `a >> b` (Python/Kotlin/C#/Ruby operator; `a.then(b)` in Java; `.pipe()` in TS) returns a new `SEQUENTIAL` agent. Chaining **flattens**: `a >> b >> c` → `Agent(name="a_b_c", strategy=SEQUENTIAL, agents=[a,b,c])`, never nested.

**`@agent` / `@AgentDef` annotation (alternative declarative path):** define an agent from an annotated method/function. Attributes mirror the constructor (`name`, `model`, `instructions`, `tools`, `guardrails`, `agents`, `strategy`, `maxTurns`, `maxTokens`, `temperature`, `credentials`, `contextWindowBudget`). Resolve with `Agent.fromInstance(obj[, name])`. Return type controls behavior: `void` (attrs only), `String` (dynamic instructions), `PromptTemplate`, `Agent.Builder` (decorate then build), or `Agent` (full factory). `@Tool` / `@GuardrailDef` methods on the same object attach to the agents.

### 2.2 Strategies

Multi-agent orchestration selected by `strategy` over `agents`:

`HANDOFF` (default), `SEQUENTIAL`, `PARALLEL`, `ROUTER`, `ROUND_ROBIN`, `RANDOM`, `SWARM`, `MANUAL`, `PLAN_EXECUTE`.

Server-side compilation: handoff/swarm/manual → `SWITCH`-driven loops, sequential → chained sub-workflows, parallel → `FORK_JOIN`, router → `SWITCH`. `PLAN_EXECUTE` uses named `planner` (required) + `fallback` (optional) slots instead of positional `agents` (§3.5).

Some strategies expect locally-registered workers by name (in the Python reference). Note: **for non-Python SDKs, the server handles several of these internally** — verify which by running the feature's example *without* a worker (see §15 lessons). Worker name patterns:

- **SWARM** — `{src}_transfer_to_{dst}`, `{name}_check_transfer`, `{name}_handoff_check`. (Transfer tools `transfer_to_{agent}` are **auto-generated by the server** — do not add them manually.)
- **MANUAL** — `{name}_process_selection`.

### 2.3 Tools

#### Custom (local) tools

Two ways to define a local tool:

1. **Annotation/decorator** — mark a method `@tool` / `@Tool(name, description, …)`; discover via reflection (`ToolRegistry.fromInstance(obj)` → `List<ToolDef>`).
2. **Builder** — construct a `ToolDef`/`ToolConfig` directly.

The SDK extracts function name, docstring, and parameter schema (type hints), generates JSON Schema, registers a Conductor SIMPLE task, and starts a worker (§3.6). A `ToolDef` carries: `name`, `description`, in/out `schema`, local `func`, `toolType` (default `worker`), `approvalRequired` (HITL gate), `credentials`, `timeoutSeconds`, retry policy, `maxCalls`, `guardrails`, `agentRef`, `stateful`, `isolated` (credential isolation, default true).

```python
@tool
def get_weather(city: str) -> str:
    """Get current weather for a city."""
    return f"72F and sunny in {city}"
```

**ToolContext (dependency injection):** when a tool declares a `ToolContext` parameter, the SDK injects `session_id`, `execution_id`, `agent_name`, `metadata`, `dependencies`, `state`. The server passes `__agentspan_ctx__` in task input; the SDK extracts/populates it and **strips it before calling the user function**. State mutations are captured back into the result under `_state_updates` (§3.10).

**External / by-reference tools:** a tool with no local function — the SDK emits only the task name; a remote worker (possibly another language/machine) picks it up. This is the core mechanism for distributed agent systems. Every SDK must support defining tools by reference (name + schema only).

#### Built-in / server-side tools

Provide factories/builders for each; all produce the same tool model. These execute **on the server — no local worker** (except `agent_tool`, which depends on the sub-agent).

| Tool | Constructor shape | toolType |
|---|---|---|
| HTTP | `httpTool(name, description, url, method, headers, …, credentials)` | `http` |
| API (OpenAPI/Swagger/Postman auto-discovery) | `apiTool(url, name, …, maxTools=64, credentials)` | `api` |
| MCP | `mcpTool(serverUrl, name, …, toolNames, maxTools=64, credentials)` | `mcp` |
| Agent-as-tool | `agentTool(agent[, description])` | `agent_tool` |
| Human (HITL) | `humanTool(name, description[, inputSchema])` | `human` |
| Media (image/audio/video) | `imageTool(name, desc, provider, model[, schema])` (+audio/video) | `generate_*` |
| PDF | `pdfTool([name, description, inputSchema, defaults])` | `generate_pdf` |
| RAG | `searchTool(…)` / `indexTool(…)` | `rag_search` / `rag_index` |

**Critical:** media (`generate_*`) and RAG tools are **server-side only** — never execute them as worker tasks. HTTP headers may reference credentials with `${NAME}` syntax, resolved server-side at execution time; all placeholders must be declared in `credentials`.

### 2.4 Guardrails

Input/output validation attached to an agent (or a tool). All produce a `GuardrailDef`/`GuardrailConfig` with `position` (`INPUT`/`OUTPUT`), `onFail` (`RETRY`/`RAISE`/`FIX`/`HUMAN`), `maxRetries`, and a `guardrailType`. See [guardrails-design.md](guardrails-design.md) for the full compilation model.

| Type | Execution | Constructor |
|---|---|---|
| Custom | SDK worker (`{agent}_output_guardrail` / `{guardrail.name}`) | `Guardrail.of(name, fn)` / `@guardrail` — `fn: String → GuardrailResult` |
| Regex | Server-side INLINE (JS) | `RegexGuardrail.builder().patterns(…).mode("block"\|"allow")` |
| LLM | Server-side LLM call | `LLMGuardrail.builder().model(…).policy(…)` |
| External | Remote worker (no local worker) | `Guardrail.external(name)` |

`GuardrailResult`: `passed` (bool), `message` (failure reason), `fixedOutput` (for `onFail=fix`). **OnFail semantics:** `RETRY` re-runs the LLM with feedback (DO_WHILE loop); `RAISE` fails the execution; `FIX` uses `fixedOutput`; `HUMAN` pauses for review (HUMAN task). The default `onFail` is now **`raise` uniformly across all four SDKs**. `human`+`input` is rejected at construction time in **all four SDKs** (an input guardrail runs client-side and cannot pause an execution). Guardrails attach at **two levels** — `agent.guardrails` and `tool.guardrails`; the runtime must register workers for both.

### 2.5 Results & Streaming

#### Execution surface (AgentRuntime)

`AutoCloseable` — shut down workers and release the HTTP pool on close. Provide both sync and async variants of each. `run` = `start` then wait. Workers register inside `start` so they bind to the correct queue.

| Method | Purpose | Returns |
|---|---|---|
| `run(agent, prompt)` | Execute synchronously | `AgentResult` |
| `start(agent, prompt)` | Fire-and-forget | `AgentHandle` |
| `stream(agent, prompt)` | Execute and stream events | `AgentStream` |
| `plan(agent)` | Compile to a workflow def without executing (dry run) | `ExecutionPlan` |
| `deploy(agents…)` | Compile + register (CI/CD); no workers, no execution | `DeploymentInfo` |
| `deploy(agent, schedules)` | Deploy + reconcile cron schedules (§2.8) | — |
| `serve(agents…)` | Register workers and poll until interrupted | — |
| `resume(executionId, agent)` | Re-attach to a running execution, re-register workers | — |
| `schedules()` | Cron-schedule lifecycle accessor | — |
| `configure(config)` / `shutdown()` | Pre-configure / tear down the singleton runtime | — |

The runtime operates on a lazily-initialized **singleton** or an explicit instance, supports language-appropriate resource management (Python `with`, Java try-with-resources, Go `defer`, C# `using`, Ruby `ensure`), and auto-starts workers/local server when configured.

#### AgentResult

`output` (always a dict — normalized; raw or typed via a class), `status` (`COMPLETED`/`FAILED`/`TERMINATED`/`TIMED_OUT`), `finishReason` (`STOP`/`LENGTH`/`TOOL_CALLS`/`ERROR`/`CANCELLED`/`TIMEOUT`/`GUARDRAIL`/`REJECTED`), `messages`, `toolCalls`, `tokenUsage` (prompt/completion/total), `error`, `events`, `subResults` (per-agent, parallel), `correlationId`. Convenience: `isSuccess`, `isFailed`, `isRejected`, `printResult`. Token usage and tool calls are enriched from the completed workflow via the Conductor workflow client.

**Result normalization** (`output` always a dict): dict → as-is; string-on-success → `{"result": s}`; null-on-success → `{"result": null}`; string-on-failure → `{"error": s, "status": "FAILED"}`; null-on-failure → `{"error": "Unknown error", "status": "FAILED"}`.

#### AgentHandle / AgentStatus

`AgentHandle` (from `start`): `getStatus`, `waitForResult(timeout, poll)`, `isWaiting`, `waitUntilWaiting(timeout)`, `approve`/`reject`/`respond`/`send`, `pause`/`resume`/`cancel`, `stream`. Every method has sync + async variants. `AgentStatus`: `executionId`, `isComplete`/`isRunning`/`isWaiting`, `output`, `status`, `reason`, `currentTask`, `messages`, `pendingTool`.

#### Streaming & HITL

`stream` returns an iterable `AgentStream` of typed `AgentEvent` plus HITL controls. After iteration: `events` (all captured), `result` (built from events), `getResult()` (drain + return).

`EventType` enum (every SDK): `THINKING, TOOL_CALL, TOOL_RESULT, HANDOFF, WAITING, MESSAGE, ERROR, DONE, GUARDRAIL_PASS, GUARDRAIL_FAIL`. Server-only types (`context_condensed`, `subagent_start`, `subagent_stop`) are **not** in the enum — pass them through as raw events. Before exposing args, **strip internal keys** `_agent_state`, `method`.

**HITL:** on pause the agent emits `WAITING` carrying the pending tool (`taskRefName`, name, params, optional response/UI schema). Respond via `approve()` / `approve(comment)` / `reject(reason)` / `respond(map)`. **Route to the right execution:** under HANDOFF/SEQUENTIAL/PARALLEL the HUMAN task lives in a *sub-execution* — pass the `WAITING` event to the approve/reject call so it targets that event's `executionId`, not the root. After approving a sub-execution, poll workflow status via `waitForResult` rather than blocking on the original stream. See [api-design.md](api-design.md) and `2026-03-20-hitl-endpoint-design.md` for endpoint detail.

**SSE client requirements:** parse the wire format (event/id/data), handle heartbeat comments (`:` lines), reconnect with `Last-Event-ID`, detect SSE unavailability (only heartbeats for 15s → fall back to polling `GET /{id}/status`), yield parsed events.

### 2.6 Termination, Stop & Gate

**Termination conditions** are composable with `and`/`or` (operator overloading or builder), each implementing both `toJSON()` (wire) and `shouldTerminate(context)` (worker evaluation → `{shouldTerminate, reason}`):

- `MaxMessageTermination.of(n)`
- `TextMentionTermination.of(text[, caseSensitive])`
- `StopMessageTermination.of(text)`
- `TokenUsageTermination.ofTotal/ofPrompt/ofCompletion(n)`

```java
MaxMessageTermination.of(10).or(TextMentionTermination.of("DONE"))
```

**Gate** stops a sequential pipeline when an agent's output contains a sentinel: `new TextGate(text[, caseSensitive])`, attached via `.gate(...)`. Compiled to an INLINE (text) or SIMPLE (worker) task that returns `{"decision": "continue"|"stop"}`. **stop_when** is a callable stop condition registered as `{agent}_stop_when`.

### 2.7 Handoffs

SWARM transfer triggers, each naming a target agent:

- `OnTextMention.of(text, target)` — output contains text.
- `OnToolResult.of(tool, target[, resultContains])` — after a tool runs.
- `OnCondition(target, predicate)` — local predicate worker (`{agent}_handoff_{target}`).

Restrict reachability with `allowedTransitions` (source → allowed targets), enforced server-side.

### 2.8 Memory

**ConversationMemory** — session history: `addUser/Assistant/SystemMessage`, `addToolCall`, `addToolResult`, `toChatMessages`, `clear`. With `maxMessages` set, trim oldest but always preserve system messages. Serializes as `{"messages": [...], "maxMessages": N}`.

**SemanticMemory** — cross-session recall (SDK-side, all four SDKs): `add`, `search(query, topK)`, `delete`, `clear`, `listAll`. This is a **client-side keyword (Jaccard-overlap) store** — it is **not** a vector DB / embedding feature, and is **not serialized to the wire**. Pluggable `MemoryStore`; SDK must ship at least `InMemoryStore` (keyword-overlap similarity).

### 2.9 Callbacks

Lifecycle hooks registered on the agent, run as local workers. Either single functions (`beforeModelCallback`, `afterModelCallback`, `beforeAgentCallback`, `afterAgentCallback`) or a composable `CallbackHandler` overriding any of `onAgentStart/End`, `onModelStart/End`, `onToolStart/End`. Returning a non-empty map short-circuits/overrides at that position; multiple handlers run in order.

Wire positions are `before_agent`, `after_agent`, `before_model`, `after_model`, `before_tool`, `after_tool` (**not** the method names). Serialized as `{"position": "<wire>", "taskName": "{agent}_<wire>"}`; the worker bridges server input (`{messages, llm_result}`) to the handler's typed signature, supplying `agentName` from the registration closure.

### 2.10 Code Execution & Schedules

**Code execution:** `CodeExecutionConfig` (`enabled`, `allowedLanguages`, `allowedCommands`, `timeout`) and `cliConfig` (CLI allowlist). Executor implementations: `LocalCodeExecutor`, `DockerCodeExecutor`, `JupyterCodeExecutor`, `ServerlessCodeExecutor`; `as_tool()` converts an executor to a tool. See [tool-execution-and-credentials-design.md](tool-execution-and-credentials-design.md).

**Schedules:** declarative cron via `deploy(agent, schedules)`:

```java
Schedule.builder().name("weekday-9am").cron("0 0 9 * * MON-FRI")
    .timezone("America/Los_Angeles").input(Map.of("channel", "#eng")).build()
```

Tri-state reconcile: `null` = leave untouched, empty list = purge, non-empty = upsert + prune others. Lifecycle via `runtime.schedules()`: `save`, `get`, `list`, `pause`, `resume`, `delete`, `runNow`, `previewNext(cron, n)`, `reconcile`. See [sentinel-agents.md](sentinel-agents.md).

### 2.11 Exceptions

`AgentspanError` (base), `AgentAPIError` (server error), `AgentNotFoundError`, `ConfigurationError` (invalid config). Credential errors: `CredentialNotFoundError`, `CredentialAuthError`, `CredentialRateLimitError` (120 calls/min), `CredentialServiceError`.

### 2.12 Feature matrix (summary)

The full contract is **~89 features**, each traceable: concept → Python reference module → wire-format key → server handler → kitchen-sink stage. There is no single authoritative per-row matrix in the repo; the grouped summary below is the working inventory.

**SDK parity status.** All four SDKs (Python, TypeScript, Java, C#) are now at **essentially complete parity** — the recent cross-SDK fixes closed the former Java/C# gaps, leaving only one honest open item (the language-driven provider/framework asymmetries, below). The fixes:

- **SemanticMemory** — now in **all four SDKs** (Java added). Reminder: it is a client-side keyword (Jaccard-overlap) store, not a vector DB; not serialized to the wire (§2.8).
- **ConversationMemory** — now in **all four SDKs** (C# added); wire shape `{messages, maxMessages}`.
- **`api_tool`** (OpenAPI/Swagger/Postman discovery) — now in **all four SDKs** (Java added; C# also gained the `${NAME}` credential-placeholder validation).
- **External guardrail** (`Guardrail.external`) — now in **all four SDKs** (C# added).
- **Tier-1 credential accessor** — now in **all four SDKs** (Python `get_secret`, TS `getCredential`, Java `ToolContext.getCredential`, C# `ToolContext.GetCredential` / `Secrets.Get`).
- **Default guardrail `onFail`** is now **`raise` uniformly** across all four; `human`+`input` is rejected at construction in all four.

- **Code-execution executors** — now **full across all four SDKs**: Local / Docker / Jupyter / Serverless ship in Python, TS, Java, and C#. The only difference is the Jupyter *mechanism* (Python in-process `jupyter_client`; TS `jupyter run` CLI; Java/C# Jupyter Kernel Gateway over HTTP); the executor itself is present everywhere. See [tool-execution-and-credentials-design.md](tool-execution-and-credentials-design.md) §2.10.
- **Optional config-field gaps — closed.** C# now emits `synthesize`, `prefillTools`, `cliConfig` (with `workingDir`), `reasoningEffort`, `contextWindowBudget`, and `maskedFields`; TS now emits `reasoningEffort`, `contextWindowBudget`, and `maskedFields`. All four SDKs now emit the full optional-field set.
- **Server `maskedFields` — now applied.** All four SDKs emit `maskedFields`, and the server now wires it into the compiled `WorkflowDef` (in `AgentCompiler.compile()`'s shared post-processing step, so it covers every compile shape; recursively-compiled sub-agents carry their own masked fields). The named input/output fields are redacted in execution history/UI. (Previously the field was accepted but dropped.)

The one remaining honest open item:

- **Provider/framework asymmetries (language-support driven):** the `claude-code` model + `ClaudeCode` config are Python/TS only; the Claude Agent SDK framework is Python-only; Vercel AI SDK is TS-only; OCG is Python-only.

Treat the matrix below as the shared reference set; the only remaining delta is the open item above.

| Group | Features (count) | Examples |
|---|---|---|
| Agent core | Agent def, `>>` chaining, structured output, introductions, metadata | #1, 30, 38, 39 |
| Strategies (9) | handoff, sequential, parallel, router, round_robin, random, swarm, manual, plan_execute | #2–9, +plan_execute |
| Tools (12 documented + internal `pull_workflow_messages`) | worker, http, api, mcp, agent_tool, human, generate_image/audio/video/pdf, rag_search/index | #10–16, 89 |
| Tool features | approval (HITL), ToolContext, credentials, tool-guardrails, external | #17–21 |
| Guardrails | regex, llm, custom, external × onFail retry/raise/fix/human | #22–29 |
| Memory | ConversationMemory, SemanticMemory | #31, 32 |
| Control flow | termination (composable), handoffs (3), allowed transitions, gate, stop_when, required_tools | #33–37, 71, 77, 70 |
| HITL | approve, reject, feedback | #40–42 |
| Streaming / exec | SSE, async stream, polling fallback, run/async, start, deploy, serve, plan | #43–51 |
| Credentials (7 modes) | isolated, in-process, CLI, HTTP header, MCP, framework, external | #52–57 |
| Code exec (4) | local, docker, jupyter, serverless | #58–61 |
| Advanced agent | callbacks, PromptTemplate, token tracking, thinking, include_contents, planner, CLI config, context condensation | #62–73 |
| SDK utilities | scatter_gather, agent discovery, OTel tracing | #74–76 |
| Testing (6) | mock_run, expect, assertions, record/replay, strategy validators, eval runner | #78–83 |
| Validation (4) | runner, judge, native execution, HTML report | #84–87 |
| Distributed | external agent | #88 |

A new SDK is **feature-complete** when all ~89 are implemented (parity across the four shipped SDKs is now essentially complete — see the parity-status note above; the only standing caveat is the language-driven provider/framework asymmetries, not an SDK feature gap), the kitchen sink produces identical `AgentConfig` JSON and executes end-to-end, both sync and async APIs work, the validation report generates, and all Python examples are ported (§5).

---

## 3. Serialization, Workers & Control Plane

The SDK's core job is to serialize the agent tree into the `AgentConfig` JSON the server compiles into a Conductor `WorkflowDef`. **Producing identical JSON for equivalent definitions is the primary correctness criterion.** See `agent-schema.json` / `agent-schema.md` for the formal wire contract and `agent-structure.md` for the field → JSON-key mapping; this section synthesizes the rules.

### 3.1 Top-level AgentConfig

```json
{
  "name": "agent_name",
  "model": "provider/model_name",
  "strategy": "handoff|sequential|parallel|router|round_robin|random|swarm|manual|plan_execute",
  "maxTurns": 25,
  "timeoutSeconds": 300,
  "external": false,
  "instructions": "string | { prompt_template } | null",
  "tools": [ ToolConfig... ],
  "agents": [ AgentConfig... ],
  "router": "AgentConfig | { taskName }",
  "outputType": { "schema": {...}, "className": "MyModel" },
  "guardrails": [ GuardrailConfig... ],
  "memory": { "messages": [...], "maxMessages": 50 },
  "maxTokens": 4096, "temperature": 0.7,
  "stopWhen": { "taskName": "agent_name_stop_when" },
  "termination": TerminationConfig,
  "handoffs": [ HandoffConfig... ],
  "allowedTransitions": { "agent_a": ["agent_b"] },
  "introduction": "...", "metadata": { "key": "value" },
  "enablePlanning": true,
  "planner": AgentConfig, "fallback": AgentConfig, "fallbackMaxTurns": 5,
  "callbacks": [ { "position": "before_agent", "taskName": "agent_name_before_agent" } ],
  "includeContents": "default|none",
  "thinkingConfig": { "enabled": true, "budgetTokens": 1024 },
  "requiredTools": ["tool_a"],
  "gate": GateConfig,
  "codeExecution": { "enabled": true, "allowedLanguages": ["python"], "allowedCommands": ["python3"], "timeout": 30 },
  "cliConfig": { "enabled": true, "allowedCommands": ["git","gh"], "timeout": 30, "allowShell": false },
  "credentials": ["GITHUB_TOKEN"]
}
```

**Rules:** all keys are **camelCase**; omit `null`-valued keys; `agents` is recursive; `strategy` is emitted only when `agents` is non-empty (or PLAN_EXECUTE slots exist); `synthesize` is emitted only when `false`. Dynamic instructions resolve at serialize time.

### 3.2 ToolConfig

```json
{
  "name": "tool_name",
  "description": "...",
  "inputSchema": { "type": "object", "properties": {...}, "required": [...] },
  "toolType": "worker|http|api|mcp|agent_tool|human|generate_image|generate_audio|generate_video|generate_pdf|rag_search|rag_index",
  "outputSchema": {...},
  "approvalRequired": true,
  "timeoutSeconds": 0,
  "config": { "url": "...", "method": "GET", "headers": {"Authorization": "Bearer ${API_KEY}"}, "credentials": ["API_KEY"] },
  "guardrails": [ GuardrailConfig... ]
}
```

**Execution model** (which side runs it, whether an SDK worker is needed):

| toolType | Conductor task | SDK worker? |
|----------|---------------|-------------|
| `worker` | SIMPLE | **Yes** (or none ⇒ external/remote) |
| `http` / `api` | HTTP (`api` via `LIST_API_TOOLS` discovery) | No |
| `mcp` | CALL_MCP_TOOL | No |
| `agent_tool` | SUB_WORKFLOW | Depends on sub-agent |
| `human` | HUMAN | No |
| `generate_image/audio/video/pdf` | GENERATE_* | No (server-only) |
| `rag_search` / `rag_index` | LLM_SEARCH_INDEX / LLM_INDEX_TEXT | No (server-only) |

### 3.3 GuardrailConfig

```json
{ "name": "...", "position": "input|output", "onFail": "retry|raise|fix|human", "maxRetries": 3,
  "guardrailType": "regex|llm|custom|external",
  "patterns": ["\\b\\d{3}-\\d{2}-\\d{4}\\b"], "mode": "block|allow", "message": "...",
  "model": "openai/gpt-4o", "policy": "...", "maxTokens": 100, "taskName": "guardrail_worker_name" }
```

`regex` → server INLINE JS (patterns/mode/message); `llm` → server LLM_CHAT_COMPLETE (model/policy/maxTokens); `custom` → SDK SIMPLE worker (taskName); `external` → remote SIMPLE (taskName, no local worker).

### 3.4 Other config shapes

- **TerminationConfig** (composable): `{"type":"text_mention","text":"DONE","caseSensitive":false}`, `stop_message`, `max_message`, `token_usage`, plus `{"type":"and|or","conditions":[…]}`.
- **HandoffConfig**: `on_tool_result` (toolName, resultContains), `on_text_mention` (text), `on_condition` (taskName).
- **PromptTemplate instructions**: `{"type":"prompt_template","name":"...","variables":{...},"version":1}`.
- **GateConfig**: `{"type":"text_contains","text":"APPROVED","caseSensitive":true}` or `{"taskName":"agent_name_gate"}`.
- **OutputType**: `{"schema":{…JSON Schema…},"className":"ArticleScore"}`.

### 3.5 PLAN_EXECUTE — typed plan builders + `Ref`

`PLAN_EXECUTE` (a.k.a. PAC/PAE) splits a task into a **planner** agent that emits a JSON DAG of operations and a server-compiled deterministic Conductor sub-workflow. Every SDK exposing it must provide: a `plan_execute` strategy value; `planner` (required) + `fallback` (optional) sub-agent slots (full `AgentConfig`, not booleans); typed builders `Plan`/`Step`/`Op`/`Generate`/`Validation`/`Action`; a `Ref(stepId)` helper; and a `run(agent, prompt, plan=…)` overload forwarding the plan as `static_plan`.

Plan wire shape (must match byte-for-byte across SDKs for round-tripping):

```json
{
  "steps": [
    { "id": "<id>", "depends_on": ["<id>"], "parallel": false,
      "operations": [
        { "tool": "<tool>", "args": { <literal map> } },
        { "tool": "<tool>", "generate": { "instructions": "...", "output_schema": "...", "max_tokens": 4096, "context": "..." } }
      ] }
  ],
  "validation": [ { "tool": "<validator>", "args": {...}, "success_condition": "$.passed === true" } ],
  "on_success": [ ... ], "on_failure": [ ... ]
}
```

`Ref("step_id")` wires the whole output of an upstream step into a downstream arg; the serializer walks every plan-value tree (`Op.args`, `Generate.context`, `Validation.args`, `Action.args`) and replaces `Ref` with `{"$ref": "step_id"}`. **Validation rules (hard errors):** self-refs; refs to a non-existent step; refs to a step not in `depends_on`. `Op` takes literal `args` **or** a `Generate` (per-op LLM call). `Context.text(...)` / `Context.url(...)` supply planner reference material (URLs fetched per run; support `${CRED_NAME}`).

**`static_plan`** (skip the planner LLM): forward the supplied plan as top-level `static_plan` on `POST /api/agent/start`. The server reads `workflow.input.static_plan` as highest-priority Case-0 and discards the planner's output. Use for tests, replays, and externally-planned pipelines.

### 3.6 Workers

Local tool functions, callbacks, guardrails, and termination/gate/stop conditions are registered as Conductor workers that poll for tasks. Walk the agent tree (sub-agents, router, agent-tools) and register every local handler.

**How a tool becomes a worker:** generate a task definition → register a worker that receives JSON input, extracts `__agentspan_ctx__`, resolves credentials, deserializes args (coercing types, §3.9), calls the user function, serializes the return → start a poll loop reporting success/failure to Conductor.

**Worker configuration:** poll interval 100ms; threads 1; daemon true; task-def `timeoutSeconds` **MUST be 0** (agent-level `timeoutSeconds` controls duration — a hardcoded task timeout prematurely kills long agents); `responseTimeoutSeconds` 3600 (Conductor minimum is 1s); retry count 2, delay 2s, LINEAR_BACKOFF.

**System worker names** (server expects these exactly; collected recursively through nested/`agent_tool` agents):

| Worker | Name pattern | Created when |
|---|---|---|
| Tool | `{tool.name}` | `@tool` function |
| Tool-level guardrail | `{guardrail.name}` | tool has guardrails |
| Output guardrail wrapper | `{agent}_output_guardrail` | agent has custom guardrails |
| stop_when / termination / gate | `{agent}_stop_when` / `_termination` / `_gate` | the field is set/callable |
| check_transfer | `{agent}_check_transfer` | agent has tools AND sub-agents |
| router_fn | `{agent}_router_fn` | ROUTER + callable router |
| handoff_check | `{agent}_handoff_check` | non-empty `handoffs` |
| process_selection | `{agent}_process_selection` | MANUAL |
| Callback | `{agent}_{position}` | callback handler for that position |

**Stateful agents** get a per-execution domain (a `runId` UUID) used as `taskToDomain`; register their workers under that domain so concurrent runs don't dequeue each other's tasks. An agent is stateful if `stateful=true`, any tool is stateful, or any descendant is. See [stateful-agents.md](stateful-agents.md).

**External workers** (by reference): emit the task name, register no local worker, trust a remote worker to pick it up.

**Circuit breaker:** disable a tool after 10 consecutive failures (per tool name, module-level, persists across workflows); reset on any success or via `reset_circuit_breaker(name)`. When open, throw immediately.

### 3.7 Control-plane API

All calls go through the Conductor `ApiClient`; map transport errors to typed SDK exceptions (not-found vs. generic). Base URL `{server_url}/agent`. Full endpoint detail in [api-design.md](api-design.md); platform context in [agentspan-design.md](agentspan-design.md).

| Method | Endpoint | Notes |
|---|---|---|
| compile | `POST /api/agent/compile` | returns `workflowDef`, no execution |
| deploy | `POST /api/agent/deploy` | compile + register; returns `registeredName` + `workflowDef`, **no** `executionId` |
| start | `POST /api/agent/start` | returns `{executionId, registeredName}` |
| status | `GET /api/agent/{executionId}/status` | poll |
| respond (HITL) | `POST /api/agent/{executionId}/respond` | `{approved}` / `{approved,reason}` / `{message}` |
| stream | `GET /api/agent/stream/{executionId}` | SSE; `Last-Event-ID` reconnect |
| events (framework push) | `POST /api/agent/{executionId}/events` | workers push intermediate events |
| list / search / detail | `GET /api/agent/list`, `/executions`, `/execution/{id}` | |
| delete | `DELETE /api/agent/{name}` | |

**Start payload** carries the compiled `agentConfig` (or `framework`+`rawConfig`), `prompt`, and optional fields. Presence rules: `sessionId` **always present** (empty string if unset); `media` **always present** (empty array); `idempotencyKey` only if provided; `timeoutSeconds`/`credentials`/`static_plan` only if provided.

```json
{ "agentConfig": {...}, "prompt": "...", "sessionId": "", "media": [],
  "idempotencyKey": "optional", "timeoutSeconds": 300, "credentials": ["CRED_A"] }
```

**Idempotency:** `idempotencyKey` → Conductor `correlationId`. Server searches RUNNING/COMPLETED (not FAILED) workflows with the same agent name + correlationId; returns the existing `executionId` if found, else creates a new execution. Failed workflows are **not** deduplicated. `correlationId` is also auto-generated by the SDK as a UUID per call for client-side tracing.

### 3.8 SSE wire format

```
event: <type>     → AgentEvent.type
id: <int>         → reconnection cursor
data: <json>      → AgentEvent fields (blank line ends the event)
:<comment>        → heartbeat (ignore; sent every 15s)
```

Reconnect with `Last-Event-ID`; the server replays from a 200-event / 5-min buffer. **Framework event push** to `POST /agent/{id}/events` supports exactly 6 types — `thinking`, `tool_call`, `tool_result`, `context_condensed`, `subagent_start`, `subagent_stop` — unknown types are silently dropped.

### 3.9 Type coercion (worker dispatch)

Coerce tool inputs from Conductor's type system to the target language, applied **in order**, all failures **silent** (return original, never throw): (1) null/unknown → unchanged; (2) unwrap `Optional<X>` and recurse; (3) already-matching → unchanged; (4) string→list/dict via `JSON.parse` (fallback to string); (5) dict/list→string via `JSON.stringify` (AI_MODEL args arrive parsed; tools wanting JSON strings must re-serialize); (6) string→int/float/bool (`"true"/"1"/"yes"`→true, `"false"/"0"/"no"`→false); (7) fallback unchanged.

### 3.10 Other server contracts SDKs must honor

- **ToolContext.state capture:** append non-empty post-execution `state` to the result under `_state_updates` (merged into a dict result, or wrapped as `{"result": <orig>, "_state_updates": {...}}`). The server persists and strips it.
- **Execution token extraction:** primary `task.input_data.__agentspan_ctx__.execution_token`, fallback `task.workflow_input.…`. Strip `__agentspan_ctx__` before calling the tool. See [tool-execution-and-credentials-design.md](tool-execution-and-credentials-design.md) and `secret-injection-contract.md`.
- **required_tools** wraps the agent loop in an outer DO_WHILE (≤3 outer iterations) — can triple worst-case execution time.
- **Class-instance normalization:** if an SDK type has a `toGuardrailDef()`/`toJSON()`/`toWireFormat()` method, the serializer must call it before reading properties (duck-typed).

### 3.11 Sync + async dual model

Every execution API has sync and async variants; the internal implementation should be async-native with blocking sync wrappers.

| Language | Async primitive | Sync wrapper |
|---|---|---|
| Python | `asyncio` | `asyncio.run()` in thread |
| TypeScript | `Promise` | inherently async |
| Go | goroutines + channels | blocking default |
| Java | `CompletableFuture` / virtual threads | `.get()`/`.join()` |
| Kotlin | `suspend` / coroutines | `runBlocking {}` |
| C# | `Task<T>` | `.GetAwaiter().GetResult()` |
| Ruby | `Async` / `Fiber` | blocking default |

---

## 4. Skills (agentskills.io directories as agents)

Skills make an [agentskills.io](https://agentskills.io/specification)-compatible directory a **first-class `Agent`** — composable, durable, observable. `skill("./dg")` works out of the box: convention-based discovery, no manifest. Because `skill()` returns `Agent`, skills mix freely with regular and framework agents (`>>`, `agent_tool()`, strategy teams, deploy, serve, stream).

**Thin SDK, thick server.** All parsing/normalization lives server-side in a `SkillNormalizer` (alongside the framework normalizers); the SDK just reads the directory, packages contents, registers script + `read_skill_file` workers (which must run user-side), and sends `{"framework": "skill", "rawConfig": {...}}` to the server. This keeps every SDK's footprint ~260 LOC.

A skill directory:

```
skill-name/
├── SKILL.md           # Required: YAML frontmatter + markdown body
├── *-agent.md         # Optional: each becomes a sub-agent
├── scripts/           # Optional: each executable → a named worker tool
├── references/ examples/ assets/   # Optional: read on demand via read_skill_file
```

**Discovery (convention-based):** `SKILL.md` frontmatter → metadata, body → orchestrator instructions; `*-agent.md` → sub-agents (filename minus `-agent.md` = name); `scripts/*` → named worker tools; `references/examples/assets/*` and other root files → paths listed, served via `read_skill_file` (an `enum`-constrained worker so the LLM can only read files that exist). Cross-skill references are matched against the search path (sibling dirs → `./.agents/skills/` → `~/.agents/skills/` → explicit `searchPath`) and packaged recursively (with cycle detection).

**SDK surface:** `skill(path, model[, agentModels, params, searchPath])` and `loadSkills(dir, model)` for a tree. Sub-agents inherit the orchestrator's model unless overridden per-agent. Script contents and resource file contents are **not** sent to the server — scripts run as local workers; resources are read on demand. The server's `SkillNormalizer` builds the orchestrator `AgentConfig`, wraps sub-agents and cross-skill refs as `agent_tool` (→ SUB_WORKFLOW), and emits script/`read_skill_file` tools as `worker` (→ SIMPLE). Worker task names are prefixed with the skill name (`dg__read_skill_file`) to avoid collisions when composing skills. No changes to `AgentCompiler`/`ToolCompiler`/`MultiAgentCompiler` — the normalizer produces the structure they already handle.

Each script call and file read is a distinct named Conductor task with full I/O, timing, retry, and crash recovery (the execution DAG resumes from the last completed task). A registry CLI (`agentspan skill register/list/get/pull/delete`, plus `run/load/serve`) stores immutable skill packages server-side.

This section is the consolidated skills design (normalizer steps, execution traces, registry API, edge cases).

---

## 5. Per-Language Guides, Implementations & Testing

### Framework bridges

Adapt native framework objects into the `Agent` model and send them via the `framework` + `rawConfig` path so the server's matching normalizer handles them. The runtime's `run/start/stream/deploy/serve/plan/resume` accept the raw native object and coerce it (detect by fully-qualified type name so the core never hard-references an optional dependency). **There is no passthrough** — every framework agent is compiled to a full AgentConfig → Conductor workflow with individual tasks per tool/LLM-call/sub-agent (durable, observable). Framework packages are optional dev/peer dependencies.

Supported bridges: OpenAI Agents SDK, Google ADK (`BaseAgent`/`LlmAgent`), LangChain / LangGraph, Vercel AI SDK (TS). OpenAI and Google ADK expose model/tools/instructions as public properties (zero user changes); JS frameworks that hide them in closures (Vercel AI `generateText`, LangGraph `createReactAgent`, LangChain `AgentExecutor`) use **drop-in import wrappers** — one import change captures model/tools at creation time. Detection order must check native `Agent` first, then framework markers. Full extraction rules per framework: [framework-integration.md](framework-integration.md) (and `langchain-integration.md`).

### Per-language idiom guides

> **Shipped vs. guide-only.** Only **four SDKs ship today**: Python, TypeScript, Java, and C# (`sdk/python`, `sdk/typescript`, `sdk/java`, `sdk/csharp`). The **Go, Kotlin, and Ruby** docs are *translation guides only* — idiom references for a future port; there is no published Go/Kotlin/Ruby SDK, so their coordinates/namespaces in those guides are illustrative, not authoritative.

Each language doc covers project setup, type-system mapping, the decorator/annotation pattern, async model, worker + SSE implementation, error handling, the testing framework, and a kitchen-sink translation. Reference type/pattern mappings:

| Python | TS | Go | Java | Kotlin | C# | Ruby |
|--------|-----|-----|------|--------|-----|------|
| `dataclass` | interface/class | struct | record/POJO | data class | record | Struct/Data |
| `>>` | `.pipe()` | `Pipeline()` | `.then()` | `then` infix | `>>` overload | `>>` |
| `&`/`\|` | `.and()`/`.or()` | `And()`/`Or()` | `.and()`/`.or()` | `and`/`or` infix | `&`/`\|` | `&`/`\|` |
| `@tool` | `@Tool()`/`tool()` | `Tool()` option | `@Tool` | `tool {}` DSL | `[Tool]` | `tool` method |

Guides: [java](sdk-design/languages/java.md) · [typescript](sdk-design/languages/typescript.md) · [csharp](sdk-design/languages/csharp.md) · [go](sdk-design/languages/go.md) · [kotlin](sdk-design/languages/kotlin.md) · [ruby](sdk-design/languages/ruby.md).

### Concrete implementation references

All four shipped SDKs have detailed reference-implementation write-ups (source layout, serializer, worker manager, SSE client, language-specific gotchas): [python](sdk-design/languages/python-implementation.md) (the reference SDK), [typescript](sdk-design/languages/typescript-implementation.md), [java](sdk-design/languages/java-implementation.md), and [csharp](sdk-design/languages/csharp-implementation.md). The TypeScript audit surfaced the recurring risks every new SDK should check:

1. **Worker-registration parity is the #1 risk** — every `taskName` the serializer emits must have a registered worker. After writing the serializer, grep all `taskName` references and verify each has a matching registration (termination, custom guardrail, stop_when, callbacks, gate, router_fn were all initially missed).
2. **Normalize class instances** before serializing (call `toGuardrailDef()` etc.).
3. **Bridge callback worker args** to typed handler signatures (supply `agentName` from the closure).
4. **Termination needs `shouldTerminate()`**, not just `toJSON()`.
5. **Some Python "SDK-side" workers are server-side for other SDKs** (check_transfer, handoff_check, swarm transfer, manual selection) — verify by running the example without the worker; don't add conflicting ones.
6. **Register tool-level guardrails as well as agent-level.**

### Acceptance testing

The **kitchen sink** is the single acceptance test — one mega-workflow (9 stages: intake/router, parallel research, sequential writing, guardrails, HITL, multi-strategy translation/discussion, handoff publishing, analytics/media/RAG, all execution modes) exercising every feature plus all cross-cutting concerns (7 credential modes, CLI config, code execution, thinking, include_contents, planner, metadata, context condensation). A new SDK **passes** when it: produces identical `AgentConfig` JSON for the same tree; workers execute all tool/guardrail/callback tasks; SSE yields the same event sequence; HITL completes; the final `AgentResult` matches; all assertions pass; and the LLM judge scores ≥ threshold on the quality rubrics. Spec + rubrics: [sdk-design/kitchen-sink.md](sdk-design/kitchen-sink.md).

Each SDK ships a **testing framework** mirroring Python: `mock_run()` (no server), an `expect()` fluent API (`expect(result).completed().outputContains("article")`), `assert_*` helpers (`assertToolUsed`, `assertGuardrailPassed`), `record()`/`replay()`, strategy validators, and an LLM-judge eval runner. Per CLAUDE.md, **do not use an LLM for validation except when judging output quality/evals**; structural and behavioral assertions must be deterministic.

A **validation framework** (concurrent runner, TOML config, example groups, LLM judge, HTML report, resume/retry) runs every ported example against multiple models and — validation-only, never a runtime dependency — compares Agentspan-compiled vs. native-framework execution for semantic equivalence. Designs: see the [validation methodology overview](validation/README.md) and the per-SDK docs — [python](validation/python-validation.md), [typescript](validation/typescript-validation.md), [java](validation/java-validation.md), [csharp](validation/csharp-validation.md).

**Example parity:** every SDK ports **all** Python examples — ~97 native + framework examples (LangGraph 44, LangChain 25, OpenAI 10, ADK 35; Vercel AI 10 for TS) — using the same numbering, translated to idiomatic patterns. **Hard rule:** framework examples must import and use the **real** native SDK (never mocks); if a package can't be installed, omit the example entirely and file a tracking issue — a missing example is honest, a mock is misleading.

### Implementation order

Configuration → HTTP client → Agent + Tool types → serialization → worker system → runtime (run/start/deploy) → SSE streaming → credentials → guardrails → memory → termination + handoffs → code execution → extended types → callbacks → framework integration → testing framework → validation framework → kitchen sink → examples. Audit each new SDK with the 3-pass methodology: (1) feature coverage / missing worker registrations, (2) edge cases / signature + normalization gaps, (3) end-to-end trace of 2–3 examples through the full pipeline.

### Reference docs (wire/platform detail)

- `agent-schema.md` / `agent-schema.json` — formal wire contract
- `agent-structure.md` — Agent field → JSON-key mapping and serialization rules
- `agent-client-api.md` — control-plane client (compile/deploy/start/status/respond)
- `agent-runtime-api.md` — runtime, streaming, and HITL semantics
- [api-design.md](api-design.md), [agentspan-design.md](agentspan-design.md) — REST/SSE and platform
- [guardrails-design.md](guardrails-design.md), [tool-execution-and-credentials-design.md](tool-execution-and-credentials-design.md), [framework-integration.md](framework-integration.md)
