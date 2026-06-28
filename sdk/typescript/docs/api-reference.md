# API Reference

The public surface of `@conductoross/conductor-agent-sdk`. One section per type. Everything here is exported from the package root unless noted.

## AgentRuntime

Core execution runtime. Manages agent lifecycle and local tool workers.

```ts
new AgentRuntime(options?: AgentConfigOptions)
```

| Member | Signature | Notes |
|---|---|---|
| `config` | `AgentConfig` | Resolved config (readonly). |
| `client` | `AgentClient` | Control-plane client (`/agent/*`). |
| `workflows` | `WorkflowClient` | Read-only workflow executions. |
| `run` | `(agent, prompt, options?) => Promise<AgentResult>` | Compile + start + stream + return result. Registers local workers. |
| `start` | `(agent, prompt, options?) => Promise<AgentHandle>` | Async interaction handle. |
| `stream` | `(agent, prompt, options?) => Promise<AgentStream>` | Event stream. |
| `deploy` | `(agent, { schedules? }?) => Promise<DeploymentInfo>` | Register workflow def + reconcile schedules. |
| `plan` | `(agent) => Promise<object>` | Compile to workflow def without executing. |
| `serve` | `(...agents) => Promise<void>` | Register workers, poll forever (blocks). |
| `getStatus` | `(executionId, signal?) => Promise<AgentStatus>` | Current execution status. |
| `schedulesClient` | `() => ScheduleClient` | Schedule lifecycle client. |
| `shutdown` | `() => Promise<void>` | Stop worker polling. |

`agent` is an `Agent` or a detected framework object. Module-level helpers `configure`, `run`, `start`, `stream`, `deploy`, `plan`, `serve`, `shutdown` operate on a shared singleton runtime.

## AgentClient

Control-plane client for the `/agent/*` HTTP surface. Mints the auth JWT and sends it as `X-Authorization`. **Does not run local tool workers.** Available as `runtime.client`.

```ts
new AgentClient(options?: AgentConfigOptions | AgentConfig)
```

| Member | Signature | Notes |
|---|---|---|
| `config` | `AgentConfig` | Resolved config. |
| `workflows` | `WorkflowClient` | Read-only workflow client. |
| `schedules` | `ScheduleClient` | Cron lifecycle client. |
| `run` | `(agent, prompt, opts?) => Promise<AgentResult>` | Compile + start + poll to result. |
| `start` | `(agent, prompt, opts?) => Promise<ClientHandle>` | Compile + start; returns a handle. |
| `deploy` | `(...agents) => Promise<DeploymentInfo[]>` | Compile + register agents. |
| `schedule` | `(agent, schedules) => Promise<DeploymentInfo>` | Deploy + reconcile schedules. |
| `startAgent` / `deployAgent` / `compile` | `(payload, signal?) => Promise<Record>` | Low-level POST endpoints. |
| `status` | `(executionId, signal?) => Promise<AgentStatus>` | GET status. |
| `respond` | `(executionId, body, signal?) => Promise<void>` | Complete a pending human task. |
| `getExecution` | `(executionId, signal?) => Promise<Record \| null>` | Full execution data. |
| `stream` | `(executionId, signal?) => Promise<AgentStream>` | SSE stream for an execution. |
| `authHeaders` | `() => Promise<Record<string,string>>` | Current auth header map. |

`decodeJwtExp(token: string): number` is also exported (epoch-seconds expiry, `0` if undecodable).

### ClientHandle

Returned by `AgentClient.start`. `{ executionId, getStatus(), wait(pollIntervalMs?), respond(output), approve(output?), reject(reason?), send(message), stream() }`.

## WorkflowClient

Read-only client for Conductor workflow executions. Available as `runtime.workflows`.

| Method | Signature | Notes |
|---|---|---|
| `getWorkflow` | `(executionId, includeTasks = true) => Promise<WorkflowExecution>` | Full execution (with tasks). |
| `getStatus` | `(executionId) => Promise<string>` | `'RUNNING'` / `'COMPLETED'` / ... or `''`. |
| `extractTokenUsage` | `(executionId) => Promise<WorkflowTokenUsage \| null>` | Aggregated across sub-workflows. |

