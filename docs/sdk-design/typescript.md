# TypeScript SDK Translation Guide

**Date:** 2026-03-23
**Base spec:** `docs/sdk-design/2026-03-23-multi-language-sdk-design.md`
**Reference implementation:** `sdk/python/examples/kitchen_sink.py`

---

## 1. Project Setup

### Package Manager and Toolchain

Use **pnpm** as the primary package manager (npm is also supported). The SDK targets **TypeScript 5.x** with experimental decorator support enabled, since the `@Tool()`, `@Agent()`, and `@Guardrail()` patterns rely on TC39 Stage 3 decorators.

```bash
mkdir agentspan-ts && cd agentspan-ts
pnpm init
pnpm add typescript@^5.4 --save-dev
pnpm add tsx tsup --save-dev          # Build + dev execution
pnpm add vitest --save-dev            # Test runner
```

### Directory Layout

```
agentspan-ts/
  src/
    index.ts               # Public re-exports
    agent.ts               # Agent, Strategy, PromptTemplate
    tool.ts                # @Tool decorator, tool(), http_tool, mcp_tool, etc.
    guardrail.ts           # @Guardrail decorator, RegexGuardrail, LLMGuardrail
    result.ts              # AgentResult, AgentHandle, AgentStatus, AgentEvent
    stream.ts              # AgentStream, SSE client
    runtime.ts             # AgentRuntime, configure(), run(), start(), etc.
    worker.ts              # Conductor task polling, worker manager
    memory.ts              # ConversationMemory, SemanticMemory
    termination.ts         # TerminationCondition, composable conditions
    handoff.ts             # OnToolResult, OnTextMention, OnCondition
    credentials.ts         # getCredential, CredentialFile, resolve
    code_execution.ts      # CodeExecutor, LocalCodeExecutor, etc.
    callback.ts            # CallbackHandler base class
    errors.ts              # AgentspanError hierarchy
    types.ts               # Shared interfaces and enums
    serialization.ts       # AgentConfig JSON serialization
    testing/
      index.ts             # mockRun, expect, record/replay
      runner.ts            # Validation runner (TOML config)
  tests/
    agent.test.ts
    tool.test.ts
    guardrail.test.ts
    stream.test.ts
    kitchen_sink.test.ts
  examples/
    kitchen_sink.ts
  package.json
  tsconfig.json
  vitest.config.ts
```

### tsconfig.json

Decorators must be enabled. Target ESNext for top-level await and async iteration support.

```json
{
  "compilerOptions": {
    "target": "ESNext",
    "module": "ESNext",
    "moduleResolution": "bundler",
    "lib": ["ESNext"],
    "outDir": "dist",
    "rootDir": "src",
    "strict": true,
    "esModuleInterop": true,
    "experimentalDecorators": true,
    "emitDecoratorMetadata": true,
    "declaration": true,
    "declarationMap": true,
    "sourceMap": true,
    "skipLibCheck": true
  },
  "include": ["src/**/*.ts"],
  "exclude": ["node_modules", "dist", "tests"]
}
```

### Dependencies

| Dependency | Purpose |
|-----------|---------|
| `zod` | Schema validation (replaces Pydantic) |
| `eventsource` | SSE client for Node.js (browser uses native `EventSource`) |
| `@types/eventsource` | Type definitions |
| `toml` | TOML config parsing for validation runner |
| `abort-controller` | Polyfill for older Node.js (16+) |

```bash
pnpm add zod eventsource toml
pnpm add @types/eventsource --save-dev
```

The SDK uses the **native `fetch` API** (available in Node 18+) for all HTTP calls rather than axios, keeping the dependency surface minimal. For Node 16 support, users can polyfill `fetch` with `undici`.

### Build and Scripts

```json
{
  "scripts": {
    "build": "tsup src/index.ts --format esm,cjs --dts",
    "test": "vitest run",
    "test:watch": "vitest",
    "lint": "tsc --noEmit",
    "validate": "tsx src/testing/runner.ts --config runs.toml"
  }
}
```

---

## 2. Type System Mapping

### Primitive and Structural Mapping

| Python | TypeScript | Notes |
|--------|-----------|-------|
| `dataclass` | `interface` (data) / `class` (behavior) | Prefer `interface` for pure data; `class` when methods needed |
| `enum(str, Enum)` | `enum` or string union | String unions (`"handoff" \| "sequential"`) are more ergonomic |
| `Optional[T]` | `T \| null` | Avoid `undefined`; use explicit `null` for "no value" |
| `list[T]` | `T[]` | Literal array syntax preferred over `Array<T>` |
| `dict[K, V]` | `Record<K, V>` | For known shapes, use explicit interface instead |
| `Callable[..., T]` | `(...args: any[]) => T` | Typed function signatures preferred |
| `Pydantic BaseModel` | `zod.object({...})` | Zod for runtime validation + type inference |
| `Union[A, B]` | `A \| B` | For tagged unions, use discriminated unions |

### Core Type Definitions

```typescript
// ── Enums as string unions ────────────────────────────────────────

export type Strategy =
  | "handoff"
  | "sequential"
  | "parallel"
  | "router"
  | "round_robin"
  | "random"
  | "swarm"
  | "manual";

export type EventType =
  | "thinking"
  | "tool_call"
  | "tool_result"
  | "guardrail_pass"
  | "guardrail_fail"
  | "waiting"
  | "handoff"
  | "message"
  | "error"
  | "done";

export type Status = "COMPLETED" | "FAILED" | "TERMINATED" | "TIMED_OUT";

export type FinishReason =
  | "stop"
  | "length"
  | "tool_calls"
  | "error"
  | "cancelled"
  | "timeout"
  | "guardrail"
  | "rejected";

export type OnFail = "retry" | "raise" | "fix" | "human";
export type Position = "input" | "output";


// ── Data interfaces ───────────────────────────────────────────────

export interface TokenUsage {
  promptTokens: number;
  completionTokens: number;
  totalTokens: number;
}

export interface ToolContext {
  sessionId: string;
  executionId: string;
  agentName: string;
  metadata: Record<string, unknown>;
  dependencies: Record<string, unknown>;
  state: Record<string, unknown>;
}

export interface GuardrailResult {
  passed: boolean;
  message?: string;
  fixedOutput?: string;
}

export interface AgentEvent {
  type: EventType | string;   // string allows server-only types to pass through
  content?: string;
  toolName?: string;
  args?: Record<string, unknown>;
  result?: unknown;
  target?: string;
  output?: unknown;
  executionId?: string;
  guardrailName?: string;
  timestamp?: number;
}

export interface AgentResult {
  output: Record<string, unknown>;
  executionId: string;
  correlationId?: string;
  messages: unknown[];
  toolCalls: unknown[];
  status: Status;
  finishReason: FinishReason;
  error?: string;
  tokenUsage?: TokenUsage;
  metadata?: Record<string, unknown>;
  events: AgentEvent[];
  subResults?: Record<string, unknown>;
  // Convenience getters
  readonly isSuccess: boolean;
  readonly isFailed: boolean;
  readonly isRejected: boolean;
}

export interface AgentStatus {
  executionId: string;
  isComplete: boolean;
  isRunning: boolean;
  isWaiting: boolean;
  output?: unknown;
  status: string;
  reason?: string;
  currentTask?: string;
  messages: unknown[];
  pendingTool?: { name: string; args: Record<string, unknown> };
}

export interface DeploymentInfo {
  registeredName: string;
  agentName: string;
}

export interface PromptTemplate {
  name: string;
  variables?: Record<string, string>;
  version?: number;
}

export interface CredentialFile {
  envVar: string;
  relativePath?: string;
  content?: string;
}
```

