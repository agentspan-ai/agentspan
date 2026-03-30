# TypeScript SDK Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the complete `@agentspan/sdk` TypeScript SDK with 89-feature parity, superset tool compatibility (Zod + JSON Schema + Vercel AI SDK), and framework passthrough for 5 frameworks.

**Architecture:** TypeScript-first SDK compiled to ESM+CJS via tsup. Raw `fetch`-based Conductor task polling (no conductor-javascript dependency). Auto-detecting runtime accepts both native agents and framework agents. Zod schemas auto-converted to JSON Schema at serialization time.

**Tech Stack:** TypeScript 5.x, tsup, vitest, zod, zod-to-json-schema, dotenv, Node.js 18+

**Spec:** `docs/superpowers/specs/2026-03-23-typescript-sdk-design.md`
**Base spec:** `docs/sdk-design/2026-03-23-multi-language-sdk-design.md`

---

## File Structure

| File | Responsibility |
|------|---------------|
| `sdk/typescript/src/index.ts` | Public re-exports |
| `sdk/typescript/src/types.ts` | All interfaces, enums, type aliases |
| `sdk/typescript/src/errors.ts` | AgentspanError hierarchy (9 types) |
| `sdk/typescript/src/config.ts` | AgentConfig env var loading, URL normalization |
| `sdk/typescript/src/agent.ts` | Agent class, Strategy, PromptTemplate, .pipe() |
| `sdk/typescript/src/tool.ts` | tool(), httpTool, mcpTool, apiTool, agentTool, media/RAG tools, @Tool decorator, superset detection |
| `sdk/typescript/src/serializer.ts` | Agent → AgentConfig JSON (recursive, all tool types, Zod conversion) |
| `sdk/typescript/src/worker.ts` | WorkerManager — raw fetch polling, type coercion, circuit breaker |
| `sdk/typescript/src/runtime.ts` | AgentRuntime — run/start/stream/deploy/plan/serve/shutdown + singleton |
| `sdk/typescript/src/stream.ts` | AgentStream — SSE client, AsyncIterable, HITL, reconnection, polling fallback |
| `sdk/typescript/src/result.ts` | makeAgentResult factory, AgentHandle, output normalization |
| `sdk/typescript/src/credentials.ts` | getCredential, resolveCredentials, CredentialFile, execution token extraction |
| `sdk/typescript/src/guardrail.ts` | guardrail(), RegexGuardrail, LLMGuardrail, @Guardrail decorator |
| `sdk/typescript/src/memory.ts` | ConversationMemory, SemanticMemory, InMemoryStore |
| `sdk/typescript/src/termination.ts` | TextMention, StopMessage, MaxMessage, TokenUsage + .and()/.or() |
| `sdk/typescript/src/handoff.ts` | OnToolResult, OnTextMention, OnCondition |
| `sdk/typescript/src/callback.ts` | CallbackHandler base class (6 positions) |
| `sdk/typescript/src/code-execution.ts` | CodeExecutor abstract, Local/Docker/Jupyter/Serverless, asTool() |
| `sdk/typescript/src/ext.ts` | UserProxyAgent, GPTAssistantAgent |
| `sdk/typescript/src/discovery.ts` | discoverAgents(path) |
| `sdk/typescript/src/tracing.ts` | OpenTelemetry integration |
| `sdk/typescript/src/frameworks/detect.ts` | detectFramework() duck-typing |
| `sdk/typescript/src/frameworks/event-push.ts` | pushEvent() non-blocking HTTP POST |
| `sdk/typescript/src/frameworks/vercel-ai.ts` | makeVercelAIWorker() |
| `sdk/typescript/src/frameworks/langgraph.ts` | makeLangGraphWorker() |
| `sdk/typescript/src/frameworks/langchain.ts` | makeLangChainWorker() |
| `sdk/typescript/src/frameworks/openai-agents.ts` | makeOpenAIAgentsWorker() |
| `sdk/typescript/src/frameworks/google-adk.ts` | makeGoogleADKWorker() |
| `sdk/typescript/src/testing/index.ts` | Re-exports: mockRun, expectResult, record, replay |
| `sdk/typescript/src/testing/mock.ts` | mockRun() serverless execution |
| `sdk/typescript/src/testing/expect.ts` | expectResult() fluent chain |
| `sdk/typescript/src/testing/assertions.ts` | assertToolUsed, assertGuardrailPassed, etc. |
| `sdk/typescript/src/testing/eval.ts` | CorrectnessEval LLM judge |
| `sdk/typescript/src/testing/strategy.ts` | validateStrategy() |
| `sdk/typescript/src/testing/recording.ts` | record()/replay() fixture capture |
| `sdk/typescript/src/validation/runner.ts` | Concurrent executor CLI entry |
| `sdk/typescript/src/validation/config.ts` | TOML parsing |
| `sdk/typescript/src/validation/judge.ts` | LLM judge integration |
| `sdk/typescript/src/validation/report.ts` | HTML report generation |