`WorkflowTokenUsage` = `{ promptTokens, completionTokens, totalTokens }`.

## AgentConfig / AgentConfigOptions

```ts
interface AgentConfigOptions {
  serverUrl?: string;            // AGENTSPAN_SERVER_URL (default http://localhost:6767/api)
  apiKey?: string;               // AGENTSPAN_API_KEY (pre-minted token)
  authKey?: string;              // AGENTSPAN_AUTH_KEY
  authSecret?: string;           // AGENTSPAN_AUTH_SECRET
  workerPollIntervalMs?: number; // AGENTSPAN_WORKER_POLL_INTERVAL (100)
  workerThreads?: number;        // AGENTSPAN_WORKER_THREADS (1)
  autoStartWorkers?: boolean;    // (true)
  autoStartServer?: boolean;     // (true)
  daemonWorkers?: boolean;       // (true)
  streamingEnabled?: boolean;    // (true)
  credentialStrictMode?: boolean;// (false)
  logLevel?: 'DEBUG' | 'INFO' | 'WARN' | 'ERROR'; // (INFO)
  llmRetryCount?: number;        // (3)
}
```

`normalizeServerUrl(url)` and `AgentConfig.fromEnv()` are exported helpers.

## Agent / agent()

```ts
new Agent(options: AgentOptions)
```

Key `AgentOptions` fields:

| Field | Type | Notes |
|---|---|---|
| `name` | `string` | Required. `/^[a-zA-Z][a-zA-Z0-9_-]*$/`. |
| `model` | `string \| ClaudeCode` | e.g. `'anthropic/claude-sonnet-4-6'`. |
| `baseUrl` | `string` | Override LLM provider base URL. |
| `instructions` | `string \| PromptTemplate \| (() => string)` | Static / template / dynamic. |
| `tools` | `unknown[]` | `tool()` wrappers, built-in tool defs, framework tools. |
| `agents` | `Agent[]` | Sub-agents (multi-agent). |
| `strategy` | `Strategy` | `'sequential' \| 'parallel' \| 'handoff' \| 'router' \| 'round_robin' \| 'random' \| 'swarm' \| 'manual' \| 'plan_execute'`. |
| `router` | `Agent \| (() => string)` | Required for `strategy: 'router'`. |
| `outputType` | Zod schema or JSON Schema | Structured output. |
| `guardrails` | `unknown[]` | Guardrail defs / instances. |
| `handoffs` | `HandoffCondition[]` | `OnTextMention` / `OnToolResult` / `OnCondition`. |
| `allowedTransitions` | `Record<string, string[]>` | Constrain agent transitions. |
| `termination` | `TerminationCondition` | Stop condition. |
| `gate` | `GateCondition` | `TextGate` / `gate()`. |
| `callbacks` | `CallbackHandler[]` | Lifecycle hooks. |
| `memory` | `ConversationMemory` | Conversation history. |
| `maxTurns` | `number` | Default 25. |
| `maxTokens` / `temperature` / `timeoutSeconds` | `number` | LLM + execution tuning. |
| `credentials` | `string[]` | Secret names to resolve. |
| `stateful` | `boolean` | Per-execution worker isolation + shared state. |
| `planner` / `fallback` | `Agent` | PLAN_EXECUTE named slots. |
| `plannerContext` | `(string \| Context \| object)[]` | PLAN_EXECUTE reference docs. |
| `enablePlanning` | `boolean` | Plan-first preamble. |
| `prefillTools` | `PrefillToolCall[]` | Tools run before the first LLM turn. |
| `cliCommands` / `cliAllowedCommands` / `cliConfig` | — | Enable CLI command execution. |
| `codeExecutionConfig` | `CodeExecutionConfig` | Code execution. |
| `introduction` / `metadata` | — | Agent metadata. |