### Agent Interface

The `Agent` class carries both data and behavior (serialization, chaining). It mirrors every field from the Python reference.

```typescript
export interface AgentOptions {
  name: string;
  model?: string;
  instructions?: string | PromptTemplate | ((...args: any[]) => string);
  tools?: ToolDef[];
  agents?: Agent[];
  strategy?: Strategy;
  router?: Agent | ((...args: any[]) => string);
  outputType?: ZodSchema | object;    // zod schema or JSON Schema
  guardrails?: GuardrailDef[];
  memory?: ConversationMemory;
  maxTurns?: number;
  maxTokens?: number;
  temperature?: number;
  timeoutSeconds?: number;
  external?: boolean;
  stopWhen?: (messages: unknown[], ...args: any[]) => boolean;
  termination?: TerminationCondition;
  handoffs?: HandoffCondition[];
  allowedTransitions?: Record<string, string[]>;
  introduction?: string;
  metadata?: Record<string, unknown>;
  callbacks?: CallbackHandler[];
  planner?: boolean;
  includeContents?: "default" | "none";
  thinkingBudgetTokens?: number;
  requiredTools?: string[];
  gate?: GateCondition;
  codeExecutionConfig?: CodeExecutionConfig;
  cliConfig?: CliConfig;
  credentials?: (string | CredentialFile)[];
}
```

### Zod for Structured Output

Where Python uses Pydantic `BaseModel` for `output_type`, TypeScript uses Zod schemas. Zod provides both runtime validation and static type inference via `z.infer<>`.

```typescript
import { z } from "zod";

const ClassificationResult = z.object({
  category: z.enum(["tech", "business", "creative"]),
  priority: z.number().int().min(1).max(5),
  metadata: z.record(z.string(), z.unknown()),
});

type ClassificationResult = z.infer<typeof ClassificationResult>;

const intake = new Agent({
  name: "intake_router",
  model: "openai/gpt-4o",
  outputType: ClassificationResult,
  // ...
});
```

---

## 3. Decorator/Annotation Pattern

TypeScript supports TC39 Stage 3 decorators (TypeScript 5.x with `experimentalDecorators`). The SDK provides **both** a decorator pattern and a function-wrapper pattern so users can choose whichever fits their codebase.

### @Tool() Decorator (Class Method)

```typescript
import { Tool, ToolContext } from "agentspan";

class ResearchTools {
  @Tool({
    credentials: [{ envVar: "RESEARCH_API_KEY" }],
  })
  async researchDatabase(query: string, ctx?: ToolContext): Promise<Record<string, unknown>> {
    const session = ctx?.sessionId ?? "unknown";
    const execution = ctx?.executionId ?? "unknown";
    return {
      query,
      sessionId: session,
      executionId: execution,
      results: { source: "internal_db", count: 42 },
    };
  }

  @Tool({ isolated: false, credentials: ["ANALYTICS_KEY"] })
  async analyzeTrends(topic: string): Promise<Record<string, unknown>> {
    const key = await getCredential("ANALYTICS_KEY");
    return { topic, trendScore: 0.87, keyPresent: Boolean(key) };
  }

  @Tool({ external: true })
  async externalResearchAggregator(query: string, sources: number = 10): Promise<Record<string, unknown>> {
    // No implementation -- runs on a remote worker
    return {};
  }

  @Tool({ approvalRequired: true })
  async publishArticle(
    title: string,
    content: string,
    platform: string
  ): Promise<Record<string, unknown>> {
    return { status: "published", title, platform };
  }
}
```

The `@Tool()` decorator introspects the method name, JSDoc (or the description option), and parameter types to generate the JSON Schema for the Conductor task definition. When `ToolContext` appears as a parameter, the SDK automatically injects the execution context extracted from `__agentspan_ctx__`.

### tool() Function Wrapper

For standalone functions (outside classes), use the `tool()` wrapper. This is the more common pattern for functional codebases.

```typescript
import { tool, ToolContext, getCredential, CredentialFile } from "agentspan";

const researchDatabase = tool(
  async (query: string, ctx?: ToolContext) => {
    return {
      query,
      sessionId: ctx?.sessionId ?? "unknown",
      results: { source: "internal_db" },
    };
  },
  {
    name: "research_database",
    description: "Search internal research database.",
    credentials: [{ envVar: "RESEARCH_API_KEY" } satisfies CredentialFile],
  }
);

const analyzeTrends = tool(
  async (topic: string) => {
    const key = await getCredential("ANALYTICS_KEY");
    return { topic, trendScore: 0.87 };
  },
  { name: "analyze_trends", isolated: false, credentials: ["ANALYTICS_KEY"] }
);
```

### @Agent() Decorator

```typescript
import { AgentDecorator as AgentDec } from "agentspan";

class Classifiers {
  @AgentDec({ name: "tech_classifier", model: "openai/gpt-4o" })
  techClassifier(prompt: string): string {
    return ""; // Implementation handled by runtime
  }

  @AgentDec({ name: "business_classifier", model: "openai/gpt-4o" })
  businessClassifier(prompt: string): string {
    return "";
  }
}
```

Or with the functional `agent()` wrapper:

```typescript
import { agent } from "agentspan";

const techClassifier = agent(
  (prompt: string) => "",
  { name: "tech_classifier", model: "openai/gpt-4o" }
);
```

### @Guardrail() Decorator

```typescript
import { Guardrail as GuardrailDec, GuardrailResult } from "agentspan";

class SafetyGuardrails {
  @GuardrailDec()
  factValidator(content: string): GuardrailResult {
    const redFlags = ["the best", "the worst", "always", "never", "guaranteed"];
    const found = redFlags.filter((rf) => content.toLowerCase().includes(rf));
    if (found.length > 0) {
      return { passed: false, message: `Unverifiable claims: ${found.join(", ")}` };
    }
    return { passed: true };
  }

  @GuardrailDec()
  sqlInjectionGuard(content: string): GuardrailResult {
    if (/(\bDROP\b|\bDELETE\b|--|;)/i.test(content)) {
      return { passed: false, message: "SQL injection detected." };
    }
    return { passed: true };
  }
}
```

Or with the functional `guardrail()` wrapper:

```typescript
import { guardrail, GuardrailResult } from "agentspan";

const factValidator = guardrail(
  (content: string): GuardrailResult => {
    const redFlags = ["the best", "always", "never"];
    const found = redFlags.filter((rf) => content.toLowerCase().includes(rf));
    return found.length > 0
      ? { passed: false, message: `Unverifiable claims: ${found}` }
      : { passed: true };
  },
  { name: "fact_validator" }
);
```

