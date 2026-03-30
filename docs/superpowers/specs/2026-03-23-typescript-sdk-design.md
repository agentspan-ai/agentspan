# TypeScript SDK Design Spec

**Date:** 2026-03-23 (updated 2026-03-24)
**Status:** Review
**Base spec:** `docs/sdk-design/2026-03-23-multi-language-sdk-design.md`
**Reference implementation:** `sdk/python/` (Python SDK)
**Replaces:** `sdk/typescript/` (PoC JS SDK)

---

## 1. Overview

The `@agentspan/sdk` TypeScript SDK is a complete rewrite of the existing JavaScript PoC. It provides full 89-feature parity with the Python reference SDK, plus framework integration for running Vercel AI SDK, LangGraph.js, LangChain.js, OpenAI Agents SDK, and Google ADK agents on agentspan's durable runtime.

### 1.1 Design Principles

| Principle | Decision |
|-----------|----------|
| Language | TypeScript-first (`.ts` source, compiled to ESM + CJS) |
| Package | `@agentspan/sdk` v1.0.0 — clean break from PoC |
| Runtime | Node.js 18+ (native `fetch`, `AbortController`, `ReadableStream`) |
| Schema | **Superset** — accepts both Zod schemas and JSON Schema, auto-detecting format |
| Framework integration | Auto-detecting runtime — `runtime.run()` accepts native agents and framework agents |
| Conductor client | Raw `fetch`-based task polling (drops `@io-orkes/conductor-javascript`) |
| Build | `tsup` → ESM + CJS dual output with `.d.ts` declarations |
| Test runner | Vitest |
| API style | Options-object pattern (single config object per function call) |

### 1.2 Architecture

```
┌──────────────────────────────────────────────────────────┐
│                  @agentspan/sdk (TypeScript)              │
│                                                          │
│  ┌─────────────┐  ┌──────────────┐  ┌────────────────┐  │
│  │ Agent + Tool │  │  Serializer  │  │   Framework    │  │
│  │ Definitions  │──│  → JSON      │  │   Detection    │  │
│  │ (Zod/JSON)   │  │  AgentConfig │  │ (duck-typing)  │  │
│  └─────────────┘  └──────┬───────┘  └───────┬────────┘  │
│                          │                    │           │
│  ┌───────────────────────▼────────────────────▼───────┐  │
│  │                  AgentRuntime                       │  │
│  │  run() / start() / stream() / deploy() / plan()    │  │
│  └──────────────────────┬─────────────────────────────┘  │
│                         │                                 │
│  ┌──────────┐  ┌────────▼────────┐  ┌────────────────┐  │
│  │  Worker   │  │   HTTP Client   │  │   SSE Client   │  │
│  │  Manager  │  │   (REST API)    │  │  (AgentStream) │  │
│  │ (polling) │  └────────┬────────┘  └───────┬────────┘  │
│  └────┬─────┘           │                    │           │
│       │                  │                    │           │
└───────┼──────────────────┼────────────────────┼──────────┘
        │                  │                    │
        │        REST + SSE (JSON)              │
        │                  │                    │
┌───────▼──────────────────▼────────────────────▼──────────┐
│                 Agentspan Server (Java)                    │
│                                                           │
│  Compiler → Conductor WorkflowDef                         │
│  Executor → Conductor Workflow Engine                      │
│  StreamRegistry → SSE Events                              │
│  CredentialService → AES-256-GCM Store                    │
│  Normalizers → LangGraph/LangChain/VercelAI/OpenAI/ADK   │
└───────────────────────────────────────────────────────────┘
```

### 1.3 Key Design Decisions

1. **Superset tool compatibility** — `tool()` accepts Zod schemas (auto-converted via `zod-to-json-schema`) or raw JSON Schema objects. Vercel AI SDK `tool()` objects are auto-detected and wrapped. All three styles can coexist in a single agent's `tools` array.

2. **Auto-detecting runtime** — `runtime.run(agent, prompt)` calls `detectFramework(agent)` to determine if the object is a native `Agent`, a Vercel AI SDK `ToolLoopAgent`, a LangGraph `CompiledStateGraph`, etc. No explicit wrapping required.

3. **No Conductor client dependency** — Task polling implemented with raw `fetch` + `setInterval`. Eliminates the heavy `@io-orkes/conductor-javascript` dependency and its noisy logging.

4. **Optional peer dependencies for frameworks** — `ai`, `@langchain/core`, `@langchain/langgraph` are optional peers. Detection uses duck-typing so the SDK works without any framework installed.

5. **Composable conditions via methods** — Since TypeScript lacks operator overloading, termination conditions use `.and()` / `.or()` methods instead of `&` / `|`. Agent chaining uses `.pipe()` instead of `>>`.

---

## 2. Package Structure

### 2.1 Dependencies

| Dependency | Type | Purpose |
|-----------|------|---------|
| `zod` | peer (required) | Schema validation + type inference |
| `zod-to-json-schema` | runtime | Convert Zod → JSON Schema for wire format |
| `dotenv` | runtime | `.env` file loading |
| `ai` | peer (optional) | Vercel AI SDK framework passthrough |
| `@langchain/core` | peer (optional) | LangChain.js framework passthrough |
| `@langchain/langgraph` | peer (optional) | LangGraph.js framework passthrough |

### 2.2 package.json

```json
{
  "name": "@agentspan/sdk",
  "version": "1.0.0",
  "type": "module",
  "main": "./dist/index.cjs",
  "module": "./dist/index.js",
  "types": "./dist/index.d.ts",
  "exports": {
    ".": {
      "import": "./dist/index.js",
      "require": "./dist/index.cjs",
      "types": "./dist/index.d.ts"
    },
    "./testing": {
      "import": "./dist/testing/index.js",
      "require": "./dist/testing/index.cjs",
      "types": "./dist/testing/index.d.ts"
    },
    "./validation": {
      "import": "./dist/validation/runner.js",
      "require": "./dist/validation/runner.cjs",
      "types": "./dist/validation/runner.d.ts"
    }
  },
  "engines": { "node": ">=18.0.0" },
  "peerDependencies": {
    "zod": "^3.22.0",
    "ai": "^4.0.0",
    "@langchain/core": "^0.3.0",
    "@langchain/langgraph": "^0.2.0",
    "@openai/agents": "^1.0.0",
    "@google/adk": "^1.0.0"
  },
  "peerDependenciesMeta": {
    "ai": { "optional": true },
    "@langchain/core": { "optional": true },
    "@langchain/langgraph": { "optional": true },
    "@openai/agents": { "optional": true },
    "@google/adk": { "optional": true }
  },
  "dependencies": {
    "zod-to-json-schema": "^3.22.0",
    "dotenv": "^16.0.0"
  },
  "devDependencies": {
    "typescript": "^5.4.0",
    "tsup": "^8.0.0",
    "vitest": "^2.0.0",
    "@types/node": "^20.0.0"
  },
  "scripts": {
    "build": "tsup",
    "test": "vitest run",
    "test:watch": "vitest",
    "lint": "tsc --noEmit",
    "validate": "tsx src/validation/runner.ts --config runs.toml"
  }
}
```

### 2.3 Directory Layout