Methods: `agent.pipe(other)` builds a sequential pipeline (flattens chains). Getters: `isClaudeCode`, `claudeCodeConfig`.

Helpers:
- `agent(fn, options)` — functional form; `fn` is the dynamic-instructions callable.
- `scatterGather({ name, workers, model?, instructions?, retryCount?, retryDelaySeconds?, failFast?, timeoutSeconds? })` — coordinator that fans out to worker agents in parallel.
- `AgentDec(options)` + `agentsFrom(instance)` — define agents as decorated class methods.
- `PromptTemplate(name, variables?, version?)` — server-managed prompt reference.

## tool() and built-in tools

```ts
tool(fn: (args, ctx?: ToolContext) => Promise<T>, options: ToolOptions): ToolFunction
```

`ToolOptions`: `{ name?, description, inputSchema, outputSchema?, approvalRequired?, timeoutSeconds?, external?, credentials?, guardrails?, maxCalls?, retryCount?, retryDelaySeconds?, retryPolicy? }`. `inputSchema`/`outputSchema` accept a Zod schema or a JSON Schema object.

Built-in tool builders (all return a `ToolDef`):

| Builder | Required options | toolType |
|---|---|---|
| `httpTool` | `name, description, url` (`method?, headers?, inputSchema?, credentials?`) | `http` |
| `mcpTool` | `serverUrl` (`name?, headers?, toolNames?, maxTools?, credentials?`) | `mcp` |
| `apiTool` | `url` (`name?, headers?, toolNames?, maxTools?, credentials?`) | `api` |
| `agentTool` | `agent` (`name?, description?, retryCount?, retryDelaySeconds?, optional?`) | `agent_tool` |
| `humanTool` | `name, description` (`inputSchema?`) | `human` |
| `imageTool` | `name, description, llmProvider, model` (`style?, size?`) | `generate_image` |
| `audioTool` | `name, description, llmProvider, model` (`voice?, speed?, format?`) | `generate_audio` |
| `videoTool` | `name, description, llmProvider, model` (`duration?, resolution?, fps?, ...`) | `generate_video` |
| `pdfTool` | — (`name?, description?, pageSize?, theme?, fontSize?`) | `generate_pdf` |
| `waitForMessageTool` | `name, description` (`batchSize?` def 1, `blocking?` def true) | `pull_workflow_messages` |
| `searchTool` | `name, description, vectorDb, index, embeddingModelProvider, embeddingModel` (`namespace?, maxResults?, dimensions?`) | `rag_search` |
| `indexTool` | `name, description, vectorDb, index, embeddingModelProvider, embeddingModel` (`namespace?, chunkSize?, chunkOverlap?, dimensions?`) | `rag_index` |

Discovery / helpers: `Tool(options?)` decorator + `toolsFrom(instance)`; `getToolDef(obj)` / `normalizeToolInput(obj)` (extract a `ToolDef` from a `tool()` wrapper, Vercel AI tool, or raw def); `isZodSchema(obj)`.

### ToolContext

Passed as the second arg to a `tool()` function:

```ts
interface ToolContext {
  sessionId: string;
  executionId: string;
  agentName: string;
  metadata: Record<string, unknown>;
  dependencies: Record<string, unknown>;
  state: Record<string, unknown>;   // mutable; mutations propagate between tool calls
}
```

## Guardrails

- `guardrail(fn, { name, position?, onFail?, maxRetries? })` — custom guardrail from a function returning `{ passed, message?, fixedOutput? }`. `guardrail.external({ name, position?, onFail? })` for remote-worker guardrails.
- `new RegexGuardrail({ name, patterns, mode, position?, onFail?, message?, maxRetries? })` — `mode: 'block' | 'allow'`. `.toGuardrailDef()`.
- `new LLMGuardrail({ name, model, policy, position?, onFail?, maxRetries?, maxTokens? })` — server-side LLM judge. `.toGuardrailDef()`.
- `Guardrail(options?)` decorator + `guardrailsFrom(instance)`.