---

## 4. Async Model

TypeScript is inherently async via `Promise<T>` and `async/await`. Unlike Python, there is no need for separate sync and async variants of the execution API -- all methods are `async` and return `Promise<T>`. Users simply `await` them.

### Core Execution Methods

```typescript
import {
  Agent,
  AgentRuntime,
  AgentResult,
  AgentHandle,
  AgentStream,
  DeploymentInfo,
} from "agentspan";

const runtime = new AgentRuntime();

// run() -- blocks (awaits) until the agent completes
const result: AgentResult = await runtime.run(myAgent, "Hello!");

// start() -- fire-and-forget, returns a handle for polling
const handle: AgentHandle = await runtime.start(myAgent, "Hello!");
const status = await handle.getStatus();

// stream() -- returns an async iterable of events
const stream: AgentStream = await runtime.stream(myAgent, "Hello!");
```

### Streaming with AsyncIterable

`AgentStream` implements `AsyncIterable<AgentEvent>`, enabling `for await...of` loops. This is the TypeScript equivalent of Python's `async for`.

```typescript
const stream = await runtime.stream(myAgent, prompt);

for await (const event of stream) {
  switch (event.type) {
    case "thinking":
      console.log(`[thinking] ${event.content?.slice(0, 80)}...`);
      break;
    case "tool_call":
      console.log(`[tool_call] ${event.toolName}(${JSON.stringify(event.args)})`);
      break;
    case "tool_result":
      console.log(`[tool_result] ${event.toolName} -> ${String(event.result).slice(0, 80)}`);
      break;
    case "waiting":
      // HITL: approve, reject, or send feedback
      await stream.approve();
      break;
    case "done":
      console.log("[done] Pipeline complete");
      break;
  }
}

const result = await stream.getResult();
console.log(`Status: ${result.status}`);
```

### Worker Poll Loop

Conductor task polling runs via `setInterval` combined with async task execution. Each registered worker function polls in its own interval timer and executes tasks concurrently with `Promise.all` when multiple tasks are available.

```typescript
class WorkerManager {
  private pollers: NodeJS.Timeout[] = [];

  registerWorker(taskName: string, handler: (input: unknown) => Promise<unknown>): void {
    const poller = setInterval(async () => {
      try {
        const tasks = await this.pollTasks(taskName);
        await Promise.all(
          tasks.map(async (task) => {
            try {
              const result = await handler(task.inputData);
              await this.reportSuccess(task.taskId, result);
            } catch (err) {
              await this.reportFailure(task.taskId, err);
            }
          })
        );
      } catch {
        // Poll failure -- will retry on next interval
      }
    }, this.pollIntervalMs);
    this.pollers.push(poller);
  }

  shutdown(): void {
    for (const poller of this.pollers) {
      clearInterval(poller);
    }
    this.pollers = [];
  }
}
```

### Top-Level Convenience Functions

These mirror the Python top-level API. Because TypeScript is async-native, there is no `run_async` / `start_async` split -- all functions return promises.

```typescript
import { configure, run, start, stream, deploy, plan, serve, shutdown } from "agentspan";

// Pre-configure the singleton runtime
configure({ serverUrl: "http://localhost:6767/api", apiKey: "sk-..." });

// Synchronous-style (just await the promise)
const result = await run(myAgent, "Write an article");

// Fire-and-forget + polling
const handle = await start(myAgent, "Write an article");

// Streaming
const agentStream = await stream(myAgent, "Write an article");

// Deploy (compile + register, no execution)
const info = await deploy(myAgent);

// Plan (compile-only dry run, no prompt)
const executionPlan = await plan(myAgent);

// Start worker serve loop (blocking)
await serve();

// Shutdown
await shutdown();
```

---

## 5. Worker Implementation

Workers are the bridge between Conductor's task queue and the SDK's locally registered tool, guardrail, and callback functions. When the server dispatches a SIMPLE task, the SDK's worker picks it up, executes the function, and returns the result.

### Task Polling Loop

The worker manager polls `GET /api/tasks/poll/{taskType}` at a configurable interval (default 100ms). Each tool, guardrail, and callback gets its own registered worker.

```typescript
interface ConductorTask {
  taskId: string;
  taskType: string;
  inputData: Record<string, unknown>;
  workflowInstanceId: string;
  status: string;
}

interface TaskResult {
  taskId: string;
  workflowInstanceId: string;
  status: "COMPLETED" | "FAILED";
  outputData?: Record<string, unknown>;
  reasonForIncompletion?: string;
}

async function pollTask(serverUrl: string, taskType: string, headers: HeadersInit): Promise<ConductorTask | null> {
  const res = await fetch(`${serverUrl}/tasks/poll/${taskType}`, { headers });
  if (res.status === 204 || !res.ok) return null;
  return res.json();
}

async function reportTaskResult(serverUrl: string, result: TaskResult, headers: HeadersInit): Promise<void> {
  await fetch(`${serverUrl}/tasks`, {
    method: "POST",
    headers: { ...headers, "Content-Type": "application/json" },
    body: JSON.stringify(result),
  });
}
```

### Complete Worker for a @tool Function

This shows the full lifecycle: poll, deserialize, inject context, resolve credentials, execute, serialize result, report.

```typescript
import { getCredential, CredentialFile } from "./credentials";

interface ToolWorkerConfig {
  taskName: string;
  handler: (args: Record<string, unknown>, ctx?: ToolContext) => Promise<unknown>;
  credentials?: (string | CredentialFile)[];
  isolated?: boolean;
}

function createToolWorker(config: ToolWorkerConfig, runtime: AgentRuntime): void {
  runtime.workerManager.registerWorker(config.taskName, async (inputData: unknown) => {
    const input = inputData as Record<string, unknown>;

    // 1. Extract __agentspan_ctx__ for ToolContext injection
    const rawCtx = input["__agentspan_ctx__"] as Record<string, unknown> | undefined;
    const toolCtx: ToolContext | undefined = rawCtx
      ? {
          sessionId: rawCtx.sessionId as string,
          executionId: rawCtx.executionId as string,
          agentName: rawCtx.agentName as string,
          metadata: (rawCtx.metadata as Record<string, unknown>) ?? {},
          dependencies: (rawCtx.dependencies as Record<string, unknown>) ?? {},
          state: (rawCtx.state as Record<string, unknown>) ?? {},
        }
      : undefined;

    // 2. Resolve credentials if declared
    if (config.credentials && config.credentials.length > 0 && rawCtx?.executionToken) {
      const credNames = config.credentials.map((c) =>
        typeof c === "string" ? c : c.envVar
      );
      const resolved = await resolveCredentials(
        runtime.serverUrl,
        rawCtx.executionToken as string,
        credNames
      );

      if (config.isolated) {
        // In isolated mode, credentials are set as env vars for subprocess
        for (const [key, value] of Object.entries(resolved)) {
          process.env[key] = value;
        }
      }
      // In-process mode: credentials available via getCredential()
    }

    // 3. Remove internal keys, pass remaining as function args
    const args = { ...input };
    delete args["__agentspan_ctx__"];

    // 4. Execute the user function
    const result = await config.handler(args, toolCtx);

    // 5. Clean up isolated credential env vars
    if (config.isolated && config.credentials) {
      for (const c of config.credentials) {
        const name = typeof c === "string" ? c : c.envVar;
        delete process.env[name];
      }
    }

    // 6. Return serialized result
    return { result: typeof result === "object" ? result : { result } };
  });
}
```