---

## Chunk 1: Project Scaffold + Foundation

### Task 1: Project scaffold

**Files:**
- Create: `sdk/typescript/package.json`
- Create: `sdk/typescript/tsconfig.json`
- Create: `sdk/typescript/tsup.config.ts`
- Create: `sdk/typescript/vitest.config.ts`
- Create: `sdk/typescript/.env.example`

- [ ] **Step 1: Clean out the old PoC SDK**

Remove all existing files in `sdk/typescript/src/`, `sdk/typescript/decorators/`, `sdk/typescript/types/`, `sdk/typescript/examples/` — but keep `sdk/typescript/` directory.

- [ ] **Step 2: Create package.json**

Per spec §2.2. Name: `@agentspan/sdk`, version `1.0.0`, type `module`. Dependencies: `zod-to-json-schema`, `dotenv`. Peer deps: `zod` (required), `ai`, `@langchain/core`, `@langchain/langgraph`, `@openai/agents`, `@google/adk` (all optional). Dev deps: `typescript`, `tsup`, `vitest`, `@types/node`, `zod`. Scripts: build, test, test:watch, lint, validate. Engines: `node >=18.0.0`.

Subpath exports: `.` (core), `./testing`, `./validation`.

- [ ] **Step 3: Create tsconfig.json**

Per spec §2.4. Target ESNext, module ESNext, bundler resolution, strict, experimentalDecorators, emitDecoratorMetadata, declaration, sourceMap.

- [ ] **Step 4: Create tsup.config.ts**

Per spec §2.5. Entry: `src/index.ts`, `src/testing/index.ts`, `src/validation/runner.ts`. Format: esm + cjs. DTS, splitting, sourcemap, clean, target node18.

- [ ] **Step 5: Create vitest.config.ts**

Globals true, testTimeout 60000, include `tests/**/*.test.ts`, setupFiles.

- [ ] **Step 6: Create .env.example**

All AGENTSPAN_ env vars from spec §20.1.

- [ ] **Step 7: Install dependencies and verify build**

```bash
cd sdk/typescript && npm install && npx tsc --noEmit
```

- [ ] **Step 8: Commit**

```bash
git add sdk/typescript/ && git commit -m "feat(ts-sdk): scaffold project with package.json, tsconfig, tsup, vitest"
```

### Task 2: Types + Errors + Config

**Files:**
- Create: `sdk/typescript/src/types.ts`
- Create: `sdk/typescript/src/errors.ts`
- Create: `sdk/typescript/src/config.ts`
- Create: `sdk/typescript/src/index.ts` (stub)
- Test: `sdk/typescript/tests/unit/types.test.ts`
- Test: `sdk/typescript/tests/unit/config.test.ts`

- [ ] **Step 1: Write types.ts**

All types from spec §3: Strategy, EventType, Status, FinishReason, OnFail, Position, ToolType, FrameworkId, TokenUsage, ToolContext, GuardrailResult, AgentEvent, AgentResult, AgentStatus, DeploymentInfo, PromptTemplate, CredentialFile, CodeExecutionConfig, CliConfig, ToolDef, GuardrailDef, HandoffCondition (abstract), GateCondition (abstract), RunOptions.

- [ ] **Step 2: Write errors.ts**

Per spec §16.1: AgentspanError, AgentAPIError, AgentNotFoundError, ConfigurationError, CredentialNotFoundError, CredentialAuthError, CredentialRateLimitError, CredentialServiceError, SSETimeoutError, GuardrailFailedError. All extend Error with `Object.setPrototypeOf(this, new.target.prototype)` for proper instanceof.