`position`: `'input' | 'output'` (default `'output'`). `onFail`: `'raise' | 'retry' | 'fix' | 'human'` (default `'raise'`). Attach via `agent.guardrails` or `tool(fn, { guardrails })`.

## Termination

All extend `TerminationCondition` and compose via `.and(other)` / `.or(other)` (or variadic `AndCondition(...)` / `OrCondition(...)`).

| Class | Constructor |
|---|---|
| `TextMention` | `(text, caseSensitive = false)` |
| `StopMessage` | `(stopMessage)` |
| `MaxMessage` | `(maxMessages)` |
| `TokenUsageCondition` | `({ maxTotalTokens?, maxPromptTokens?, maxCompletionTokens? })` |
| `AndCondition` / `OrCondition` | `(...conditions)` |

## Handoffs

- `new OnTextMention({ target, text })` — hand off when output mentions `text` (case-insensitive).
- `new OnToolResult({ target, toolName, resultContains? })` — hand off after a tool returns.
- `new OnCondition({ target, condition, agentName? })` — hand off when a predicate (runs as a worker) returns true.
- `new TextGate({ text, caseSensitive? })` — gate on text containment (`gate:` option).
- `gate(fn, { agentName? })` — custom gate from a function.

`HandoffContext` (passed to conditions): `{ result, toolName?, toolResult?, messages? }`.

## Callbacks

Subclass `CallbackHandler` and override hooks (each runs as a server worker):

```ts
abstract class CallbackHandler {
  onAgentStart?(agentName, prompt): Promise<void>;
  onAgentEnd?(agentName, result): Promise<void>;
  onModelStart?(agentName, messages): Promise<void>;
  onModelEnd?(agentName, response): Promise<void>;
  onToolStart?(agentName, toolName, args): Promise<void>;
  onToolEnd?(agentName, toolName, result): Promise<void>;
}
```

`CALLBACK_POSITIONS` maps hook names to wire positions; `getCallbackWorkerNames(agentName, handler)` lists registered worker names.

## Schedules / ScheduleClient

```ts
new Schedule({ name, cron, timezone?, input?, catchup?, paused?, startAt?, endAt?, description? })
```

`ScheduleClient` methods: `save(schedule, agentName)`, `get(wireName, agentName?)`, `listForAgent(agentName)`, `pause(wireName, reason?)`, `resume(wireName)`, `delete(wireName)`, `runNow(info)`, `previewNext(cron, { n?, startAt?, endAt? })`, `reconcile(agentName, desired)`.

The `schedules` namespace is a convenience layer over the singleton runtime: `schedules.list({ agent })`, `.get(name, { runtime? })`, `.pause(name, { reason?, runtime? })`, `.resume`, `.delete`, `.runNow`, `.previewNext(cron, { n? })`, `.save(schedule, agent)`. Lifecycle calls key on the **wire name** (the prefixed `name` in `ScheduleInfo`).

Errors: `ScheduleError`, `ScheduleNameConflict`, `ScheduleNotFound`, `InvalidCronExpression`. `ScheduleInfo` includes `name`, `shortName`, `agent`, `cron`, `timezone`, `paused`, `pausedReason`, `nextRun`, ...

## AgentResult

Returned by `run()` / `wait()`.

```ts
interface AgentResult {
  output: Record<string, unknown>;   // text answer -> { result: "..." }
  executionId: string;
  correlationId?: string;
  messages: unknown[];
  toolCalls: unknown[];
  status: 'COMPLETED' | 'FAILED' | 'TERMINATED' | 'TIMED_OUT';
  finishReason: 'stop' | 'length' | 'tool_calls' | 'error' | 'cancelled' | 'timeout' | 'guardrail' | 'rejected';
  error?: string;
  tokenUsage?: { promptTokens; completionTokens; totalTokens };
  metadata?: Record<string, unknown>;
  events: AgentEvent[];
  subResults?: Record<string, unknown>;
  readonly isSuccess: boolean;   // status === 'COMPLETED'
  readonly isFailed: boolean;    // FAILED | TIMED_OUT
  readonly isRejected: boolean;  // finishReason === 'rejected'
  printResult(): void;
}
```