### Credential Resolution

```typescript
async function resolveCredentials(
  serverUrl: string,
  executionToken: string,
  names: string[]
): Promise<Record<string, string>> {
  const res = await fetch(`${serverUrl}/credentials/resolve`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ executionToken, names }),
  });
  if (!res.ok) {
    throw new CredentialServiceError(`Failed to resolve credentials: ${res.status}`);
  }
  return res.json();
}
```

### Callback Worker Registration

Callbacks follow the same worker pattern but with 6 position-specific task names:

```typescript
function registerCallbackWorkers(
  agentName: string,
  handler: CallbackHandler,
  runtime: AgentRuntime
): void {
  const positions = [
    { position: "before_agent", method: handler.onAgentStart?.bind(handler) },
    { position: "after_agent", method: handler.onAgentEnd?.bind(handler) },
    { position: "before_model", method: handler.onModelStart?.bind(handler) },
    { position: "after_model", method: handler.onModelEnd?.bind(handler) },
    { position: "before_tool", method: handler.onToolStart?.bind(handler) },
    { position: "after_tool", method: handler.onToolEnd?.bind(handler) },
  ];

  for (const { position, method } of positions) {
    if (method) {
      const taskName = `${agentName}_${position}`;
      runtime.workerManager.registerWorker(taskName, async (input) => {
        await method(input as any);
        return { acknowledged: true };
      });
    }
  }
}
```

---

## 6. SSE Client

The SSE client must handle two environments: **browser** (native `EventSource`) and **Node.js** (manual `fetch` + `ReadableStream` parsing or the `eventsource` npm package). The SDK provides a unified `AgentStream` that abstracts both.

### Node.js SSE Implementation (fetch + ReadableStream)

This is the preferred approach for Node.js since it supports custom headers (`Authorization`, `Last-Event-ID`) which the native `EventSource` API does not.

```typescript
interface SSEClientOptions {
  url: string;
  headers: Record<string, string>;
  lastEventId?: string;
  signal?: AbortSignal;
  onEvent: (event: AgentEvent) => void;
  onError: (error: Error) => void;
  onReconnect?: () => void;
}

async function connectSSE(options: SSEClientOptions): Promise<void> {
  const headers: Record<string, string> = {
    Accept: "text/event-stream",
    "Cache-Control": "no-cache",
    ...options.headers,
  };

  if (options.lastEventId) {
    headers["Last-Event-ID"] = options.lastEventId;
  }

  const res = await fetch(options.url, {
    headers,
    signal: options.signal,
  });

  if (!res.ok) {
    throw new AgentAPIError(`SSE connection failed: ${res.status}`, res.status);
  }

  if (!res.body) {
    throw new AgentAPIError("Response body is null");
  }

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  // Parsing state for current SSE event
  let currentEvent = "";
  let currentId = "";
  let currentData = "";

  let lastRealEventTime = Date.now();

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;

    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split("\n");
    buffer = lines.pop() ?? ""; // Keep incomplete line in buffer

    for (const line of lines) {
      // Heartbeat comment -- filter out, but reset timeout tracker
      if (line.startsWith(":")) {
        // Don't update lastRealEventTime: heartbeats indicate SSE is alive
        // but if we see ONLY heartbeats for 15s, fall back to polling
        continue;
      }

      // Blank line = end of event
      if (line === "") {
        if (currentData) {
          lastRealEventTime = Date.now();
          try {
            const parsed = JSON.parse(currentData) as AgentEvent;
            parsed.type = (currentEvent || parsed.type) as EventType;
            options.onEvent(parsed);
          } catch {
            // Malformed JSON -- skip
          }
          currentEvent = "";
          currentId = "";
          currentData = "";
        }
        continue;
      }

      // Parse SSE fields
      if (line.startsWith("event:")) {
        currentEvent = line.slice(6).trim();
      } else if (line.startsWith("id:")) {
        currentId = line.slice(3).trim();
      } else if (line.startsWith("data:")) {
        currentData += line.slice(5).trim();
      }
    }

    // 15-second timeout detection: if no real events, fall back to polling
    if (Date.now() - lastRealEventTime > 15_000) {
      reader.cancel();
      throw new SSETimeoutError("No real events for 15s, falling back to polling");
    }
  }
}
```

### Browser EventSource Wrapper

For browser environments, use the native `EventSource` API but wrap it to produce the same `AgentStream` interface.

```typescript
function createBrowserSSEStream(
  url: string,
  headers: Record<string, string>
): AsyncIterable<AgentEvent> {
  return {
    [Symbol.asyncIterator]() {
      const eventSource = new EventSource(url);
      const eventQueue: AgentEvent[] = [];
      let resolve: ((value: IteratorResult<AgentEvent>) => void) | null = null;
      let done = false;

      const eventTypes: EventType[] = [
        "thinking", "tool_call", "tool_result", "guardrail_pass",
        "guardrail_fail", "waiting", "handoff", "message", "error", "done",
      ];

      for (const type of eventTypes) {
        eventSource.addEventListener(type, (e: MessageEvent) => {
          const parsed: AgentEvent = { ...JSON.parse(e.data), type };
          if (type === "done") done = true;

          if (resolve) {
            const r = resolve;
            resolve = null;
            r({ value: parsed, done: false });
          } else {
            eventQueue.push(parsed);
          }

          if (done) eventSource.close();
        });
      }

      eventSource.onerror = () => {
        done = true;
        eventSource.close();
        if (resolve) {
          resolve({ value: undefined as any, done: true });
        }
      };

      return {
        next(): Promise<IteratorResult<AgentEvent>> {
          if (eventQueue.length > 0) {
            return Promise.resolve({ value: eventQueue.shift()!, done: false });
          }
          if (done) {
            return Promise.resolve({ value: undefined as any, done: true });
          }
          return new Promise((r) => { resolve = r; });
        },
        return(): Promise<IteratorResult<AgentEvent>> {
          eventSource.close();
          done = true;
          return Promise.resolve({ value: undefined as any, done: true });
        },
      };
    },
  };
}
```

### Reconnection with Last-Event-ID

The `AgentStream` class wraps the SSE connection and handles automatic reconnection. When the connection drops, it reconnects with the `Last-Event-ID` header so the server replays missed events from its buffer (200 events, 5-min retention).