```
sdk/typescript/
  src/
    index.ts                    # Public re-exports
    agent.ts                    # Agent, Strategy, PromptTemplate
    tool.ts                     # tool(), httpTool, mcpTool, apiTool, agentTool, media/RAG tools
    guardrail.ts                # guardrail(), RegexGuardrail, LLMGuardrail
    result.ts                   # AgentResult, AgentHandle, AgentStatus, AgentEvent
    stream.ts                   # AgentStream — SSE client + AsyncIterable + HITL methods
    runtime.ts                  # AgentRuntime — run/start/stream/deploy/plan/shutdown
    worker.ts                   # WorkerManager — raw fetch task polling + execution
    memory.ts                   # ConversationMemory, SemanticMemory, InMemoryStore
    termination.ts              # TextMention, StopMessage, MaxMessage, TokenUsage (.and/.or)
    handoff.ts                  # OnToolResult, OnTextMention, OnCondition
    credentials.ts              # getCredential, resolveCredentials, CredentialFile
    callback.ts                 # CallbackHandler base class (6 positions)
    code-execution.ts           # CodeExecutor, Local/Docker/Jupyter/Serverless + asTool()
    errors.ts                   # AgentspanError hierarchy (9 error types)
    types.ts                    # Shared interfaces, enums, ToolContext, EventType, Status
    serializer.ts               # Agent → AgentConfig JSON (recursive, handles all tool types)
    config.ts                   # AgentConfig env var loading, URL normalization
    ext.ts                      # UserProxyAgent, GPTAssistantAgent
    discovery.ts                # discoverAgents(path)
    tracing.ts                  # OpenTelemetry integration
    frameworks/
      detect.ts                 # detectFramework() — duck-typing for all 5 frameworks
      vercel-ai.ts              # makeVercelAIWorker(), step → event mapping
      langgraph.ts              # makeLangGraphWorker(), dual-stream event mapping
      langchain.ts              # makeLangChainWorker(), callback handler injection
      openai-agents.ts          # makeOpenAIAgentsWorker()
      google-adk.ts             # makeGoogleADKWorker()
      event-push.ts             # pushEvent() — non-blocking HTTP POST to /agent/{id}/events
    testing/
      index.ts                  # Re-exports: mockRun, expectResult, record, replay
      mock.ts                   # mockRun() — serverless execution
      expect.ts                 # expectResult() — fluent assertion chain
      assertions.ts             # assertToolUsed, assertGuardrailPassed, assertAgentRan, etc.
      eval.ts                   # CorrectnessEval — LLM judge
      strategy.ts               # validateStrategy()
      recording.ts              # record() / replay() — fixture capture + deterministic replay
    validation/
      runner.ts                 # Concurrent executor (entry point for CLI)
      config.ts                 # TOML parsing for runs.toml
      judge.ts                  # LLM judge integration
      report.ts                 # HTML report generation with score heatmap
  examples/
    kitchen-sink.ts             # Full 89-feature acceptance test
    01-basic-agent.ts
    02-tools.ts
    03-multi-agent.ts
    04-guardrails.ts
    05-streaming.ts
    06-hitl.ts
    07-memory.ts
    08-credentials.ts
    09-structured-output.ts
    10-code-execution.ts
    vercel-ai/
      01-passthrough.ts         # Run ToolLoopAgent on agentspan
      02-tools-compat.ts        # Mix AI SDK + native tools
      03-streaming.ts           # Stream Vercel AI SDK agent events
    langgraph/
      01-react-agent.ts         # createReactAgent passthrough
      02-custom-graph.ts        # StateGraph passthrough
      03-hitl.ts                # HITL with LangGraph
    langchain/
      01-agent-executor.ts      # AgentExecutor passthrough
      02-chain.ts               # RunnableSequence passthrough
    openai-agents/
      01-basic.ts               # OpenAI Agent passthrough
    google-adk/
      01-basic.ts               # Google ADK passthrough
  tests/
    unit/                       # No server required (52+ test files)
      agent.test.ts
      tool.test.ts
      serializer.test.ts
      guardrail.test.ts
      termination.test.ts
      handoff.test.ts
      memory.test.ts
      stream.test.ts
      worker.test.ts
      credentials.test.ts
      frameworks/
        detect.test.ts
        vercel-ai.test.ts
        langgraph.test.ts
        langchain.test.ts
    integration/                # Requires running server
      run.test.ts
      stream.test.ts
      hitl.test.ts
      frameworks.test.ts
    e2e/
      kitchen-sink.test.ts
  tsconfig.json
  tsup.config.ts
  vitest.config.ts
```

### 2.4 tsconfig.json

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
  "exclude": ["node_modules", "dist", "tests", "examples"]
}
```

### 2.5 tsup.config.ts

```typescript
import { defineConfig } from 'tsup';

export default defineConfig({
  entry: [
    'src/index.ts',
    'src/testing/index.ts',
    'src/validation/runner.ts',
  ],
  format: ['esm', 'cjs'],
  dts: true,
  splitting: true,
  sourcemap: true,
  clean: true,
  target: 'node18',
});
```

---

## 3. Type System

### 3.1 Core Types

```typescript
// ── Enums as string unions ─────────────────────────────────

export type Strategy =
  | 'handoff' | 'sequential' | 'parallel' | 'router'
  | 'round_robin' | 'random' | 'swarm' | 'manual';

export type EventType =
  | 'thinking' | 'tool_call' | 'tool_result'
  | 'guardrail_pass' | 'guardrail_fail'
  | 'waiting' | 'handoff' | 'message' | 'error' | 'done';

export type Status = 'COMPLETED' | 'FAILED' | 'TERMINATED' | 'TIMED_OUT';

export type FinishReason =
  | 'stop' | 'length' | 'tool_calls' | 'error'
  | 'cancelled' | 'timeout' | 'guardrail' | 'rejected';

export type OnFail = 'retry' | 'raise' | 'fix' | 'human';
export type Position = 'input' | 'output';

export type ToolType =
  | 'worker' | 'http' | 'api' | 'mcp' | 'agent_tool' | 'human'
  | 'generate_image' | 'generate_audio' | 'generate_video' | 'generate_pdf'
  | 'rag_search' | 'rag_index';

export type FrameworkId =
  | 'vercel_ai' | 'langgraph' | 'langchain' | 'openai' | 'google_adk';
```

### 3.2 Data Interfaces

```typescript
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
  state: Record<string, unknown>;  // Mutable — mutations captured as _state_updates
}
```

**ToolContext.state mutation capture (base spec §14.6):** When a tool modifies `ctx.state`, the SDK worker must capture mutations and append them to the tool result:

- Key name: `_state_updates` (underscore prefix)
- Only included if `state` is non-empty after tool execution
- If tool result is an object: merge `_state_updates` into the object
- If tool result is not an object: wrap as `{ result: <original>, _state_updates: {...} }`
- Server extracts `_state_updates`, persists state, removes key from user-visible output

```typescript
// Worker implementation pseudocode:
const stateBefore = { ...ctx.state };
const result = await handler(args, ctx);
const stateUpdates: Record<string, unknown> = {};
for (const [k, v] of Object.entries(ctx.state)) {
  if (JSON.stringify(v) !== JSON.stringify(stateBefore[k])) stateUpdates[k] = v;
}
if (Object.keys(stateUpdates).length > 0) {
  if (typeof result === 'object' && result !== null) {
    return { ...result, _state_updates: stateUpdates };
  }
  return { result, _state_updates: stateUpdates };
}

export interface GuardrailResult {
  passed: boolean;
  message?: string;
  fixedOutput?: string;
}

export interface AgentEvent {
  type: EventType | string;          // string allows server-only types to pass through
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
  readonly isSuccess: boolean;
  readonly isFailed: boolean;
  readonly isRejected: boolean;
  printResult(): void;
}
```

**AgentResult.output normalization rules:** The SDK must normalize raw server responses before exposing `AgentResult.output`:

1. If output is a string → wrap as `{ result: <string> }`
2. If output is `null`/`undefined` and status is COMPLETED → `{ result: null }`
3. If output is `null`/`undefined` and status is FAILED → `{ error: <error_message> }`
4. If output is already an object → use as-is
5. `output` is **always** a `Record<string, unknown>` — never a primitive

**AgentEvent key stripping (base spec §14.12):** Before exposing `AgentEvent` to users, the SDK must strip internal Conductor routing keys from `args`:
- Remove `_agent_state` key from `event.args`
- Remove `method` key from `event.args`

These are internal Conductor fields that must not leak to user-facing event streams.

```typescript
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
  agentName: string;
  workflowDef?: object;  // Included in deploy() response (Conductor WorkflowDef)
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

### 3.3 Agent Interface

```typescript
export interface AgentOptions {
  name: string;
  model?: string;
  instructions?: string | PromptTemplate | ((...args: unknown[]) => string);
  tools?: ToolDef[];
  agents?: Agent[];
  strategy?: Strategy;
  router?: Agent | ((...args: unknown[]) => string);
  outputType?: ZodSchema | object;           // Zod schema or JSON Schema
  guardrails?: GuardrailDef[];
  memory?: ConversationMemory;
  maxTurns?: number;
  maxTokens?: number;
  temperature?: number;
  timeoutSeconds?: number;
  external?: boolean;
  stopWhen?: (messages: unknown[], ...args: unknown[]) => boolean;
  termination?: TerminationCondition;
  handoffs?: HandoffCondition[];
  allowedTransitions?: Record<string, string[]>;
  introduction?: string;
  metadata?: Record<string, unknown>;
  callbacks?: CallbackHandler[];
  planner?: boolean;
  includeContents?: 'default' | 'none';
  thinkingBudgetTokens?: number;
  requiredTools?: string[];
  gate?: GateCondition;
  codeExecutionConfig?: CodeExecutionConfig;
  cliConfig?: CliConfig;
  credentials?: (string | CredentialFile)[];
}
```

---

## 4. Tool System (Superset)

### 4.1 Auto-Detection Logic

The serializer inspects each tool in the `tools` array and normalizes it:

```typescript
function normalizeToolInput(toolInput: unknown): ToolDef {
  // 1. Already an agentspan ToolDef (has _toolDef symbol)
  if (hasToolDef(toolInput)) return getToolDef(toolInput);

  // 2. Vercel AI SDK tool() object (has inputSchema as ZodType + execute fn)
  if (isVercelAITool(toolInput)) return wrapVercelAITool(toolInput);

  // 3. Raw object with required shape (name + description + inputSchema)
  if (isRawToolDef(toolInput)) return toolInput as ToolDef;

  throw new ConfigurationError(`Unrecognized tool format: ${typeof toolInput}`);
}

function isVercelAITool(obj: unknown): boolean {
  return obj != null
    && typeof obj === 'object'
    && 'inputSchema' in obj
    && 'execute' in obj
    && isZodSchema((obj as any).inputSchema);
}

function isZodSchema(obj: unknown): boolean {
  return obj != null && typeof obj === 'object' && '_def' in obj;
}
```