## AgentHandle

Returned by `runtime.start()`.

```ts
interface AgentHandle {
  executionId: string;
  correlationId: string;
  getStatus(): Promise<AgentStatus>;
  wait(pollIntervalMs?): Promise<AgentResult>;
  respond(output): Promise<void>;
  approve(output?): Promise<void>;
  reject(reason?): Promise<void>;
  send(message): Promise<void>;
  pause(): Promise<void>;
  resume(): Promise<void>;
  cancel(): Promise<void>;
  stream(): AgentStream;
}
```

`approve()` sends `{ approved: true, ...output }`; `reject(reason)` sends `{ approved: false, reason }`; `send(message)` sends `{ message }`. For a custom human-task response (shaped by `pendingTool.response_schema`), use `respond(body)`.

## AgentStream / AgentEvent

`AgentStream` implements `AsyncIterable<AgentEvent>` — iterate with `for await`. Methods: `respond(output)`, `approve(output?)`, `reject(reason?)`, `send(message)`, and `getResult(): Promise<AgentResult>` (drains the stream, polls for the terminal status, returns the result). Fields: `executionId`, `events` (accumulates).

```ts
interface AgentEvent {
  type: 'thinking' | 'tool_call' | 'tool_result' | 'guardrail_pass' | 'guardrail_fail'
      | 'waiting' | 'handoff' | 'message' | 'error' | 'done' | string;
  content?: string;
  toolName?: string;
  args?: Record<string, unknown>;
  result?: unknown;
  target?: string;          // handoff target
  output?: unknown;         // on 'done'
  pendingTool?: PendingTool;// on 'waiting'
  guardrailName?: string;
}
```

`AgentStatus`: `{ executionId, isComplete, isRunning, isWaiting, output?, status, reason?, currentTask?, messages, pendingTool? }`. `PendingTool`: `{ taskRefName, toolCalls?: { name, args }[], response_schema?, ... }`. `EventTypes`, `Statuses`, `FinishReasons`, `TERMINAL_STATUSES` enums are exported.

## Errors

`AgentspanError` (base), `AgentAPIError`, `AgentNotFoundError`, `ConfigurationError`, `CredentialNotFoundError`, `CredentialAuthError`, `CredentialRateLimitError`, `CredentialServiceError`, `SSETimeoutError`, `TerminalToolError`, `GuardrailFailedError`.

## Other exports

- **Memory:** `ConversationMemory`, `SemanticMemory`, `InMemoryStore`.
- **Plans:** `Plan`, `Step`, `Op`, `Generate`, `Validation`, `Action`, `Ref`, `Context`, `coercePlan`.
- **Skills:** `skill(path, options?)`, `loadSkills(dir, options?)`, `SkillLoadError`.
- **Credentials:** `getCredential`, `resolveCredentials`, `runWithCredentialContext`, `setCredentialContext`, `clearCredentialContext`, `extractExecutionToken`.
- **Code execution:** `LocalCodeExecutor`, `DockerCodeExecutor`, `JupyterCodeExecutor`, `ServerlessCodeExecutor`, `CodeExecutor`, `CommandValidator`.
- **Claude Code:** `ClaudeCode(modelName?, permissionMode?)`, `PermissionMode`, `resolveClaudeCodeModel`.
- **Extended agents:** `GPTAssistantAgent({ name, assistantId, model?, instructions? })`.
- **Framework integration:** `detectFramework`, `serializeFrameworkAgent`, `serializeLangGraph`, `serializeLangChain`.
- **Subpath exports:** `@conductoross/conductor-agent-sdk/vercel-ai`, `@conductoross/conductor-agent-sdk/langgraph`, `@conductoross/conductor-agent-sdk/langchain`, `@conductoross/conductor-agent-sdk/testing`.