```typescript
class AgentStream implements AsyncIterable<AgentEvent> {
  private lastEventId: string = "";
  private events: AgentEvent[] = [];
  private controller = new AbortController();

  constructor(
    private url: string,
    private headers: Record<string, string>,
    private executionId: string,
    private runtime: AgentRuntime
  ) {}

  // HITL methods -- available on the stream object
  async approve(): Promise<void> {
    await this.runtime.respond(this.executionId, { approved: true });
  }

  async reject(reason?: string): Promise<void> {
    await this.runtime.respond(this.executionId, { approved: false, reason });
  }

  async send(message: string): Promise<void> {
    await this.runtime.respond(this.executionId, { message });
  }

  async getResult(): Promise<AgentResult> {
    // Drain remaining events, build AgentResult
    for await (const event of this) {
      // Consumed by the iterator
    }
    return this.buildResult();
  }

  async *[Symbol.asyncIterator](): AsyncIterator<AgentEvent> {
    let retries = 0;
    const maxRetries = 5;

    while (retries < maxRetries) {
      try {
        const eventIterator = this.createSSEIterator();
        for await (const event of eventIterator) {
          this.events.push(event);
          if (event.type === "done") return;
          yield event;
        }
        return; // Stream ended normally
      } catch (err) {
        if (err instanceof SSETimeoutError) {
          // Fall back to polling
          yield* this.pollFallback();
          return;
        }
        retries++;
        await new Promise((r) => setTimeout(r, 1000 * retries));
      }
    }
  }

  private async *pollFallback(): AsyncGenerator<AgentEvent> {
    while (true) {
      await new Promise((r) => setTimeout(r, 500));
      const status = await this.runtime.getStatus(this.executionId);
      if (status.isComplete) {
        yield { type: "done", output: status.output, executionId: this.executionId };
        return;
      }
      if (status.isWaiting) {
        yield { type: "waiting", executionId: this.executionId };
      }
    }
  }

  // ...
}
```

---

## 7. Error Handling

### Custom Error Hierarchy

TypeScript errors extend the built-in `Error` class. Each error type provides structured information for programmatic handling.

```typescript
/** Base error for all Agentspan SDK errors */
export class AgentspanError extends Error {
  constructor(message: string, public readonly cause?: Error) {
    super(message);
    this.name = "AgentspanError";
    // Preserve prototype chain for instanceof checks
    Object.setPrototypeOf(this, new.target.prototype);
  }
}

/** Server returned an HTTP error */
export class AgentAPIError extends AgentspanError {
  constructor(
    message: string,
    public readonly statusCode?: number,
    public readonly responseBody?: string
  ) {
    super(message);
    this.name = "AgentAPIError";
  }
}

/** Agent or workflow not found */
export class AgentNotFoundError extends AgentspanError {
  constructor(public readonly agentName: string) {
    super(`Agent not found: ${agentName}`);
    this.name = "AgentNotFoundError";
  }
}

/** Invalid configuration (missing model, conflicting settings, etc.) */
export class ConfigurationError extends AgentspanError {
  constructor(message: string) {
    super(message);
    this.name = "ConfigurationError";
  }
}

/** Credential not found in store */
export class CredentialNotFoundError extends AgentspanError {
  constructor(public readonly credentialName: string) {
    super(`Credential not found: ${credentialName}`);
    this.name = "CredentialNotFoundError";
  }
}

/** Credential auth token invalid or expired */
export class CredentialAuthError extends AgentspanError {
  constructor(message: string = "Credential token invalid or expired") {
    super(message);
    this.name = "CredentialAuthError";
  }
}

/** Credential service rate limit exceeded (120 calls/min) */
export class CredentialRateLimitError extends AgentspanError {
  constructor() {
    super("Credential rate limit exceeded (120 calls/min)");
    this.name = "CredentialRateLimitError";
  }
}

/** Credential service unavailable */
export class CredentialServiceError extends AgentspanError {
  constructor(message: string) {
    super(message);
    this.name = "CredentialServiceError";
  }
}

/** SSE connection timed out (no real events for 15s) */
export class SSETimeoutError extends AgentspanError {
  constructor(message: string = "SSE stream timed out") {
    super(message);
    this.name = "SSETimeoutError";
  }
}

/** Guardrail validation failed and on_fail=RAISE */
export class GuardrailFailedError extends AgentspanError {
  constructor(
    public readonly guardrailName: string,
    public readonly failureMessage: string
  ) {
    super(`Guardrail '${guardrailName}' failed: ${failureMessage}`);
    this.name = "GuardrailFailedError";
  }
}
```

### Guardrail Failure Propagation

When a guardrail with `on_fail: "raise"` fails, the SDK throws a `GuardrailFailedError`. Other modes are handled server-side (retry, fix, human), but RAISE propagates to the client.

```typescript
const complianceGuardrail = new GuardrailConfig({
  name: "compliance_check",
  external: true,
  position: "output",
  onFail: "raise",
});

try {
  const result = await runtime.run(reviewAgent, prompt);
} catch (err) {
  if (err instanceof GuardrailFailedError) {
    console.error(`Guardrail '${err.guardrailName}' blocked output: ${err.failureMessage}`);
  } else if (err instanceof AgentAPIError) {
    console.error(`Server error: ${err.statusCode} -- ${err.responseBody}`);
  }
}
```

### Timeout via AbortController

All network operations accept an `AbortSignal` for timeout control. This is the idiomatic TypeScript pattern for cancellation.

```typescript
// Timeout a run() call after 60 seconds
const controller = new AbortController();
const timeout = setTimeout(() => controller.abort(), 60_000);

try {
  const result = await runtime.run(myAgent, prompt, {
    signal: controller.signal,
  });
} catch (err) {
  if (err instanceof DOMException && err.name === "AbortError") {
    console.error("Agent execution timed out after 60 seconds");
  }
} finally {
  clearTimeout(timeout);
}

// Or using AbortSignal.timeout() (Node 18+)
try {
  const result = await runtime.run(myAgent, prompt, {
    signal: AbortSignal.timeout(60_000),
  });
} catch (err) {
  if (err instanceof DOMException && err.name === "AbortError") {
    console.error("Timed out");
  }
}
```

### Error Handling Best Practices

```typescript
try {
  const stream = await runtime.stream(pipeline, prompt);
  for await (const event of stream) {
    if (event.type === "error") {
      // Server-side error reported as an event -- may or may not be fatal
      console.warn(`Agent error event: ${event.content}`);
    }
    if (event.type === "waiting") {
      await stream.approve();
    }
  }
  const result = await stream.getResult();
  if (result.isFailed) {
    throw new AgentspanError(`Agent failed: ${result.error}`);
  }
} catch (err) {
  if (err instanceof AgentNotFoundError) {
    console.error("Deploy the agent first");
  } else if (err instanceof ConfigurationError) {
    console.error("Check AGENTSPAN_SERVER_URL and AGENTSPAN_API_KEY");
  } else if (err instanceof CredentialNotFoundError) {
    console.error(`Missing credential: ${err.credentialName}`);
  } else {
    throw err; // Re-throw unexpected errors
  }
}
```

---

## 8. Testing Framework

The testing module provides utilities for unit testing agents without a running server, fluent assertions for result verification, and deterministic record/replay for integration tests.

### mockRun() -- Serverless Testing

`mockRun()` executes an agent locally without connecting to the Agentspan server. It simulates the Conductor execution loop, dispatching tools and guardrails in-process.