### 4.2 Zod → JSON Schema Conversion

At serialization time (not at definition time), Zod schemas are converted to JSON Schema:

```typescript
import { zodToJsonSchema } from 'zod-to-json-schema';

function serializeInputSchema(schema: ZodSchema | object): object {
  if (isZodSchema(schema)) {
    return zodToJsonSchema(schema, { target: 'jsonSchema7' });
  }
  return schema; // Already JSON Schema — pass through
}
```

### 4.3 tool() Function

```typescript
export function tool<TInput, TOutput>(
  fn: (args: TInput, ctx?: ToolContext) => Promise<TOutput>,
  options: {
    name?: string;
    description: string;
    inputSchema: ZodSchema<TInput> | object;
    outputSchema?: ZodSchema<TOutput> | object;
    approvalRequired?: boolean;
    timeoutSeconds?: number;
    external?: boolean;
    isolated?: boolean;
    credentials?: (string | CredentialFile)[];
    guardrails?: GuardrailDef[];
  }
): ToolFunction<TInput, TOutput>;
```

When `external: true`, `fn` is ignored — no local worker is registered. Only the schema is emitted in AgentConfig.

### 4.4 Server-Side Tool Constructors

All produce `ToolDef` objects with no local worker:

| Function | toolType | Purpose |
|----------|----------|---------|
| `httpTool(opts)` | `http` | HTTP API call (server-side) |
| `apiTool(opts)` | `api` | Auto-discover from OpenAPI/Swagger/Postman spec |
| `mcpTool(opts)` | `mcp` | MCP protocol tool |
| `agentTool(agent, opts)` | `agent_tool` | Sub-agent as callable tool |
| `humanTool(opts)` | `human` | Human-in-the-loop tool |
| `imageTool(opts)` | `generate_image` | Image generation |
| `audioTool(opts)` | `generate_audio` | Audio generation (TTS) |
| `videoTool(opts)` | `generate_video` | Video generation |
| `pdfTool(opts)` | `generate_pdf` | PDF generation from markdown |
| `searchTool(opts)` | `rag_search` | Vector search (RAG) |
| `indexTool(opts)` | `rag_index` | Vector index (RAG) |

### 4.5 httpTool Credential Header Substitution

```typescript
const api = httpTool({
  name: 'search_api',
  description: 'Search via API',
  url: 'https://api.example.com/search',
  method: 'GET',
  headers: { Authorization: 'Bearer ${SEARCH_API_KEY}' }, // ${NAME} resolved server-side
  credentials: ['SEARCH_API_KEY'],
  inputSchema: { type: 'object', properties: { q: { type: 'string' } }, required: ['q'] },
});
```

All placeholder names in headers must be declared in the `credentials` array.

### 4.6 @Tool Decorator (Class Method Pattern)

```typescript
import { Tool, ToolContext } from '@agentspan/sdk';

class ResearchTools {
  @Tool({ credentials: [{ envVar: 'RESEARCH_API_KEY' }] })
  async researchDatabase(query: string, ctx?: ToolContext): Promise<Record<string, unknown>> {
    return { query, sessionId: ctx?.sessionId ?? 'unknown', results: { count: 42 } };
  }

  @Tool({ external: true })
  async externalAggregator(query: string): Promise<Record<string, unknown>> {
    return {}; // No local implementation — runs on remote worker
  }

  @Tool({ approvalRequired: true })
  async publishArticle(title: string, content: string): Promise<Record<string, unknown>> {
    return { status: 'published', title };
  }
}

// Extract decorated methods as tool() wrappers
const tools = toolsFrom(new ResearchTools());
```

### 4.7 Vercel AI SDK Tool Wrapping

When a Vercel AI SDK `tool()` object is detected in the `tools` array:

```typescript
function wrapVercelAITool(aiTool: VercelAIToolShape): ToolDef {
  const jsonSchema = zodToJsonSchema(aiTool.inputSchema, { target: 'jsonSchema7' });
  const wrapped = tool(
    async (args: unknown) => aiTool.execute(args, {}),
    {
      name: aiTool.title ?? aiTool.description?.slice(0, 30).replace(/\s+/g, '_') ?? 'ai_tool',
      description: aiTool.description ?? '',
      inputSchema: jsonSchema,
    }
  );
  return getToolDef(wrapped);
}
```

---

## 5. Guardrail System

### 5.1 guardrail() Function

```typescript
export function guardrail(
  fn: (content: string) => GuardrailResult | Promise<GuardrailResult>,
  options: {
    name: string;
    position?: Position;       // default: 'output'
    onFail?: OnFail;           // default: 'raise'
    maxRetries?: number;       // default: 3 (for onFail='retry')
  }
): GuardrailDef;

// External guardrail (no local worker)
guardrail.external = (options: {
  name: string;
  position?: Position;
  onFail?: OnFail;
}): GuardrailDef;
```

Custom guardrails are registered as Conductor SIMPLE workers. The worker receives the content to validate and returns `GuardrailResult`.

### 5.2 Built-In Guardrails

```typescript
// Regex guardrail — server-side INLINE JavaScript, no worker
export class RegexGuardrail {
  constructor(options: {
    name: string;
    patterns: string[];            // regex patterns
    mode: 'block' | 'allow';      // block = fail on match, allow = fail on no match
    position?: Position;
    onFail?: OnFail;
    message?: string;              // custom failure message
  });
}

// LLM guardrail — server-side LLM_CHAT_COMPLETE, no worker
export class LLMGuardrail {
  constructor(options: {
    name: string;
    model: string;                 // 'provider/model' format
    policy: string;                // evaluation prompt
    position?: Position;
    onFail?: OnFail;
    maxTokens?: number;
  });
}
```

### 5.3 @Guardrail Decorator

```typescript
class SafetyGuardrails {
  @Guardrail({ position: 'output', onFail: 'human' })
  factValidator(content: string): GuardrailResult {
    const redFlags = ['the best', 'always', 'never'];
    const found = redFlags.filter(rf => content.toLowerCase().includes(rf));
    return found.length > 0
      ? { passed: false, message: `Unverifiable claims: ${found.join(', ')}` }
      : { passed: true };
  }
}
```

### 5.4 Wire Format

```json
{
  "name": "pii_blocker",
  "position": "output",
  "onFail": "retry",
  "maxRetries": 3,
  "guardrailType": "regex",
  "patterns": ["\\b\\d{3}-\\d{2}-\\d{4}\\b"],
  "mode": "block",
  "message": "PII detected"
}
```

| guardrailType | Execution | Worker |
|---------------|-----------|--------|
| `regex` | Server-side INLINE JS | None |
| `llm` | Server-side LLM call | None |
| `custom` | SDK worker (SIMPLE task) | Yes |
| `external` | Remote worker (SIMPLE task) | None (remote) |

---

## 6. Memory System

### 6.1 ConversationMemory

Session-level conversation history, serialized to wire format.

```typescript
export class ConversationMemory {
  constructor(options?: { maxMessages?: number });

  addUserMessage(content: string): void;
  addAssistantMessage(content: string): void;
  addSystemMessage(content: string): void;
  addToolCall(name: string, args: unknown): void;
  addToolResult(name: string, result: unknown): void;
  toChatMessages(): unknown[];
  clear(): void;
}
```

**Wire format:** `{ "messages": [...], "maxMessages": 50 }`

**Max message windowing:** When `maxMessages` is set, trim oldest messages but always preserve system messages.

### 6.2 SemanticMemory

Cross-session long-term memory with pluggable vector search.

```typescript
export class SemanticMemory {
  constructor(options: { store: MemoryStore });

  async add(content: string, metadata?: Record<string, unknown>): Promise<string>;
  async search(query: string, topK?: number): Promise<MemoryEntry[]>;
  async delete(id: string): Promise<void>;
  async clear(): Promise<void>;
  async listAll(): Promise<MemoryEntry[]>;
}

export interface MemoryStore {
  add(entry: MemoryEntry): Promise<string>;
  search(query: string, topK: number): Promise<MemoryEntry[]>;
  delete(id: string): Promise<void>;
  clear(): Promise<void>;
  listAll(): Promise<MemoryEntry[]>;
}

// Built-in: keyword-overlap similarity (no external deps)
export class InMemoryStore implements MemoryStore { /* ... */ }
```

---

## 7. Termination & Handoff Conditions

### 7.1 Composable Termination

Since TypeScript lacks operator overloading, composition uses `.and()` / `.or()` methods:

```typescript
export abstract class TerminationCondition {
  and(other: TerminationCondition): TerminationCondition;
  or(other: TerminationCondition): TerminationCondition;
  abstract toJSON(): object;
}

export class TextMention extends TerminationCondition {
  constructor(text: string, caseSensitive?: boolean);
  // Wire: { "type": "text_mention", "text": "DONE", "caseSensitive": false }
}

export class StopMessage extends TerminationCondition {
  constructor(stopMessage: string);
}

export class MaxMessage extends TerminationCondition {
  constructor(maxMessages: number);
}

export class TokenUsage extends TerminationCondition {
  constructor(options: {
    maxTotalTokens?: number;
    maxPromptTokens?: number;
    maxCompletionTokens?: number;
  });
}
```