- [ ] **Step 3: Write config.ts**

Per spec §20: AgentConfig class with env var loading, URL normalization (append `/api` if missing), `fromEnv()` static factory. All 14 env vars.

- [ ] **Step 4: Write failing tests for config**

Test URL normalization (with/without /api suffix), env var precedence (constructor > env > defaults), fromEnv() factory.

- [ ] **Step 5: Run tests, verify they fail, then verify they pass**

```bash
cd sdk/typescript && npx vitest run tests/unit/config.test.ts
```

- [ ] **Step 6: Create index.ts stub**

Re-export types, errors, config.

- [ ] **Step 7: Verify build**

```bash
npx tsc --noEmit
```

- [ ] **Step 8: Commit**

```bash
git commit -m "feat(ts-sdk): add types, errors, config with tests"
```

---

## Chunk 2: Core Data Model (Agent + Tool + Serializer)

### Task 3: Tool system (superset)

**Files:**
- Create: `sdk/typescript/src/tool.ts`
- Test: `sdk/typescript/tests/unit/tool.test.ts`

- [ ] **Step 1: Write tool.ts**

Implement:
- `tool(fn, options)` — attaches `_toolDef` via Symbol. Options accept Zod or JSON Schema for `inputSchema`.
- `getToolDef(toolObj)` — extract ToolDef from tool wrappers, Vercel AI SDK tools, or raw objects.
- `isZodSchema(obj)` — checks for `._def` property.
- `normalizeToolInput(input)` — auto-detect: agentspan tool, Vercel AI SDK tool, raw ToolDef.
- `httpTool(opts)`, `mcpTool(opts)`, `apiTool(opts)` — server-side tools.
- `agentTool(agent, opts)` — SUB_WORKFLOW tool.
- `humanTool(opts)` — HUMAN tool.
- `imageTool(opts)`, `audioTool(opts)`, `videoTool(opts)`, `pdfTool(opts)` — media tools.
- `searchTool(opts)`, `indexTool(opts)` — RAG tools.
- `@Tool` decorator + `toolsFrom(instance)`.
- Zod → JSON Schema conversion via `zod-to-json-schema` at definition time.

All option interfaces from spec §24.7.

- [ ] **Step 2: Write tests**

Test: tool() with Zod schema, tool() with JSON Schema, getToolDef() extraction, normalizeToolInput() with all 3 formats (agentspan, Vercel AI SDK shape, raw), httpTool/mcpTool/apiTool produce correct ToolDef shape, @Tool decorator + toolsFrom(), media tools, RAG tools.

- [ ] **Step 3: Run tests**

```bash
npx vitest run tests/unit/tool.test.ts
```

- [ ] **Step 4: Commit**

### Task 4: Agent class

**Files:**
- Create: `sdk/typescript/src/agent.ts`
- Test: `sdk/typescript/tests/unit/agent.test.ts`

- [ ] **Step 1: Write agent.ts**