```typescript
import { mockRun } from "agentspan/testing";

// vitest test file
import { describe, it, expect } from "vitest";

describe("research_database tool", () => {
  it("returns results with session context", async () => {
    const result = await mockRun(researchAgent, "Find quantum computing papers", {
      mockTools: {
        web_search: async (args) => ({ results: ["paper1", "paper2"] }),
      },
      mockCredentials: {
        RESEARCH_API_KEY: "test-key-123",
      },
      sessionId: "test-session",
    });

    expect(result.status).toBe("COMPLETED");
    expect(result.output).toBeDefined();
  });
});
```

### Fluent Assertion Chain -- expect(result)

The SDK provides a fluent `expect()` wrapper for `AgentResult` that chains readability-focused assertions. This integrates with vitest/jest's assertion model.

```typescript
import { expectResult } from "agentspan/testing";

it("completes the full pipeline", async () => {
  const result = await mockRun(fullPipeline, "Write an article about AI");

  expectResult(result)
    .toBeCompleted()
    .toContainOutput("article")
    .toHaveUsedTool("research_database")
    .toHaveUsedTool("web_search")
    .toHavePassedGuardrail("pii_blocker")
    .toHaveFinishReason("stop")
    .toHaveTokenUsageBelow(50_000);
});
```

Implementation of the fluent chain:

```typescript
export function expectResult(result: AgentResult) {
  return {
    toBeCompleted() {
      if (result.status !== "COMPLETED") {
        throw new Error(`Expected COMPLETED, got ${result.status}: ${result.error}`);
      }
      return this;
    },
    toContainOutput(text: string) {
      const output = JSON.stringify(result.output);
      if (!output.includes(text)) {
        throw new Error(`Output does not contain "${text}"`);
      }
      return this;
    },
    toHaveUsedTool(toolName: string) {
      const used = result.events.some(
        (e) => e.type === "tool_call" && e.toolName === toolName
      );
      if (!used) {
        throw new Error(`Tool "${toolName}" was not used`);
      }
      return this;
    },
    toHavePassedGuardrail(guardrailName: string) {
      const passed = result.events.some(
        (e) => e.type === "guardrail_pass" && e.guardrailName === guardrailName
      );
      if (!passed) {
        throw new Error(`Guardrail "${guardrailName}" did not pass`);
      }
      return this;
    },
    toHaveFinishReason(reason: FinishReason) {
      if (result.finishReason !== reason) {
        throw new Error(`Expected finish reason "${reason}", got "${result.finishReason}"`);
      }
      return this;
    },
    toHaveTokenUsageBelow(maxTokens: number) {
      if (result.tokenUsage && result.tokenUsage.totalTokens > maxTokens) {
        throw new Error(
          `Token usage ${result.tokenUsage.totalTokens} exceeds limit ${maxTokens}`
        );
      }
      return this;
    },
  };
}
```

### record() / replay() -- Deterministic Tests

`record()` captures the full event stream and tool call/response pairs to a JSON fixture file. `replay()` loads that fixture and replays the exact sequence, making tests fully deterministic and independent of LLM variability.

```typescript
import { record, replay } from "agentspan/testing";

// Record a live execution to a fixture file
it("records execution", async () => {
  const result = await record(
    myAgent,
    "Write an article about quantum computing",
    { fixturePath: "tests/fixtures/quantum_article.json" }
  );
  expectResult(result).toBeCompleted();
});

// Replay from the recorded fixture (no server needed)
it("replays recorded execution", async () => {
  const result = await replay("tests/fixtures/quantum_article.json");
  expectResult(result)
    .toBeCompleted()
    .toContainOutput("quantum")
    .toHaveUsedTool("research_database");
});
```

### Validation Runner (npm script + TOML config)

The validation runner executes kitchen sink examples against multiple models concurrently, with optional LLM judge evaluation. Configuration is via a TOML file.

```toml
# validation/runs.toml
[judge]
model = "openai/gpt-4o-mini"
max_output_chars = 3000
max_tokens = 300
rate_limit = 0.5

[[runs]]
name = "openai"
model = "openai/gpt-4o"
group = "SMOKE_TEST"
timeout = 300

[[runs]]
name = "anthropic"
model = "anthropic/claude-sonnet-4-20250514"
group = "SMOKE_TEST"
timeout = 300
```

Run via npm script:

```bash
pnpm run validate                          # Run all
pnpm run validate -- --run openai          # Run subset
pnpm run validate -- --dry-run             # Dry run
pnpm run validate -- --judge               # With judge
```

### vitest Integration

```typescript
// vitest.config.ts
import { defineConfig } from "vitest/config";

export default defineConfig({
  test: {
    globals: true,
    testTimeout: 60_000,
    include: ["tests/**/*.test.ts"],
    setupFiles: ["tests/setup.ts"],
  },
});

// tests/setup.ts
import { configure } from "agentspan";

configure({
  serverUrl: process.env.AGENTSPAN_SERVER_URL ?? "http://localhost:6767/api",
  apiKey: process.env.AGENTSPAN_API_KEY,
});
```

---

## 9. Kitchen Sink Translation

This section maps each of the 9 kitchen sink stages from the Python reference (`sdk/python/examples/kitchen_sink.py`) to idiomatic TypeScript. The full working implementation lives in `examples/kitchen_sink.ts`.

### Stage 1: Intake and Classification

**Python features:** `@agent` decorator, `Strategy.ROUTER`, `PromptTemplate`, `output_type`

```typescript
import { Agent, agent, PromptTemplate } from "agentspan";
import { z } from "zod";

const ClassificationResult = z.object({
  category: z.enum(["tech", "business", "creative"]),
  priority: z.number().int(),
  metadata: z.record(z.string(), z.unknown()),
});

const techClassifier = agent(() => "", { name: "tech_classifier", model: LLM_MODEL });
const businessClassifier = agent(() => "", { name: "business_classifier", model: LLM_MODEL });
const creativeClassifier = agent(() => "", { name: "creative_classifier", model: LLM_MODEL });

const intakeRouter = new Agent({
  name: "intake_router",
  model: LLM_MODEL,
  instructions: new PromptTemplate("article-classifier", { categories: "tech, business, creative" }),
  agents: [techClassifier, businessClassifier, creativeClassifier],
  strategy: "router",
  router: new Agent({
    name: "category_router",
    model: LLM_MODEL,
    instructions: "Route to the appropriate classifier based on article topic.",
  }),
  outputType: ClassificationResult,
});
```

**Key difference:** `PromptTemplate` is constructed with `new PromptTemplate(name, variables)` (or a plain object literal) instead of keyword arguments.

### Stage 2: Research Team

**Python features:** `@tool` with `ToolContext`, `CredentialFile`, `http_tool`, `mcp_tool`, `scatter_gather`, `Strategy.PARALLEL`