**Composition example:**
```typescript
const t = new TextMention('PUBLISHED').or(
  new MaxMessage(50).and(new TokenUsage({ maxTotalTokens: 100000 }))
);
// Wire: { "type": "or", "conditions": [
//   { "type": "text_mention", "text": "PUBLISHED" },
//   { "type": "and", "conditions": [
//     { "type": "max_message", "maxMessages": 50 },
//     { "type": "token_usage", "maxTotalTokens": 100000 }
//   ]}
// ]}
```

### 7.2 Handoff Conditions

```typescript
export class OnToolResult {
  constructor(options: { target: string; toolName: string; resultContains?: string });
}

export class OnTextMention {
  constructor(options: { target: string; text: string });
}

export class OnCondition {
  constructor(options: {
    target: string;
    condition: (messages: unknown[]) => boolean | Promise<boolean>;
  });
  // Condition registers as Conductor SIMPLE worker
}
```

### 7.3 Gate Conditions

```typescript
export class TextGate {
  constructor(text: string, caseSensitive?: boolean);
  // Wire: { "type": "text_contains", "text": "APPROVED", "caseSensitive": true }
}

// Custom gate (callable → registers as worker)
export function gate(
  fn: (output: string) => boolean | Promise<boolean>,
  options?: { name?: string }
): GateCondition;
```

### 7.4 Agent Chaining

```typescript
// .pipe() replaces Python's >> operator
const pipeline = researcher.pipe(writer).pipe(editor);
// Equivalent to:
new Agent({ name: 'pipeline', agents: [researcher, writer, editor], strategy: 'sequential' });
```

**Flattening rule (base spec §14.14):** `.pipe()` must flatten sequential agents. `a.pipe(b).pipe(c)` must produce `Agent({ agents: [a, b, c] })`, **not** a nested tree like `Agent({ agents: [Agent({ agents: [a, b] }), c] })`. The implementation must check if the left-hand agent already has `strategy: 'sequential'` and merge the sub-agents array.

### 7.5 Swarm Strategy Note

**Transfer tool auto-generation (base spec §14.15):** When `strategy: 'swarm'` is used, the server automatically generates `transfer_to_{agent_name}` tools during compilation. SDKs must **NOT** manually add these transfer tools — the server handles it. The SDK only needs to set `strategy: 'swarm'` in the AgentConfig.

### 7.6 scatter_gather

```typescript
export function scatterGather(options: {
  name: string;
  model: string;
  instructions?: string;
  workers: Agent[];
  coordinatorInstructions?: string;
}): Agent;
```

`scatterGather()` is syntactic sugar for creating a coordinator agent that dispatches parallel research workers. It produces an agent with `strategy: 'parallel'` and a coordinator sub-agent. The coordinator's instructions describe how to split work across workers and aggregate results.

---

## 8. Credentials

### 8.1 Credential Resolution Flow

1. Tool declares credentials in config
2. Server mints scoped execution token at execution start
3. Worker extracts token from `__agentspan_ctx__` in task input
4. Worker calls `POST /api/credentials/resolve` with token + credential names
5. Resolved values injected into execution context

### 8.2 Isolation Modes

| Mode | Behavior |
|------|----------|
| Isolated (default) | Credentials set as `process.env` vars, cleaned up after |
| In-process (`isolated: false`) | Available via `getCredential(name)` |
| HTTP header | Server substitutes `${NAME}` in headers |
| MCP | Passed to MCP server connection config |
| CLI | Injected into CLI tool env |
| Framework passthrough | Injected into `process.env` for framework execution |

### 8.3 API

```typescript
// In-process credential access
export async function getCredential(name: string): Promise<string>;

// Bulk resolution (for external workers)
export async function resolveCredentials(
  inputData: Record<string, unknown>,
  names: string[]
): Promise<Record<string, string>>;
```

### 8.4 Error Types

```typescript
CredentialNotFoundError    // credential doesn't exist in store
CredentialAuthError        // execution token invalid/expired
CredentialRateLimitError   // 120 calls/min exceeded
CredentialServiceError     // server error
```

---

## 9. Callbacks

### 9.1 CallbackHandler

```typescript
export abstract class CallbackHandler {
  onAgentStart?(agentName: string, prompt: string): Promise<void>;
  onAgentEnd?(agentName: string, result: unknown): Promise<void>;
  onModelStart?(agentName: string, messages: unknown[]): Promise<void>;
  onModelEnd?(agentName: string, response: unknown): Promise<void>;
  onToolStart?(agentName: string, toolName: string, args: unknown): Promise<void>;
  onToolEnd?(agentName: string, toolName: string, result: unknown): Promise<void>;
}
```

### 9.2 Wire Format

Each implemented method registers as a Conductor SIMPLE worker:

| Method | Wire Position | Task Name |
|--------|--------------|-----------|
| `onAgentStart` | `before_agent` | `{agentName}_before_agent` |
| `onAgentEnd` | `after_agent` | `{agentName}_after_agent` |
| `onModelStart` | `before_model` | `{agentName}_before_model` |
| `onModelEnd` | `after_model` | `{agentName}_after_model` |
| `onToolStart` | `before_tool` | `{agentName}_before_tool` |
| `onToolEnd` | `after_tool` | `{agentName}_after_tool` |

---

## 10. Code Execution

### 10.1 CodeExecutor (Abstract)

```typescript
export abstract class CodeExecutor {
  abstract execute(code: string, language?: string): Promise<ExecutionResult>;
  asTool(name?: string): ToolDef;
}

export interface ExecutionResult {
  output: string;
  error: string;
  exitCode: number;
  timedOut: boolean;
  readonly success: boolean;  // exitCode === 0 && !timedOut
}
```

### 10.2 Implementations

| Class | Description | Config |
|-------|-------------|--------|
| `LocalCodeExecutor` | Subprocess execution | `{ timeout: 30 }` |
| `DockerCodeExecutor` | Docker container | `{ image, timeout, memoryLimit }` |
| `JupyterCodeExecutor` | Jupyter kernel | `{ kernelName, timeout }` |
| `ServerlessCodeExecutor` | Remote function | `{ endpoint, timeout, headers }` |

### 10.3 Agent-Level Config

```typescript
export interface CodeExecutionConfig {
  enabled: boolean;
  allowedLanguages?: string[];   // default: ['python']
  allowedCommands?: string[];
  timeout?: number;              // default: 30
}

export interface CliConfig {
  enabled: boolean;
  allowedCommands?: string[];    // e.g., ['git', 'gh']
  timeout?: number;              // default: 30
  allowShell?: boolean;          // default: false
}
```

---

## 11. Execution API

### 11.1 AgentRuntime

```typescript
export class AgentRuntime {
  constructor(options?: {
    serverUrl?: string;
    apiKey?: string;
    authKey?: string;
    authSecret?: string;
    logLevel?: 'DEBUG' | 'INFO' | 'WARN' | 'ERROR';
    workerPollIntervalMs?: number;
  });

  // Execute and block until done
  async run(agent: unknown, prompt: string, options?: RunOptions): Promise<AgentResult>;

  // Fire-and-forget — returns handle immediately
  async start(agent: unknown, prompt: string, options?: RunOptions): Promise<AgentHandle>;

  // Stream events as they happen
  async stream(agent: unknown, prompt: string, options?: RunOptions): Promise<AgentStream>;

  // Compile + register agent (no execution)
  async deploy(agent: unknown): Promise<DeploymentInfo>;

  // Compile-only dry-run preview
  async plan(agent: unknown): Promise<object>;

  // Start worker serve loop (blocking — keeps process alive for external agent execution)
  async serve(): Promise<void>;

  // Stop all workers
  async shutdown(): Promise<void>;
}
```

**Note:** The `agent` parameter is typed as `unknown` — the runtime calls `detectFramework(agent)` internally to determine the execution path. Native `Agent` instances take the standard path; framework objects take the passthrough path.

### 11.2 RunOptions

```typescript
export interface RunOptions {
  sessionId?: string;
  media?: string[];
  idempotencyKey?: string;
  timeoutSeconds?: number;
  signal?: AbortSignal;         // Cancellation/timeout
}
```

### 11.3 AgentHandle

```typescript
export interface AgentHandle {
  readonly executionId: string;
  readonly correlationId: string;   // Auto-generated UUID per run/start/stream call (base spec §14.8)

  getStatus(): Promise<AgentStatus>;
  wait(pollIntervalMs?: number): Promise<AgentResult>;  // TS-specific convenience: poll until terminal
  respond(output: unknown): Promise<void>;  // General-purpose HITL response (arbitrary output)
  approve(output?: unknown): Promise<void>; // Shorthand: respond({ approved: true, ...output })
  reject(reason?: string): Promise<void>;   // Shorthand: respond({ approved: false, reason })
  send(message: string): Promise<void>;     // Shorthand: respond({ message })
  pause(): Promise<void>;
  resume(): Promise<void>;
  cancel(reason?: string): Promise<void>;
  stream(): Promise<AgentStream>;
}
```