Implement:
- `Agent` class constructor taking `AgentOptions` (spec §3.3). Store all fields as readonly.
- `.pipe(other)` method — creates sequential agent with flattening (spec §7.4, §24.1 fix #4).
- `PromptTemplate` class — `name`, `variables`, `version`.
- `@AgentDec` decorator + `agentsFrom(instance)`.
- `agent()` functional wrapper.
- `scatterGather()` helper (spec §7.6).

- [ ] **Step 2: Write tests**

Test: Agent construction with all options, .pipe() creates sequential, .pipe() flattening (a.pipe(b).pipe(c) → flat array), PromptTemplate, scatterGather.

- [ ] **Step 3: Run tests, commit**

### Task 5: Serializer

**Files:**
- Create: `sdk/typescript/src/serializer.ts`
- Test: `sdk/typescript/tests/unit/serializer.test.ts`

- [ ] **Step 1: Write serializer.ts**

Implement `AgentConfigSerializer`:
- `serialize(agent)` — full POST /agent/start payload. `sessionId` always present (empty string), `media` always present (empty array).
- `serializeAgent(agent)` — recursive AgentConfig. camelCase keys, omit nulls, strategy only when agents non-empty.
- `serializeTool(tool)` — ToolConfig with all toolTypes. agentTool recursively serializes sub-agent.
- `serializeGuardrail(guard)` — GuardrailConfig.
- `serializeTermination(cond)` — recursive AND/OR.
- `serializeHandoff(handoff)` — HandoffConfig.
- Zod → JSON Schema via `zodToJsonSchema()` at serialization of `outputType` and any remaining Zod schemas.

Key rules from spec §19.2 and base spec §3.

- [ ] **Step 2: Write tests**

Test: simple agent → JSON, multi-agent sequential/parallel/handoff, all tool types serialize correctly, guardrails serialize (regex/llm/custom/external), termination composition (AND/OR), Zod outputType → JSON Schema, PromptTemplate serialization, credentials in tool config, nested agent_tool serialization.

**Critical test:** Compare serialized output against Python SDK's expected JSON for equivalent agents (wire format parity).

- [ ] **Step 3: Run tests, commit**

---

## Chunk 3: Execution Engine (Worker + Runtime + Streaming + Result)

### Task 6: Worker Manager

**Files:**
- Create: `sdk/typescript/src/worker.ts`
- Test: `sdk/typescript/tests/unit/worker.test.ts`

- [ ] **Step 1: Write worker.ts**

Implement `WorkerManager`:
- Constructor: `serverUrl`, `headers`, `pollIntervalMs`.
- `addWorker(taskName, handler)` — queue worker for polling.
- `registerTaskDef(taskName, config?)` — POST /api/metadata/taskdefs with retry config (retryCount:2, LINEAR_BACKOFF, retryDelay:2s, timeout:120s).
- `startPolling()` / `stopPolling()` — setInterval-based polling per worker.
- `pollTask(taskType)` — GET /api/tasks/poll/{taskType}.
- `reportSuccess(taskId, executionId, result)` / `reportFailure(...)` — POST /api/tasks.
- Type coercion rules (spec §13.4, base spec §14.1): null check → optional unwrap → type match → string↔object JSON parse/stringify → string→number/bool → fallback. All silent.
- Circuit breaker (spec §13.5): 10 failures → disable, reset on success.
- ToolContext extraction from `__agentspan_ctx__`.
- State mutation capture (`_state_updates`) per spec §24.1 fix #1.
- Strip `_agent_state` and `method` keys from inputs.

- [ ] **Step 2: Write tests**

Test: type coercion (string→object, object→string, string→number, string→bool, null passthrough), circuit breaker (opens at 10, resets on success), ToolContext extraction, state mutation capture, key stripping.

- [ ] **Step 3: Run tests, commit**

### Task 7: Result + Handle

**Files:**
- Create: `sdk/typescript/src/result.ts`
- Test: `sdk/typescript/tests/unit/result.test.ts`

- [ ] **Step 1: Write result.ts**

Implement:
- `makeAgentResult(data)` — factory with computed `isSuccess`, `isFailed`, `isRejected`, `printResult()`.
- Output normalization (spec fix #2): string→`{result}`, null+COMPLETED→`{result:null}`, null+FAILED→`{error}`, object→as-is.
- `EventType`, `Status`, `FinishReason` constant objects.
- `TERMINAL_STATUSES` set.

- [ ] **Step 2: Write tests, run, commit**

### Task 8: SSE Streaming (AgentStream)

**Files:**
- Create: `sdk/typescript/src/stream.ts`
- Test: `sdk/typescript/tests/unit/stream.test.ts`

- [ ] **Step 1: Write stream.ts**

Implement `AgentStream`:
- Constructor: `url`, `headers`, `executionId`, `runtime` reference.
- `[Symbol.asyncIterator]()` — SSE parsing via fetch ReadableStream. Line buffering, event/id/data field parsing, heartbeat filtering, JSON parse.
- Reconnection: Last-Event-ID header, max 5 retries, exponential backoff.
- Polling fallback: if no real events for 15s, switch to GET /agent/{id}/status every 500ms.
- HITL methods: `respond()`, `approve()`, `reject()`, `send()` → POST /agent/{id}/respond.
- `getResult()` — drain stream, build AgentResult.
- `events` array — all captured events.
- Event key stripping: remove `_agent_state`, `method` from args.
- Forward server-only events (context_condensed, subagent_start, subagent_stop).

- [ ] **Step 2: Write tests**

Test: SSE parsing (mock ReadableStream), heartbeat filtering, event type mapping, reconnection with Last-Event-ID, polling fallback trigger (15s timeout), HITL method payloads, key stripping.

- [ ] **Step 3: Run tests, commit**

### Task 9: AgentRuntime

**Files:**
- Create: `sdk/typescript/src/runtime.ts`
- Test: `sdk/typescript/tests/unit/runtime.test.ts`

- [ ] **Step 1: Write runtime.ts**

Implement `AgentRuntime`:
- Constructor: options → AgentConfig, auth headers, serializer, worker manager.
- `run(agent, prompt, options?)` — detect framework → serialize → POST /start → register workers → poll/stream → return AgentResult. Token aggregation from sub-workflows.
- `start(agent, prompt, options?)` — same but returns AgentHandle immediately. Handle has: getStatus, wait, respond, approve, reject, send, pause, resume, cancel, stream.
- `stream(agent, prompt, options?)` — returns AgentStream.
- `deploy(agent)` — POST /deploy → DeploymentInfo.
- `plan(agent)` — POST /compile → workflow def.
- `serve()` — blocking worker poll loop (keeps process alive).
- `shutdown()` — stop workers.
- Framework detection: import `detectFramework` from frameworks/detect.ts. If framework detected, delegate to `_runFramework()`.
- `_runFramework()` — build passthrough worker, register with 600s timeout, POST /start with `framework` field.
- Singleton pattern: `configure()`, `run()`, `start()`, `stream()`, `deploy()`, `plan()`, `serve()`, `shutdown()` top-level functions.
- AbortSignal support on all methods.
- correlationId auto-generation (UUID).

- [ ] **Step 2: Write tests**

Test: constructor config resolution, serializer called with correct agent, HTTP calls made to correct endpoints, framework detection delegation, singleton configure/run, AbortSignal cancellation.

- [ ] **Step 3: Run tests, commit**

---

## Chunk 4: Credentials + Guardrails

### Task 10: Credentials

**Files:**
- Create: `sdk/typescript/src/credentials.ts`
- Test: `sdk/typescript/tests/unit/credentials.test.ts`

- [ ] **Step 1: Write credentials.ts**

Implement:
- `getCredential(name)` — resolve single credential via execution token from ToolContext.
- `resolveCredentials(inputData, names)` — bulk resolution, POST /api/credentials/resolve.
- `extractExecutionToken(task)` — two-level fallback (inputData → workflowInput) per spec §24.4.
- Credential injection in worker: isolated mode (process.env), in-process mode (getCredential), cleanup.
- Error mapping: 404→CredentialNotFoundError, 401→CredentialAuthError, 429→CredentialRateLimitError, 5xx→CredentialServiceError.

- [ ] **Step 2: Write tests, run, commit**

### Task 11: Guardrails

**Files:**
- Create: `sdk/typescript/src/guardrail.ts`
- Test: `sdk/typescript/tests/unit/guardrail.test.ts`

- [ ] **Step 1: Write guardrail.ts**

Implement:
- `guardrail(fn, options)` — wraps function, produces GuardrailDef with guardrailType='custom'.
- `guardrail.external(options)` — no function, guardrailType='external'.
- `RegexGuardrail` class — patterns, mode (block/allow), message. guardrailType='regex'.
- `LLMGuardrail` class — model, policy, maxTokens. guardrailType='llm'.
- `@Guardrail` decorator + functional wrapper.
- Serialization format per spec §5.4.

- [ ] **Step 2: Write tests, run, commit**

---

## Chunk 5: Agent Features

### Task 12: Memory

**Files:**
- Create: `sdk/typescript/src/memory.ts`
- Test: `sdk/typescript/tests/unit/memory.test.ts`

- [ ] **Step 1: Write memory.ts**

Implement:
- `ConversationMemory` — addUserMessage, addAssistantMessage, addSystemMessage, addToolCall, addToolResult, toChatMessages, clear. maxMessages windowing (preserve system messages). Wire format: `{ messages, maxMessages }`.
- `SemanticMemory` — add, search, delete, clear, listAll. Takes MemoryStore.
- `MemoryStore` interface.
- `InMemoryStore` — keyword-overlap similarity (no external deps). TF-IDF-like scoring.

- [ ] **Step 2: Write tests, run, commit**

### Task 13: Termination + Handoffs + Gate

**Files:**
- Create: `sdk/typescript/src/termination.ts`
- Create: `sdk/typescript/src/handoff.ts`
- Test: `sdk/typescript/tests/unit/termination.test.ts`
- Test: `sdk/typescript/tests/unit/handoff.test.ts`

- [ ] **Step 1: Write termination.ts**

Implement `TerminationCondition` abstract with `.and()`, `.or()` → `AndCondition`, `OrCondition`. Concrete: `TextMention`, `StopMessage`, `MaxMessage`, `TokenUsage`. Each has `toJSON()` returning wire format.

- [ ] **Step 2: Write handoff.ts**

Implement `OnToolResult`, `OnTextMention`, `OnCondition`. Each has `toJSON()`.

Gate: `TextGate` class, `gate()` function for custom gates (worker). Response format: `{ decision: 'continue' | 'stop' }`.

- [ ] **Step 3: Write tests**

Test: individual conditions toJSON, composition (and/or nesting), TextGate toJSON, handoff serialization.

- [ ] **Step 4: Run tests, commit**

### Task 14: Callbacks + Code Execution + Extended Types

**Files:**
- Create: `sdk/typescript/src/callback.ts`
- Create: `sdk/typescript/src/code-execution.ts`
- Create: `sdk/typescript/src/ext.ts`
- Create: `sdk/typescript/src/discovery.ts`
- Create: `sdk/typescript/src/tracing.ts`
- Test: `sdk/typescript/tests/unit/callback.test.ts`
- Test: `sdk/typescript/tests/unit/code-execution.test.ts`

- [ ] **Step 1: Write callback.ts**

`CallbackHandler` abstract class with 6 optional methods. Worker registration produces task names `{agentName}_{position}`.

- [ ] **Step 2: Write code-execution.ts**

`CodeExecutor` abstract with `execute(code, language)` and `asTool(name?)`. Concrete: `LocalCodeExecutor` (child_process), `DockerCodeExecutor`, `JupyterCodeExecutor`, `ServerlessCodeExecutor`. `ExecutionResult` interface. `CodeExecutionConfig` and `CliConfig` types (already in types.ts).

- [ ] **Step 3: Write ext.ts**

`UserProxyAgent` extends Agent (modes: ALWAYS/TERMINATE/NEVER). `GPTAssistantAgent` extends Agent (assistantId, thread support).

- [ ] **Step 4: Write discovery.ts**

`discoverAgents(path)` — scan directory for files exporting Agent instances via dynamic import.

- [ ] **Step 5: Write tracing.ts**

`isTracingEnabled()` — check for OTel env vars. Stub span creation (user configures OTel SDK).

- [ ] **Step 6: Write tests, run, commit**

---

## Chunk 6: Framework Integration

### Task 15: Framework detection + event push

**Files:**
- Create: `sdk/typescript/src/frameworks/detect.ts`
- Create: `sdk/typescript/src/frameworks/event-push.ts`
- Test: `sdk/typescript/tests/unit/frameworks/detect.test.ts`

- [ ] **Step 1: Write detect.ts**

`detectFramework(agent)` — duck-typing checks in priority order: native Agent (null) → vercel_ai → langgraph → langchain → openai → google_adk → null. Each check is a private function testing method/property signatures.

- [ ] **Step 2: Write event-push.ts**

`pushEvent(executionId, event, serverUrl, headers)` — fire-and-forget fetch POST to `/agent/{executionId}/events`. Errors logged at debug only, never thrown.

- [ ] **Step 3: Write tests**

Test detectFramework with mock objects mimicking each framework's shape. Test it returns null for native Agent and unknown objects.

- [ ] **Step 4: Run tests, commit**

### Task 16: Framework workers (all 5)

**Files:**
- Create: `sdk/typescript/src/frameworks/vercel-ai.ts`
- Create: `sdk/typescript/src/frameworks/langgraph.ts`
- Create: `sdk/typescript/src/frameworks/langchain.ts`
- Create: `sdk/typescript/src/frameworks/openai-agents.ts`
- Create: `sdk/typescript/src/frameworks/google-adk.ts`
- Test: `sdk/typescript/tests/unit/frameworks/vercel-ai.test.ts`
- Test: `sdk/typescript/tests/unit/frameworks/langgraph.test.ts`

- [ ] **Step 1: Write vercel-ai.ts**

`makeVercelAIWorker(agent, name, serverUrl, headers)` — returns async worker function. Calls `agent.generate({ prompt, onStepFinish })`. Maps step events to agentspan SSE events. Credential injection via process.env.

- [ ] **Step 2: Write langgraph.ts**

`makeLangGraphWorker(graph, name, serverUrl, headers)` — dual stream mode (updates + values). Auto-detect input format from graph schema. Map node updates to events. Extract output from final values.

- [ ] **Step 3: Write langchain.ts**

`makeLangChainWorker(executor, name, serverUrl, headers)` — callback handler injection. `AgentspanCallbackHandler` class mapping LangChain callbacks to events.

- [ ] **Step 4: Write openai-agents.ts**

`makeOpenAIAgentsWorker(agent, name, serverUrl, headers)` — calls agent.run(), maps events.

- [ ] **Step 5: Write google-adk.ts**

`makeGoogleADKWorker(agent, name, serverUrl, headers)` — calls agent.run(), maps events.

- [ ] **Step 6: Write tests**

Test each worker factory with mock framework objects. Verify event push calls, output extraction, error handling.

- [ ] **Step 7: Run tests, commit**

---

## Chunk 7: Testing Framework + Validation

### Task 17: Testing framework

**Files:**
- Create: `sdk/typescript/src/testing/index.ts`
- Create: `sdk/typescript/src/testing/mock.ts`
- Create: `sdk/typescript/src/testing/expect.ts`
- Create: `sdk/typescript/src/testing/assertions.ts`
- Create: `sdk/typescript/src/testing/eval.ts`
- Create: `sdk/typescript/src/testing/strategy.ts`
- Create: `sdk/typescript/src/testing/recording.ts`
- Test: `sdk/typescript/tests/unit/testing/mock.test.ts`
- Test: `sdk/typescript/tests/unit/testing/expect.test.ts`

- [ ] **Step 1: Write mock.ts**

`mockRun(agent, prompt, options?)` — simulates Conductor execution loop locally. Accepts `mockTools` (override tool functions) and `mockCredentials`. Dispatches tools in-process, builds AgentResult.

- [ ] **Step 2: Write expect.ts**

`expectResult(result)` — returns fluent chain: toBeCompleted, toBeFailed, toContainOutput, toHaveUsedTool, toHavePassedGuardrail, toHaveFinishReason, toHaveTokenUsageBelow. Each throws on failure.

- [ ] **Step 3: Write assertions.ts**

Individual functions: assertToolUsed, assertGuardrailPassed, assertAgentRan, assertHandoffTo, assertStatus, assertNoErrors.

- [ ] **Step 4: Write eval.ts**

`CorrectnessEval` class — LLM judge. `evaluate(result, { rubrics, passThreshold })` → EvalResult with scores, weightedAverage, passed, reasoning.

- [ ] **Step 5: Write strategy.ts**

`validateStrategy(agent, expected)` — verify agent.strategy matches expected.

- [ ] **Step 6: Write recording.ts**

`record(agent, prompt, { fixturePath })` — capture events + tool calls to JSON file.
`replay(fixturePath)` — load fixture, replay, return AgentResult.

- [ ] **Step 7: Write index.ts**

Re-export all testing utilities.

- [ ] **Step 8: Write tests, run, commit**

### Task 18: Validation framework

**Files:**
- Create: `sdk/typescript/src/validation/runner.ts`
- Create: `sdk/typescript/src/validation/config.ts`
- Create: `sdk/typescript/src/validation/judge.ts`
- Create: `sdk/typescript/src/validation/report.ts`

- [ ] **Step 1: Write config.ts**

TOML parsing for `runs.toml`. Types: RunConfig, JudgeConfig, ValidationConfig.

- [ ] **Step 2: Write runner.ts**

CLI entry point. Concurrent executor: parse TOML, filter by --run/--group, run examples against models in parallel, collect results, optionally invoke judge, optionally generate report.

- [ ] **Step 3: Write judge.ts**

LLM judge integration. Call LLM with rubric prompts, parse scores, compute weighted average.

- [ ] **Step 4: Write report.ts**

HTML report generation with score heatmap, pass/fail status, expandable details.

- [ ] **Step 5: Commit**

---

## Chunk 8: Public API + Examples + Integration Tests

### Task 19: Public API (index.ts)

**Files:**
- Modify: `sdk/typescript/src/index.ts`

- [ ] **Step 1: Write complete index.ts**

Re-export everything from all modules. Organized by category: core (Agent, tool, httpTool, etc.), runtime (AgentRuntime, configure, run, start, stream, deploy, plan, serve, shutdown), results (AgentResult, AgentHandle, AgentStream, AgentEvent, etc.), guardrails, memory, termination, handoffs, callbacks, code execution, credentials, extended types, frameworks, types.

- [ ] **Step 2: Verify build compiles**

```bash
cd sdk/typescript && npm run build
```

- [ ] **Step 3: Commit**

### Task 20: Examples

**Files:**
- Create: `sdk/typescript/examples/01-basic-agent.ts`
- Create: `sdk/typescript/examples/02-tools.ts`
- Create: `sdk/typescript/examples/03-multi-agent.ts`
- Create: `sdk/typescript/examples/04-guardrails.ts`
- Create: `sdk/typescript/examples/05-streaming.ts`
- Create: `sdk/typescript/examples/06-hitl.ts`
- Create: `sdk/typescript/examples/07-memory.ts`
- Create: `sdk/typescript/examples/08-credentials.ts`
- Create: `sdk/typescript/examples/09-structured-output.ts`
- Create: `sdk/typescript/examples/10-code-execution.ts`
- Create: `sdk/typescript/examples/vercel-ai/01-passthrough.ts`
- Create: `sdk/typescript/examples/vercel-ai/02-tools-compat.ts`
- Create: `sdk/typescript/examples/vercel-ai/03-streaming.ts`
- Create: `sdk/typescript/examples/langgraph/01-react-agent.ts`
- Create: `sdk/typescript/examples/langchain/01-agent-executor.ts`

- [ ] **Step 1: Write basic examples (01-10)**

Each example demonstrates a specific feature cluster. Should be runnable with `npx tsx examples/01-basic-agent.ts`.

- [ ] **Step 2: Write framework examples**

Vercel AI SDK passthrough, mixed tools, streaming. LangGraph/LangChain passthrough.

- [ ] **Step 3: Commit**

### Task 21: Kitchen sink

**Files:**
- Create: `sdk/typescript/examples/kitchen-sink.ts`
- Create: `sdk/typescript/tests/unit/kitchen-sink-structural.test.ts`

- [ ] **Step 1: Write kitchen-sink.ts**

Port all 9 stages from `sdk/python/examples/kitchen_sink.py` to TypeScript. Exercise all 89 features per `docs/sdk-design/kitchen-sink.md`.

- [ ] **Step 2: Write structural tests**

Assertions that don't require a server: agent tree structure, strategy types, guardrail configs, tool counts, termination composition, outputType schemas.

- [ ] **Step 3: Run structural tests, commit**

### Task 22: Integration tests

**Files:**
- Create: `sdk/typescript/tests/integration/run.test.ts`
- Create: `sdk/typescript/tests/integration/stream.test.ts`
- Create: `sdk/typescript/tests/integration/hitl.test.ts`
- Create: `sdk/typescript/tests/integration/frameworks.test.ts`

- [ ] **Step 1: Write integration tests**

Requires running agentspan server. Test: basic run() completes, stream() yields events in order, HITL approve/reject/send, framework passthrough (mock Vercel AI SDK agent).

- [ ] **Step 2: Run integration tests (if server available)**

```bash
AGENTSPAN_SERVER_URL=http://localhost:6767/api npx vitest run tests/integration/
```

- [ ] **Step 3: Commit**

### Task 23: Final build + verify

- [ ] **Step 1: Full build**

```bash
cd sdk/typescript && npm run build
```

Verify dist/ has ESM + CJS + .d.ts for all three entry points.

- [ ] **Step 2: Full test suite**

```bash
npm test
```

- [ ] **Step 3: Lint**

```bash
npm run lint
```

- [ ] **Step 4: Fix any issues, re-test**

- [ ] **Step 5: Final commit**

```bash
git commit -m "feat(ts-sdk): complete TypeScript SDK v1.0 with 89-feature parity"
```