```typescript
import { tool, httpTool, mcpTool, apiTool, scatterGather, getCredential, Agent } from "agentspan";
import type { ToolContext, CredentialFile } from "agentspan";

const researchDatabase = tool(
  async (args: { query: string }, ctx?: ToolContext) => ({
    query: args.query,
    sessionId: ctx?.sessionId ?? "unknown",
    executionId: ctx?.executionId ?? "unknown",
    results: MOCK_RESEARCH_DATA.quantum_computing ?? {},
  }),
  { name: "research_database", credentials: [{ envVar: "RESEARCH_API_KEY" }] }
);

const webSearch = httpTool({
  name: "web_search",
  description: "Search the web for recent articles and papers.",
  url: "https://api.example.com/search",
  method: "GET",
  headers: { Authorization: "Bearer ${SEARCH_API_KEY}" },
  inputSchema: { type: "object", properties: { q: { type: "string" } }, required: ["q"] },
  credentials: ["SEARCH_API_KEY"],
});

const mcpFactChecker = mcpTool({
  serverUrl: "http://localhost:3001/mcp",
  name: "fact_checker",
  description: "Verify factual claims using knowledge base.",
  toolNames: ["verify_claim", "check_source"],
  credentials: ["MCP_AUTH_TOKEN"],
});

// Auto-discover from OpenAPI/Swagger/Postman spec
const stripe = apiTool({
  url: "https://api.stripe.com/openapi.json",
  headers: { Authorization: "Bearer ${STRIPE_KEY}" },
  credentials: ["STRIPE_KEY"],
  maxTools: 20,
});

const researchCoordinator = scatterGather({
  name: "research_coordinator",
  worker: researcherWorker,
  model: LLM_MODEL,
  instructions: "Create research tasks...",
  timeoutSeconds: 300,
});

const researchTeam = new Agent({
  name: "research_team",
  agents: [researchCoordinator, dataAnalyst],
  strategy: "parallel",
});
```

**Key difference:** `http_tool()` becomes `httpTool()` (camelCase). `CredentialFile` is a plain object `{ envVar: "..." }` rather than a class instance.

### Stage 3: Writing Pipeline

**Python features:** `>>` operator, `ConversationMemory`, `SemanticMemory`, `CallbackHandler`, `stop_when`

```typescript
import { Agent, ConversationMemory, SemanticMemory, CallbackHandler } from "agentspan";

const semanticMem = new SemanticMemory({ maxResults: 3 });
for (const article of MOCK_PAST_ARTICLES) {
  semanticMem.add(`Past article: ${article.title}`);
}

class PublishingCallbackHandler extends CallbackHandler {
  onAgentStart(agentName?: string) { callbackLog.log("before_agent", { agentName }); }
  onAgentEnd(agentName?: string) { callbackLog.log("after_agent", { agentName }); }
  onModelStart(messages?: unknown[]) { callbackLog.log("before_model", { messageCount: messages?.length ?? 0 }); }
  onModelEnd(llmResult?: string) { callbackLog.log("after_model", { resultLength: llmResult?.length ?? 0 }); }
  onToolStart(toolName?: string) { callbackLog.log("before_tool", { toolName }); }
  onToolEnd(toolName?: string) { callbackLog.log("after_tool", { toolName }); }
}

const draftWriter = new Agent({
  name: "draft_writer",
  model: LLM_MODEL,
  instructions: "Write a comprehensive article draft based on research findings.",
  tools: [recallPastArticles],
  memory: new ConversationMemory({ maxMessages: 50 }),
  callbacks: [new PublishingCallbackHandler()],
});

const editor = new Agent({
  name: "editor",
  model: LLM_MODEL,
  instructions: "Review and edit. When done, include ARTICLE_COMPLETE.",
  stopWhen: (messages: unknown[]) => {
    const last = messages[messages.length - 1] as Record<string, unknown> | undefined;
    return typeof last?.content === "string" && last.content.includes("ARTICLE_COMPLETE");
  },
});

// Sequential pipeline: Python's >> becomes .pipe()
const writingPipeline = draftWriter.pipe(editor);
```

**Key difference:** Python's `>>` operator becomes `.pipe()`. The method returns a new `Agent` with `strategy: "sequential"` wrapping the two agents.

### Stage 4: Review and Safety

**Python features:** `RegexGuardrail`, `LLMGuardrail`, `@guardrail`, external guardrail, `OnFail` modes, tool guardrails

```typescript
import { RegexGuardrail, LLMGuardrail, GuardrailConfig, guardrail } from "agentspan";

const piiGuardrail = new RegexGuardrail({
  name: "pii_blocker",
  patterns: [/\b\d{3}-\d{2}-\d{4}\b/.source, /\b\d{4}[\s-]?\d{4}[\s-]?\d{4}[\s-]?\d{4}\b/.source],
  mode: "block",
  position: "output",
  onFail: "retry",
  message: "PII detected. Redact all personal information.",
});

const biasGuardrail = new LLMGuardrail({
  name: "bias_detector",
  model: "openai/gpt-4o-mini",
  policy: "Check for biased language or stereotypes. If found, provide corrected version.",
  position: "output",
  onFail: "fix",
  maxTokens: 10000,
});

const factValidator = guardrail(
  (content: string) => {
    const redFlags = ["the best", "the worst", "always", "never", "guaranteed"];
    const found = redFlags.filter((rf) => content.toLowerCase().includes(rf));
    return found.length > 0
      ? { passed: false, message: `Unverifiable claims: ${found}` }
      : { passed: true };
  },
  { name: "fact_validator" }
);

const safeSearch = tool(
  async (args: { query: string }) => ({ query: args.query, results: ["result1", "result2"] }),
  {
    name: "safe_search",
    guardrails: [new GuardrailConfig({ fn: sqlInjectionGuard, position: "input", onFail: "raise" })],
  }
);

const reviewAgent = new Agent({
  name: "safety_reviewer",
  model: LLM_MODEL,
  guardrails: [
    piiGuardrail,
    biasGuardrail,
    new GuardrailConfig({ fn: factValidator, position: "output", onFail: "human" }),
    new GuardrailConfig({ name: "compliance_check", external: true, position: "output", onFail: "raise" }),
  ],
});
```

### Stage 5: Editorial Approval

**Python features:** `approval_required`, `human_tool`, `UserProxyAgent`, `Strategy.HANDOFF`, HITL interactions

```typescript
import { tool, humanTool, UserProxyAgent, Agent } from "agentspan";

const publishArticle = tool(
  async (args: { title: string; content: string; platform: string }) => ({
    status: "published", title: args.title, platform: args.platform,
  }),
  { name: "publish_article", approvalRequired: true }
);

const editorialQuestion = humanTool({
  name: "ask_editor",
  description: "Ask the editor a question about the article.",
  inputSchema: { type: "object", properties: { question: { type: "string" } }, required: ["question"] },
});

const editorialReviewer = new UserProxyAgent({
  name: "editorial_reviewer",
  model: LLM_MODEL,
  instructions: "You are the editorial reviewer.",
  humanInputMode: "TERMINATE",
});

const editorialAgent = new Agent({
  name: "editorial_approval",
  model: LLM_MODEL,
  tools: [publishArticle, editorialQuestion],
  agents: [editorialReviewer],
  strategy: "handoff",
});
```

### Stage 6: Translation and Discussion

**Python features:** `Strategy.ROUND_ROBIN`, `Strategy.SWARM`, `Strategy.RANDOM`, `Strategy.MANUAL`, `OnTextMention`, `allowed_transitions`, `introduction`