### 11.4 AgentStream

```typescript
export class AgentStream implements AsyncIterable<AgentEvent> {
  readonly executionId: string;
  readonly events: AgentEvent[];

  // HITL methods
  async respond(output: unknown): Promise<void>;         // General-purpose
  async approve(output?: unknown): Promise<void>;        // Shorthand
  async reject(reason?: string): Promise<void>;          // Shorthand
  async send(message: string): Promise<void>;            // Shorthand

  // Drain stream and build result
  async getResult(): Promise<AgentResult>;

  // AsyncIterable implementation with SSE reconnection
  [Symbol.asyncIterator](): AsyncIterator<AgentEvent>;
}
```

### 11.5 Singleton Convenience Functions

```typescript
export type AgentRuntimeOptions = ConstructorParameters<typeof AgentRuntime>[0];

export function configure(options: AgentRuntimeOptions): void;
export async function run(agent: unknown, prompt: string, options?: RunOptions): Promise<AgentResult>;
export async function start(agent: unknown, prompt: string, options?: RunOptions): Promise<AgentHandle>;
export async function stream(agent: unknown, prompt: string, options?: RunOptions): Promise<AgentStream>;
export async function deploy(agent: unknown): Promise<DeploymentInfo>;
export async function plan(agent: unknown): Promise<object>;
export async function serve(): Promise<void>;    // Blocking — keeps process alive for worker polling
export async function shutdown(): Promise<void>;
```

All use a lazily-initialized singleton `AgentRuntime`.

---

## 12. Streaming Implementation

### 12.1 SSE Client (Node.js — fetch + ReadableStream)

Uses native `fetch` with custom headers (supports `Authorization` which native `EventSource` does not).

**Parsing:**
1. Connect to `GET /agent/stream/{executionId}` with `Accept: text/event-stream`
2. Read `ReadableStream` chunks, buffer partial lines
3. Parse SSE fields: `event:`, `id:`, `data:`
4. Blank line → dispatch event
5. `:` prefix lines → heartbeat (keep-alive, not a real event)

**Reconnection:**
- On connection drop: reconnect with `Last-Event-ID: {lastId}` header
- Max 5 retries with exponential backoff (1s, 2s, 4s, 8s, 16s)
- Server replays missed events from buffer (200 events, 5-min retention)

**Fallback:**
- If no real events for 15 seconds (only heartbeats): switch to polling
- Poll `GET /agent/{id}/status` every 500ms
- Emit synthetic `done` event when `isComplete` is true

### 12.2 Browser EventSource Wrapper

For browser environments, wrap native `EventSource` with the same `AgentStream` interface:

```typescript
function createBrowserSSEStream(url: string): AsyncIterable<AgentEvent>;
```

Registers listeners for all `EventType` values, queues events, and exposes as `AsyncIterator`.

---

## 13. Worker System

### 13.1 WorkerManager

Raw `fetch`-based task polling, replacing `@io-orkes/conductor-javascript`.

```typescript
export class WorkerManager {
  constructor(options: {
    serverUrl: string;
    headers: Record<string, string>;
    pollIntervalMs: number;
  });

  // Register a worker for a task type
  addWorker(taskName: string, handler: WorkerHandler): void;

  // Register Conductor task definition
  async registerTaskDef(taskName: string, config?: TaskDefConfig): Promise<void>;

  // Start/stop polling
  startPolling(): void;
  stopPolling(): void;
}
```

### 13.2 Task Polling Loop

```typescript
// Per-worker polling via setInterval
const poller = setInterval(async () => {
  const task = await pollTask(serverUrl, taskType, headers);
  if (!task) return;
  try {
    const result = await handler(task.inputData);
    await reportSuccess(task.taskId, task.workflowInstanceId, result);
  } catch (err) {
    await reportFailure(task.taskId, task.workflowInstanceId, err);
  }
}, pollIntervalMs);
```

### 13.3 Task Definition Registration

```typescript
// POST /api/metadata/taskdefs
{
  name: taskName,
  retryCount: 2,
  retryLogic: 'LINEAR_BACKOFF',
  retryDelaySeconds: 2,
  timeoutSeconds: 120,        // 600 for framework passthrough
  responseTimeoutSeconds: 120  // 600 for framework passthrough
}
```

### 13.4 Type Coercion Rules

Applied to tool input values from Conductor's type system (per base spec §14.1):

1. Null/empty → return unchanged
2. Optional unwrapping → recurse
3. Type match → short-circuit
4. String → object/array via `JSON.parse()` (silent fallback)
5. Object/array → string via `JSON.stringify()`
6. String → number/boolean via conversion
7. Fallback → return unchanged

**All coercion failures are silent** — return original value, never throw.

### 13.5 Circuit Breaker

Per base spec §14.2: 10 consecutive failures → tool disabled. Reset on any success. Manual reset via `resetCircuitBreaker(toolName)`.

### 13.6 Worker Naming Conventions

Per base spec §14.3 — all names are collected recursively through nested agents:

| Worker Type | Name Pattern |
|-------------|-------------|
| Tool | `{tool.name}` |
| Tool guardrail | `{guardrail.name}` |
| Output guardrail | `{agentName}_output_guardrail` |
| stop_when | `{agentName}_stop_when` |
| Gate | `{agentName}_gate` |
| check_transfer | `{agentName}_check_transfer` |
| Router function | `{agentName}_router_fn` |
| Handoff check | `{agentName}_handoff_check` |
| Manual selection | `{agentName}_process_selection` |
| Callback | `{agentName}_{position}` |

---

## 14. Framework Integration

### 14.1 Detection

```typescript
export type FrameworkId = 'vercel_ai' | 'langgraph' | 'langchain' | 'openai' | 'google_adk';

export function detectFramework(agent: unknown): FrameworkId | null {
  // Native agentspan Agent — not a framework
  if (agent instanceof Agent) return null;

  // Vercel AI SDK: ToolLoopAgent has .generate() + .stream() + .tools
  if (hasGenerateAndStreamAndTools(agent)) return 'vercel_ai';

  // LangGraph.js: CompiledStateGraph has .invoke() + .getGraph() or .nodes
  if (hasInvokeAndGetGraph(agent)) return 'langgraph';

  // LangChain.js: AgentExecutor/Runnable has .invoke() + .lc_namespace
  if (hasInvokeAndLcNamespace(agent)) return 'langchain';

  // OpenAI Agents: has .run() + .tools + .model with OpenAI markers
  if (hasRunAndOpenAIMarkers(agent)) return 'openai';

  // Google ADK: has .run() + .model with Google/ADK markers
  if (hasRunAndADKMarkers(agent)) return 'google_adk';

  return null;
}
```

All detection uses duck-typing — checks for method/property signatures without importing framework packages. This ensures the SDK works without any framework installed.

### 14.2 Passthrough Architecture

All five frameworks follow the same pattern:

```
runtime.run(frameworkAgent, prompt)
  │
  ├─ detectFramework(agent) → frameworkId
  │
  ├─ makeFrameworkWorker(agent, frameworkId, name, serverUrl, headers)
  │   └─ Returns: (task: ConductorTask) → TaskResult
  │
  ├─ registerPassthroughWorker(name, workerFn, timeout=600)
  │
  ├─ POST /api/agent/start { framework: frameworkId, rawConfig: { name, _worker_name }, prompt }
  │
  └─ Server: Normalizer → AgentConfig { _framework_passthrough: true }
     → Compiler → WorkflowDef { tasks: [SIMPLE(_fw_task)] }
     → Conductor executes → Worker polls → Framework runs → Events pushed → Result
```

### 14.3 Per-Framework Worker Factories

#### Vercel AI SDK

```typescript
function makeVercelAIWorker(
  agent: VercelAIAgent,
  name: string,
  serverUrl: string,
  headers: Record<string, string>
): WorkerFunction {
  return async (task: ConductorTask) => {
    const executionId = task.workflowInstanceId;
    const prompt = task.inputData.prompt ?? '';

    const result = await agent.generate({
      prompt,
      onStepFinish: ({ text, toolCalls, toolResults }) => {
        if (toolCalls?.length) {
          for (const tc of toolCalls) {
            pushEvent(executionId, { type: 'tool_call', toolName: tc.toolName, args: tc.args }, serverUrl, headers);
          }
        }
        if (toolResults?.length) {
          for (const tr of toolResults) {
            pushEvent(executionId, { type: 'tool_result', toolName: tr.toolName, result: tr.result }, serverUrl, headers);
          }
        }
        if (text) {
          pushEvent(executionId, { type: 'thinking', content: text }, serverUrl, headers);
        }
      },
    });

    return { status: 'COMPLETED', outputData: { result: result.text } };
  };
}
```

#### LangGraph.js

```typescript
function makeLangGraphWorker(graph, name, serverUrl, headers): WorkerFunction {
  return async (task) => {
    const prompt = task.inputData.prompt ?? '';
    const input = buildLangGraphInput(graph, prompt);
    const config = task.inputData.session_id
      ? { configurable: { thread_id: task.inputData.session_id } }
      : {};

    let finalState: unknown;
    for await (const [mode, chunk] of graph.stream(input, { ...config, streamMode: ['updates', 'values'] })) {
      if (mode === 'updates') {
        processUpdatesChunk(chunk, task.workflowInstanceId, serverUrl, headers);
      } else if (mode === 'values') {
        finalState = chunk;
      }
    }

    return { status: 'COMPLETED', outputData: { result: extractOutput(finalState) } };
  };
}
```

#### LangChain.js

```typescript
function makeLangChainWorker(executor, name, serverUrl, headers): WorkerFunction {
  return async (task) => {
    const prompt = task.inputData.prompt ?? '';
    const handler = new AgentspanCallbackHandler(task.workflowInstanceId, serverUrl, headers);
    const result = await executor.invoke({ input: prompt }, { callbacks: [handler] });
    const output = typeof result === 'object' ? result.output ?? result : String(result);
    return { status: 'COMPLETED', outputData: { result: output } };
  };
}
```

#### OpenAI Agents SDK / Google ADK

Follow the same pattern — invoke the framework's `.run()` method, capture events via callbacks or streaming, push events to SSE, return result.

### 14.4 Non-Blocking Event Push

Shared utility used by all framework workers:

```typescript
// frameworks/event-push.ts
export function pushEvent(
  executionId: string,
  event: object,
  serverUrl: string,
  headers: Record<string, string>
): void {
  // Fire-and-forget — do not await
  fetch(`${serverUrl}/agent/${executionId}/events`, {
    method: 'POST',
    headers: { ...headers, 'Content-Type': 'application/json' },
    body: JSON.stringify([event]),
  }).catch(err => {
    // Log at debug level only — do not block graph execution
  });
}
```

**Supported event types** (per base spec §14.7): `thinking`, `tool_call`, `tool_result`, `context_condensed`, `subagent_start`, `subagent_stop`. Unknown types are silently dropped by the server.

### 14.5 Server-Side Requirements

The server needs normalizers for each framework. For TypeScript SDK:

| Normalizer | Framework | Behavior |
|-----------|-----------|----------|
| `VercelAINormalizer` | `vercel_ai` | **New** — produces passthrough AgentConfig |
| `LangGraphNormalizer` | `langgraph` | **Exists** — reused from Python SDK |
| `LangChainNormalizer` | `langchain` | **Exists** — reused from Python SDK |
| `OpenAINormalizer` | `openai` | **Exists or new** |
| `GoogleADKNormalizer` | `google_adk` | **Exists or new** |

All passthrough normalizers produce the same structure:
```json
{
  "name": "<agent_name>",
  "metadata": { "_framework_passthrough": true },
  "tools": [{ "name": "<worker_name>", "toolType": "worker" }]
}
```

---

## 15. Extended Types

### 15.1 UserProxyAgent

Human stand-in for multi-agent conversations.

```typescript
export class UserProxyAgent extends Agent {
  constructor(options: {
    name: string;
    mode: 'ALWAYS' | 'TERMINATE' | 'NEVER';
    instructions?: string;
  });
}
```

- `ALWAYS` — always pause for human input
- `TERMINATE` — pause only on termination condition
- `NEVER` — auto-respond (useful for testing)

### 15.2 GPTAssistantAgent

Wraps OpenAI Assistants API.

```typescript
export class GPTAssistantAgent extends Agent {
  constructor(options: {
    name: string;
    assistantId: string;
    model?: string;
    instructions?: string;
  });
}
```

### 15.3 Agent Discovery

```typescript
export async function discoverAgents(path: string): Promise<Agent[]>;
```

Scans a directory for files exporting `Agent` instances.

### 15.4 OpenTelemetry Tracing

```typescript
export function isTracingEnabled(): boolean;
// SDK emits spans for: run/start/stream, tool execution, SSE connection
// Requires user to configure OTel SDK separately
```

---

## 16. Error Handling

### 16.1 Error Hierarchy

```typescript
export class AgentspanError extends Error {
  constructor(message: string, public readonly cause?: Error);
}

export class AgentAPIError extends AgentspanError {
  constructor(message: string, public readonly statusCode?: number, public readonly responseBody?: string);
}

export class AgentNotFoundError extends AgentspanError {
  constructor(public readonly agentName: string);
}

export class ConfigurationError extends AgentspanError {}

export class CredentialNotFoundError extends AgentspanError {
  constructor(public readonly credentialName: string);
}

export class CredentialAuthError extends AgentspanError {}
export class CredentialRateLimitError extends AgentspanError {}
export class CredentialServiceError extends AgentspanError {}
export class SSETimeoutError extends AgentspanError {}

export class GuardrailFailedError extends AgentspanError {
  constructor(public readonly guardrailName: string, public readonly failureMessage: string);
}
```

### 16.2 AbortSignal Support

All network operations accept `AbortSignal` for timeout/cancellation:

```typescript
// Timeout via AbortSignal.timeout() (Node 18+)
const result = await runtime.run(agent, prompt, {
  signal: AbortSignal.timeout(60_000),
});

// Manual abort
const controller = new AbortController();
setTimeout(() => controller.abort(), 60_000);
const result = await runtime.run(agent, prompt, { signal: controller.signal });
```

---

## 17. Testing Framework

### 17.1 mockRun()

Execute an agent without connecting to the server:

```typescript
export async function mockRun(
  agent: Agent,
  prompt: string,
  options?: {
    mockTools?: Record<string, (args: unknown) => unknown | Promise<unknown>>;
    mockCredentials?: Record<string, string>;
    sessionId?: string;
  }
): Promise<AgentResult>;
```

### 17.2 expectResult() — Fluent Assertions

```typescript
export function expectResult(result: AgentResult): ResultExpectation;

interface ResultExpectation {
  toBeCompleted(): this;
  toBeFailed(): this;
  toContainOutput(text: string): this;
  toHaveUsedTool(toolName: string): this;
  toHavePassedGuardrail(guardrailName: string): this;
  toHaveFinishReason(reason: FinishReason): this;
  toHaveTokenUsageBelow(maxTokens: number): this;
}
```

### 17.3 Individual Assertions

```typescript
export function assertToolUsed(result: AgentResult, toolName: string): void;
export function assertGuardrailPassed(result: AgentResult, guardrailName: string): void;
export function assertAgentRan(result: AgentResult, agentName: string): void;
export function assertHandoffTo(result: AgentResult, targetAgent: string): void;
export function assertStatus(result: AgentResult, status: Status): void;
export function assertNoErrors(result: AgentResult): void;
```

### 17.4 record() / replay()

```typescript
export async function record(
  agent: Agent,
  prompt: string,
  options: { fixturePath: string }
): Promise<AgentResult>;

export async function replay(fixturePath: string): Promise<AgentResult>;
```

### 17.5 Strategy Validation

```typescript
export function validateStrategy(agent: Agent, expectedStrategy: Strategy): void;
```

### 17.6 LLM Judge (CorrectnessEval)

```typescript
export class CorrectnessEval {
  constructor(options: { model: string; maxOutputChars?: number; maxTokens?: number });

  async evaluate(
    result: AgentResult,
    options: {
      rubrics: Record<string, number>;  // rubric name → weight (must sum to 1.0)
      passThreshold?: number;            // default: 3.5 out of 5
    }
  ): Promise<EvalResult>;
}

interface EvalResult {
  passed: boolean;
  scores: Record<string, number>;       // rubric → score (1-5)
  weightedAverage: number;
  reasoning: Record<string, string>;     // rubric → judge reasoning
}
```

---

## 18. Validation Framework

### 18.1 Runner (CLI)

```bash
pnpm run validate                          # Run all
pnpm run validate -- --run openai          # Run subset
pnpm run validate -- --group SMOKE_TEST    # Run group
pnpm run validate -- --dry-run             # Preview
pnpm run validate -- --judge               # With LLM judge
pnpm run validate -- --report              # Generate HTML report
pnpm run validate -- --resume              # Resume failed runs
```