```typescript
const spanishTranslator = new Agent({
  name: "spanish_translator",
  model: LLM_MODEL,
  instructions: "You translate articles to Spanish with a formal tone.",
  introduction: "I am the Spanish translator, specializing in formal academic translations.",
});

// ... french_translator, german_translator similarly ...

const translationSwarm = new Agent({
  name: "translation_swarm",
  agents: [spanishTranslator, frenchTranslator, germanTranslator],
  strategy: "swarm",
  handoffs: [
    { type: "on_text_mention", text: "Spanish", target: "spanish_translator" },
    { type: "on_text_mention", text: "French", target: "french_translator" },
    { type: "on_text_mention", text: "German", target: "german_translator" },
  ],
  allowedTransitions: {
    spanish_translator: ["french_translator", "german_translator"],
    french_translator: ["spanish_translator", "german_translator"],
    german_translator: ["spanish_translator", "french_translator"],
  },
});
```

### Stage 7: Publishing Pipeline

**Python features:** `OnToolResult`, `OnCondition`, external agent, composable termination, `TextGate`

```typescript
import {
  TextMentionTermination, MaxMessageTermination, TokenUsageTermination, TextGate,
} from "agentspan";

const publishingPipeline = new Agent({
  name: "publishing_pipeline",
  model: LLM_MODEL,
  agents: [formatter, externalPublisher],
  strategy: "handoff",
  handoffs: [
    { type: "on_tool_result", target: "external_publisher", toolName: "format_check" },
    { type: "on_condition", target: "external_publisher", condition: shouldHandoffToPublisher },
  ],
  // Composable termination: Python's | and & become .or() and .and()
  termination: new TextMentionTermination("PUBLISHED")
    .or(new MaxMessageTermination(50).and(new TokenUsageTermination({ maxTotalTokens: 100_000 }))),
  gate: new TextGate({ text: "APPROVED" }),
});
```

**Key difference:** Python's `|` and `&` operators on `TerminationCondition` become `.or()` and `.and()` method calls. This is because TypeScript does not support operator overloading on arbitrary classes.

### Stage 8: Analytics and Reporting

**Python features:** Code executors, media tools, RAG tools, `agent_tool`, `GPTAssistantAgent`, `thinking_budget_tokens`, `planner`, `required_tools`, `CliConfig`

```typescript
import {
  LocalCodeExecutor, DockerCodeExecutor, JupyterCodeExecutor, ServerlessCodeExecutor,
  imageTool, audioTool, videoTool, pdfTool, searchTool, indexTool,
  agentTool, GPTAssistantAgent,
} from "agentspan";

const researchSubtool = agentTool(
  new Agent({ name: "quick_researcher", model: LLM_MODEL, instructions: "Quick research lookup." }),
  { name: "quick_research", description: "Quick research lookup as a tool." }
);

const analyticsAgent = new Agent({
  name: "analytics_agent",
  model: LLM_MODEL,
  tools: [
    localExecutor.asTool(),
    dockerExecutor.asTool({ name: "run_sandboxed" }),
    imageTool({ name: "generate_thumbnail", llmProvider: "openai", model: "dall-e-3", description: "..." }),
    searchTool({ name: "search_articles", vectorDb: "pgvector", index: "articles", /* ... */ }),
    researchSubtool,
  ],
  agents: [new GPTAssistantAgent({ name: "openai_research_assistant", model: "gpt-4o" })],
  strategy: "handoff",
  thinkingBudgetTokens: 2048,
  includeContents: "default",
  outputType: ArticleReport,
  requiredTools: ["index_article"],
  planner: true,
  codeExecutionConfig: { enabled: true, allowedLanguages: ["python", "shell"], timeout: 30 },
  cliConfig: { enabled: true, allowedCommands: ["git", "gh"], timeout: 30 },
  metadata: { stage: "analytics", version: "1.0" },
});
```

### Stage 9: Execution Modes

**Python features:** `deploy`, `plan`, `stream` (sync+async), `start`, `run`, HITL on stream, `discover_agents`, `is_tracing_enabled`

```typescript
import { AgentRuntime, configure, run, start, stream, deploy, plan, discoverAgents, isTracingEnabled, shutdown } from "agentspan";

const PROMPT = "Write a comprehensive tech article about quantum computing advances in 2026...";

if (isTracingEnabled()) {
  console.log("[tracing] OpenTelemetry tracing is enabled");
}

// Using runtime as a resource (dispose pattern)
await using runtime = new AgentRuntime();

// Deploy
const deployments = await runtime.deploy(fullPipeline);
for (const dep of deployments) {
  console.log(`  Deployed: ${dep.registeredName} (${dep.agentName})`);
}

// Plan (dry-run)
const executionPlan = await runtime.plan(fullPipeline);

// Stream with HITL
const agentStream = await runtime.stream(fullPipeline, PROMPT);
const hitlState = { approved: 0, rejected: 0, feedback: 0 };

for await (const event of agentStream) {
  switch (event.type) {
    case "thinking":
      console.log(`  [thinking] ${event.content?.slice(0, 80)}...`);
      break;
    case "tool_call":
      console.log(`  [tool_call] ${event.toolName}(${JSON.stringify(event.args)})`);
      break;
    case "waiting":
      console.log("  --- HITL: Approval required ---");
      if (hitlState.feedback === 0) {
        await agentStream.send("Please add more details about quantum error correction.");
        hitlState.feedback++;
      } else if (hitlState.rejected === 0) {
        await agentStream.reject("Title needs improvement");
        hitlState.rejected++;
      } else {
        await agentStream.approve();
        hitlState.approved++;
      }
      break;
    case "done":
      console.log("  [done] Pipeline complete");
      break;
  }
}

const result = await agentStream.getResult();
if (result.tokenUsage) {
  console.log(`Total tokens: ${result.tokenUsage.totalTokens}`);
}

// Start + polling
const handle = await runtime.start(fullPipeline, PROMPT);
const status = await handle.getStatus();
console.log(`  Status: ${status.status}, Running: ${status.isRunning}`);

// Top-level convenience
configure({ serverUrl: process.env.AGENTSPAN_SERVER_URL });
const simpleResult = await run(new Agent({ name: "simple_test", model: LLM_MODEL, instructions: "Say hello." }), "Hello!");

// Discover agents
const agents = await discoverAgents("examples/");
console.log(`  Discovered ${agents.length} agents`);

// Cleanup
await shutdown();
```

**Key differences from Python:**
- `for await (const event of stream)` replaces `for event in agent_stream`
- `stream.send()`, `stream.approve()`, `stream.reject()` are the HITL methods on the stream object (same API shape as Python)
- `await using runtime = new AgentRuntime()` uses the TC39 Explicit Resource Management proposal (`Symbol.asyncDispose`) for automatic cleanup. Falls back to manual `runtime.shutdown()` in environments without `using` support
- No `run_async()` / `stream_async()` split: all functions return `Promise<T>` and are awaited directly
- `>>` becomes `.pipe()`; `&` / `|` for termination composition become `.and()` / `.or()`
- `EventSource` (browser) or `fetch` + `ReadableStream` (Node.js) replaces Python's SSE client