### 18.2 TOML Configuration

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
model = "anthropic/claude-sonnet-4-5"
group = "SMOKE_TEST"
timeout = 300
```

### 18.3 HTML Report

Interactive dashboard with:
- Score heatmap (model × rubric)
- Pass/fail status per run
- Expandable details per example
- Filter by group, model, status

---

## 19. Serialization

### 19.1 AgentConfig JSON

The serializer recursively converts an `Agent` tree to the wire format defined in base spec §3:

```typescript
export class AgentConfigSerializer {
  serialize(agent: Agent): object;           // Full payload for POST /agent/start
  serializeAgent(agent: Agent): object;      // AgentConfig subtree
  serializeTool(tool: ToolDef): object;      // ToolConfig
  serializeGuardrail(guard: GuardrailDef): object;
  serializeTermination(cond: TerminationCondition): object;
  serializeHandoff(handoff: HandoffCondition): object;
}
```

### 19.2 Key Rules (per base spec §3)

- All keys are **camelCase**
- Omit keys with `null`/`undefined` values
- Recursive: `agents` array contains nested AgentConfig objects
- `strategy` is only set when `agents` is non-empty
- Zod schemas converted to JSON Schema at serialization time
- `outputType` includes both `schema` and `className`
- `sessionId` is always present (empty string if not provided)
- `media` is always present (empty array if not provided)

### 19.3 Framework Serialization

For framework agents, the serializer produces:
```json
{
  "framework": "vercel_ai",
  "rawConfig": { "name": "my_agent", "_worker_name": "my_agent" },
  "prompt": "user input",
  "sessionId": ""
}
```

---

## 20. Configuration

### 20.1 Environment Variables

Per base spec §2.3:

| Variable | Default | Description |
|----------|---------|-------------|
| `AGENTSPAN_SERVER_URL` | `http://localhost:6767/api` | Server API URL |
| `AGENTSPAN_API_KEY` | — | Bearer token / API key |
| `AGENTSPAN_AUTH_KEY` | — | Legacy auth key |
| `AGENTSPAN_AUTH_SECRET` | — | Legacy auth secret |
| `AGENTSPAN_LLM_RETRY_COUNT` | `3` | LLM call retry count |
| `AGENTSPAN_WORKER_POLL_INTERVAL` | `100` | Worker poll interval (ms) |
| `AGENTSPAN_WORKER_THREADS` | `1` | Concurrent executions per worker |
| `AGENTSPAN_AUTO_START_WORKERS` | `true` | Auto-start workers on first run |
| `AGENTSPAN_AUTO_START_SERVER` | `true` | Auto-start local server |
| `AGENTSPAN_DAEMON_WORKERS` | `true` | Kill workers on exit |
| `AGENTSPAN_STREAMING_ENABLED` | `true` | Enable SSE streaming |
| `AGENTSPAN_CREDENTIAL_STRICT_MODE` | `false` | No env var fallback |
| `AGENTSPAN_INTEGRATIONS_AUTO_REGISTER` | `false` | Auto-register LLM integrations |
| `AGENTSPAN_LOG_LEVEL` | `INFO` | DEBUG / INFO / WARN / ERROR |

### 20.2 URL Normalization

If `serverUrl` does not end with `/api`, append it automatically.

---

## 21. Implementation Order

Per base spec §12, with TypeScript-specific additions:

1. **Configuration** — `config.ts`, env vars, URL normalization
2. **Types** — `types.ts`, all interfaces and enums
3. **Errors** — `errors.ts`, full hierarchy
4. **HTTP client** — fetch wrappers for all REST endpoints
5. **Agent + Tool** — `agent.ts`, `tool.ts` (superset: Zod + JSON Schema + AI SDK detection)
6. **Serialization** — `serializer.ts`, AgentConfig JSON generation
7. **Worker system** — `worker.ts`, raw fetch polling + type coercion + circuit breaker
8. **Runtime** — `runtime.ts`, run/start/deploy/plan/shutdown
9. **SSE streaming** — `stream.ts`, AgentStream with reconnection + polling fallback
10. **Credentials** — `credentials.ts`, resolve, inject, isolation modes
11. **Guardrails** — `guardrail.ts`, all 4 types + OnFail modes
12. **Memory** — `memory.ts`, ConversationMemory + SemanticMemory + InMemoryStore
13. **Termination + Handoffs** — `termination.ts`, `handoff.ts`, composable conditions
14. **Callbacks** — `callback.ts`, 6-position lifecycle hooks
15. **Code execution** — `code-execution.ts`, all 4 executors + asTool()
16. **Extended types** — `ext.ts`, UserProxyAgent + GPTAssistantAgent
17. **Framework integration** — `frameworks/`, detection + 5 worker factories + event push
18. **Testing framework** — `testing/`, mockRun + expect + assertions + record/replay + eval
19. **Validation framework** — `validation/`, runner + judge + report
20. **Kitchen sink** — `examples/kitchen-sink.ts`, full 89-feature acceptance test
21. **Examples** — all numbered examples + per-framework examples

---

## 22. Kitchen Sink Acceptance Test

The kitchen sink (`examples/kitchen-sink.ts`) exercises all 89 features from the traceability matrix in a single mega-pipeline — a content publishing pipeline processing an article through 9 stages.

Per `docs/sdk-design/kitchen-sink.md`, the SDK passes when:

1. **Wire format parity** — produces identical AgentConfig JSON for the same agent tree
2. **Worker execution** — all tool/guardrail/callback workers execute successfully
3. **SSE streaming** — same event sequence (types + order) as Python SDK
4. **HITL parity** — approve, reject, send all work correctly
5. **Result structure** — `AgentResult` matches expected fields and types
6. **Structural tests pass** — all assertions in unit tests
7. **Judge scores** — LLM judge >= 3.5 on all rubrics
8. **Validation framework** — runner produces HTML report with passing results

---

## 23. Success Criteria

The TypeScript SDK v1.0 is complete when:

1. All 89 features in the traceability matrix are implemented
2. Kitchen sink produces identical AgentConfig JSON as Python SDK
3. Kitchen sink executes successfully against a running server
4. All unit tests pass (52+ test files)
5. All integration tests pass
6. LLM judge scores >= 3.5 on all rubrics
7. Validation framework runs with HTML report
8. Framework passthrough works for all 5 frameworks (Vercel AI SDK, LangGraph.js, LangChain.js, OpenAI Agents, Google ADK)
9. Superset tool compatibility works (Zod, JSON Schema, AI SDK tools in same agent)
10. Published to npm as `@agentspan/sdk` v1.0.0
11. Documentation covers all public APIs with examples

---

## 24. Addendum: Implementation Details

This section documents critical implementation details required for correctness. These supplement the base spec's addendum (§14) with TypeScript-specific details.

### 24.1 Feature Traceability

The full 89-feature traceability matrix lives in the base spec (§11). This TypeScript SDK implements all 89 features. The TypeScript module mapping follows the directory layout in §2.3. For quick reference:

| Feature Group | TS Module | Feature #s |
|--------------|-----------|------------|
| Agent definition | `agent.ts` | #1, #30, #37-39, #63, #67-72 |
| Strategies | `agent.ts` | #2-9, #76 |
| Tools | `tool.ts` | #10-16, #17, #19-21, #89 |
| ToolContext | `worker.ts` | #18 |
| Guardrails | `guardrail.ts` | #20, #22-29 |
| Memory | `memory.ts` | #31-32 |
| Termination | `termination.ts` | #33 |
| Handoffs | `handoff.ts` | #34-36 |
| HITL | `result.ts`, `stream.ts` | #40-42 |
| Streaming | `stream.ts` | #43-45 |
| Execution | `runtime.ts` | #46-51 |
| Credentials | `credentials.ts` | #52-57 |
| Code execution | `code-execution.ts` | #58-61 |
| Callbacks | `callback.ts` | #62 |
| Extended types | `ext.ts` | #65-66 |
| Discovery/tracing | `discovery.ts`, `tracing.ts` | #74-75 |
| Testing | `testing/` | #78-83 |
| Validation | `validation/` | #84-87 |
| External agent | `agent.ts` | #88 |

### 24.2 @Agent Decorator

In addition to `@Tool` and `@Guardrail`, the SDK provides an `@AgentDec` decorator for class-based agent definitions:

```typescript
import { AgentDec } from '@agentspan/sdk';

class Classifiers {
  @AgentDec({ name: 'tech_classifier', model: 'openai/gpt-4o' })
  techClassifier(prompt: string): string { return ''; }

  @AgentDec({ name: 'business_classifier', model: 'openai/gpt-4o' })
  businessClassifier(prompt: string): string { return ''; }
}

// Extract decorated methods as Agent instances
const agents = agentsFrom(new Classifiers());
```

Functional equivalent:
```typescript
const techClassifier = agent(() => '', { name: 'tech_classifier', model: 'openai/gpt-4o' });
```

### 24.3 Status Type Clarification

The `Status` type represents **terminal** execution states only:

```typescript
export type Status = 'COMPLETED' | 'FAILED' | 'TERMINATED' | 'TIMED_OUT';
```

The `AgentStatus.status` field (returned by `getStatus()`) is typed as `string` and may contain non-terminal values from Conductor: `'RUNNING'`, `'PAUSED'`, `'PENDING'`. The boolean flags (`isComplete`, `isRunning`, `isWaiting`) are the preferred way to check state.

### 24.4 Execution Token Extraction

Workers must extract the execution token from task input using a two-level fallback path (base spec §14.16):

```typescript
function extractExecutionToken(task: ConductorTask): string | null {
  // Primary: from task input
  const ctx = task.inputData?.['__agentspan_ctx__'] as Record<string, unknown> | undefined;
  if (ctx?.executionToken) return ctx.executionToken as string;

  // Fallback: from workflow input (for sub-agents in Conductor SUB_WORKFLOW)
  const wfCtx = task.workflowInput?.['__agentspan_ctx__'] as Record<string, unknown> | undefined;
  if (wfCtx?.executionToken) return wfCtx.executionToken as string;

  return null;
}
```

### 24.5 Idempotency Semantics (base spec §14.5)

When `RunOptions.idempotencyKey` is provided:
1. Maps to Conductor's `correlationId` in the start request
2. Server searches for existing execution with same agent name + correlationId
3. Search scope: **RUNNING or COMPLETED** executions only (not FAILED)
4. If found: returns existing `executionId` without re-execution
5. If not found: creates new execution with `correlationId = idempotencyKey`

Failed executions are NOT deduplicated — a new execution is always created.

`AgentHandle.correlationId` is auto-generated as a UUID for every `run()`/`start()`/`stream()` call (base spec §14.8).

### 24.6 required_tools Enforcement (base spec §14.10)

When `AgentOptions.requiredTools` is set, the server wraps the agent's loop in an outer DO_WHILE with up to 3 iterations, checking after each iteration whether all required tools were called. This can **triple execution time** in worst case. Document this performance implication in examples.

### 24.7 Tool Constructor Full Signatures

Detailed option interfaces for all server-side tool constructors:

```typescript
// httpTool
interface HttpToolOptions {
  name: string;
  description: string;
  url: string;
  method?: 'GET' | 'POST' | 'PUT' | 'DELETE' | 'PATCH';  // default: 'GET'
  headers?: Record<string, string>;       // supports ${CREDENTIAL_NAME} substitution
  inputSchema?: object | ZodSchema;
  accept?: string[];                       // default: ['application/json']
  contentType?: string;                    // default: 'application/json'
  credentials?: (string | CredentialFile)[];
}

// apiTool (auto-discover from OpenAPI/Swagger/Postman spec)
interface ApiToolOptions {
  url: string;                             // Spec URL or base URL
  name?: string;
  description?: string;
  headers?: Record<string, string>;
  toolNames?: string[];                    // Filter to specific operations
  maxTools?: number;                       // default: 64 (LLM selects if exceeded)
  credentials?: (string | CredentialFile)[];
}

// mcpTool
interface McpToolOptions {
  serverUrl: string;
  name?: string;
  description?: string;
  headers?: Record<string, string>;
  toolNames?: string[];                    // Filter to specific tools
  maxTools?: number;                       // default: 64
  credentials?: (string | CredentialFile)[];
}

// agentTool
interface AgentToolOptions {
  name?: string;
  description?: string;
  retryCount?: number;
  retryDelaySeconds?: number;
  optional?: boolean;                      // If true, failure doesn't fail parent
}
function agentTool(agent: Agent, options?: AgentToolOptions): ToolDef;

// humanTool
interface HumanToolOptions {
  name: string;
  description: string;
  inputSchema?: object | ZodSchema;
}

// imageTool
interface ImageToolOptions {
  name: string;
  description: string;
  llmProvider: string;
  model: string;
  inputSchema?: object | ZodSchema;
  style?: string;
  size?: string;
}

// audioTool
interface AudioToolOptions {
  name: string;
  description: string;
  llmProvider: string;
  model: string;
  inputSchema?: object | ZodSchema;
  voice?: string;
  speed?: number;
  format?: string;
}

// videoTool
interface VideoToolOptions {
  name: string;
  description: string;
  llmProvider: string;
  model: string;
  inputSchema?: object | ZodSchema;
  duration?: number;
  resolution?: string;
  fps?: number;
  style?: string;
  aspectRatio?: string;
}

// pdfTool
interface PdfToolOptions {
  name?: string;                           // default: 'generate_pdf'
  description?: string;
  inputSchema?: object | ZodSchema;
  pageSize?: string;
  theme?: string;
  fontSize?: number;
}

// searchTool (RAG)
interface SearchToolOptions {
  name: string;
  description: string;
  vectorDb: string;
  index: string;
  embeddingModelProvider: string;
  embeddingModel: string;
  namespace?: string;                      // default: 'default_ns'
  maxResults?: number;                     // default: 5
  dimensions?: number;
  inputSchema?: object | ZodSchema;
}

// indexTool (RAG)
interface IndexToolOptions {
  name: string;
  description: string;
  vectorDb: string;
  index: string;
  embeddingModelProvider: string;
  embeddingModel: string;
  namespace?: string;                      // default: 'default_ns'
  chunkSize?: number;
  chunkOverlap?: number;
  dimensions?: number;
  inputSchema?: object | ZodSchema;
}
```

### 24.8 ToolFunction Type

The return type of `tool()`:

```typescript
// ToolFunction is the callable returned by tool()
// It's an async function with a hidden _toolDef property
export type ToolFunction<TInput = unknown, TOutput = unknown> =
  ((args: TInput, ctx?: ToolContext) => Promise<TOutput>) & {
    readonly _toolDef: ToolDef;
  };

// ToolDef is the serializable metadata
export interface ToolDef {
  name: string;
  description: string;
  inputSchema: object;            // Always JSON Schema (Zod converted at definition time)
  outputSchema?: object;
  toolType: ToolType;
  func?: Function;                // null for server-side tools and external tools
  approvalRequired?: boolean;
  timeoutSeconds?: number;
  external?: boolean;
  isolated?: boolean;
  credentials?: (string | CredentialFile)[];
  guardrails?: GuardrailDef[];
  config?: Record<string, unknown>;  // Tool-type-specific config (url, method, headers, etc.)
}
```

### 24.9 Agent Default Values

| Field | Default | Notes |
|-------|---------|-------|
| `maxTurns` | `25` | Max LLM call turns per agent |
| `timeoutSeconds` | `0` | 0 = no timeout |
| `temperature` | `null` | Use model default |
| `maxTokens` | `null` | Use model default |
| `external` | `false` | |
| `planner` | `false` | |
| `includeContents` | `null` | |
| `isolated` (tools) | `true` | Credentials in subprocess env vars |

### 24.10 Worker Configuration Defaults

| Setting | Default | Configurable via |
|---------|---------|-----------------|
| Poll interval | 100ms | `AGENTSPAN_WORKER_POLL_INTERVAL` or constructor |
| Thread count | 1 | `AGENTSPAN_WORKER_THREADS` or constructor |
| Task timeout | 120s | Per-tool `timeoutSeconds` or task def config |
| Framework task timeout | 600s | Hardcoded for passthrough workers |
| Retry count | 2 | Per task def |
| Retry delay | 2s | Per task def |
| Retry policy | LINEAR_BACKOFF | Per task def |
| Daemon mode | true | `AGENTSPAN_DAEMON_WORKERS` |

### 24.11 SSE Server-Only Events

The SSE stream may include server-only event types not in the `EventType` enum. The SDK must forward these to users as raw events (the `AgentEvent.type` field accepts `EventType | string` for this reason):

| Server-Only Type | Fields | Description |
|-----------------|--------|-------------|
| `context_condensed` | `content`, `trigger`, `messagesBefore`, `messagesAfter` | Context window condensation |
| `subagent_start` | `executionId`, `prompt` | Sub-agent execution started |
| `subagent_stop` | `executionId`, `result` | Sub-agent execution completed |

### 24.12 Gate Worker Response Format

Custom gate workers (registered via `gate()` function) must return:
```json
{ "decision": "continue" }
```
or
```json
{ "decision": "stop" }
```

The server reads the `decision` field to determine whether the next pipeline stage should execute.

### 24.13 Framework Peer Dependencies (Complete)

All framework packages in `peerDependenciesMeta`:

```json
{
  "peerDependencies": {
    "zod": "^3.22.0",
    "ai": "^4.0.0",
    "@langchain/core": "^0.3.0",
    "@langchain/langgraph": "^0.2.0",
    "@openai/agents": "^1.0.0",
    "@google/adk": "^1.0.0"
  },
  "peerDependenciesMeta": {
    "ai": { "optional": true },
    "@langchain/core": { "optional": true },
    "@langchain/langgraph": { "optional": true },
    "@openai/agents": { "optional": true },
    "@google/adk": { "optional": true }
  }
}
```

**Note:** `@openai/agents` and `@google/adk` package names are placeholders — use the actual npm package names when they stabilize. Detection uses duck-typing regardless.

### 24.14 Browser Support

The SDK targets Node.js 18+ as the primary runtime. Browser support is secondary:

- **SSE streaming**: In browsers, the SDK uses native `EventSource` API wrapped in the `AgentStream` interface. Limitation: native `EventSource` does not support custom headers (`Authorization`), so browser use requires either a proxy or cookie-based auth.
- **Worker polling**: Not applicable in browsers — workers are server-side only.
- **Tool execution**: Not applicable in browsers.

For browser-only use cases (consuming SSE streams, calling REST APIs), the HTTP client and SSE client modules work with browser `fetch` and `EventSource`. The `@agentspan/sdk` package marks Node.js-only modules (worker, credentials, code-execution) with a `node` export condition.
