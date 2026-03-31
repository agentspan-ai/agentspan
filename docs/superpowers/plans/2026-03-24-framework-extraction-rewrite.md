# Framework Extraction Rewrite — Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the passthrough pattern with real extraction — framework agents are introspected, decomposed into agentspan primitives (model, tools, instructions), and compiled into multi-task Conductor workflows.

**Architecture:** The TS SDK's generic serializer walks framework agent properties, extracts callables as `WorkerInfo` with `_worker_ref` markers, and sends `raw_config` to the server. Server normalizers (OpenAI, ADK, LangGraph, LangChain) map raw_config to AgentConfig. The compiler produces multi-task workflows (LLM_CHAT_COMPLETE + SIMPLE per tool). Vercel AI SDK is removed from detection — handled by superset tools + native Agent.

**Tech Stack:** TypeScript, Java (server normalizers), vitest, Gradle (server tests)

**Spec:** `docs/sdk-design/2026-03-23-multi-language-sdk-design.md` §5.3

---

## File Structure

| File | Action | Responsibility |
|------|--------|---------------|
| `sdk/typescript/src/frameworks/detect.ts` | Modify | Remove Vercel AI detection, keep 4 frameworks |
| `sdk/typescript/src/frameworks/serializer.ts` | Create | Generic deep serializer (port from Python) |
| `sdk/typescript/src/frameworks/langgraph-serializer.ts` | Create | LangGraph-specific extraction (full + graph-structure) |
| `sdk/typescript/src/frameworks/langchain-serializer.ts` | Create | LangChain-specific extraction |
| `sdk/typescript/src/frameworks/vercel-ai.ts` | Delete | No longer needed |
| `sdk/typescript/src/frameworks/openai-agents.ts` | Delete | Handled by generic serializer |
| `sdk/typescript/src/frameworks/google-adk.ts` | Delete | Handled by generic serializer |
| `sdk/typescript/src/frameworks/event-push.ts` | Delete | No passthrough = no direct event push |
| `sdk/typescript/src/runtime.ts` | Modify | Rewrite `_runFramework()` to use extraction → serialize → POST /start → register workers |
| `server/.../normalizer/VercelAINormalizer.java` | Modify | Rewrite from passthrough to real extraction (like OpenAINormalizer) |
| `sdk/typescript/examples/vercel-ai/*.ts` | Rewrite | Use native Agent with superset tools |
| `sdk/typescript/examples/openai/*.ts` | Rewrite | Pass real Agent, verify extraction produces multi-task workflow |
| `sdk/typescript/examples/adk/*.ts` | Rewrite | Pass real LlmAgent, verify extraction |
| `sdk/typescript/examples/langgraph/*.ts` | Rewrite | Pass real compiled graph, verify extraction |
| `sdk/typescript/examples/langchain/*.ts` | Rewrite | Pass real chain, verify extraction |
| `sdk/typescript/tests/unit/frameworks/serializer.test.ts` | Create | Generic serializer tests |
| `sdk/typescript/tests/unit/frameworks/detect.test.ts` | Modify | Remove Vercel AI tests |
| `sdk/typescript/tests/unit/frameworks/extraction-e2e.test.ts` | Create | E2E: framework agent → raw_config → verify structure |

---

## Chunk 1: Generic Serializer + Detection Cleanup

### Task 1: Remove Vercel AI from detection, clean up passthrough code

**Files:**
- Modify: `sdk/typescript/src/frameworks/detect.ts`
- Delete: `sdk/typescript/src/frameworks/vercel-ai.ts`
- Delete: `sdk/typescript/src/frameworks/event-push.ts`
- Delete: `sdk/typescript/src/frameworks/openai-agents.ts`
- Delete: `sdk/typescript/src/frameworks/google-adk.ts`
- Modify: `sdk/typescript/tests/unit/frameworks/detect.test.ts`

- [ ] **Step 1: Remove Vercel AI detection from detect.ts**

Remove `hasGenerateAndStreamAndTools()` and the Vercel AI check. Keep OpenAI, ADK, LangGraph, LangChain detection.

- [ ] **Step 2: Delete passthrough worker files**

Delete `vercel-ai.ts`, `event-push.ts`, `openai-agents.ts`, `google-adk.ts`. These contained `makeXWorker()` passthrough factories — no longer needed.

- [ ] **Step 3: Update detect.test.ts**

Remove Vercel AI detection tests. Keep OpenAI, ADK, LangGraph, LangChain tests.

- [ ] **Step 4: Update index.ts exports**

Remove exports for deleted modules. Add exports for new modules (serializer).

- [ ] **Step 5: Verify tests pass**

```bash
cd sdk/typescript && npx vitest run
```

- [ ] **Step 6: Commit**

```bash
git commit -m "refactor(ts-sdk): remove passthrough pattern, clean up framework detection"
```

### Task 2: Build generic deep serializer

**Files:**
- Create: `sdk/typescript/src/frameworks/serializer.ts`
- Create: `sdk/typescript/tests/unit/frameworks/serializer.test.ts`

- [ ] **Step 1: Write serializer.ts**

Port Python's `sdk/python/src/agentspan/agents/frameworks/serializer.py` to TypeScript. Key functions:

```typescript
export interface WorkerInfo {
  name: string;
  description: string;
  inputSchema: Record<string, unknown>;
  func: Function | null;
}

/**
 * Generic deep serializer. Walks object properties, extracts callables as WorkerInfo.
 * Returns (rawConfig, workers) tuple — same format as Python's serialize_agent().
 */
export function serializeFrameworkAgent(agentObj: unknown): [Record<string, unknown>, WorkerInfo[]];

/**
 * Check if an object is a tool-like callable that should be extracted as a worker.
 */
function isToolCallable(obj: unknown): boolean;

/**
 * Try to extract a tool wrapper object (has name + description + schema + callable).
 */
function tryExtractToolObject(obj: unknown): WorkerInfo | null;

/**
 * Try to detect an agent-as-tool wrapper and recursively serialize.
 */
function tryExtractAgentTool(obj: unknown): [Record<string, unknown>, WorkerInfo[]] | null;

/**
 * Extract name, description, JSON Schema from a callable function.
 */
function extractCallable(func: Function): WorkerInfo;

/**
 * Find an embedded function in an object's properties (up to 2 levels deep).
 */
function findEmbeddedFunction(obj: unknown, maxDepth?: number): Function | null;
```

The serializer walks objects using `Object.keys()` / `Object.getOwnPropertyNames()` instead of Python's `vars()`. It produces the SAME `_worker_ref` / `_type` marker format that the server normalizers expect.

Key behaviors:
- Callables → `{ "_worker_ref": "name", "description": "...", "parameters": {...} }`
- Non-callable objects → `{ "_type": "ClassName", ... }` with properties recursively serialized
- Enums → string values
- Zod schemas → JSON Schema via `toJsonSchema()`
- Circular references → tracked via WeakSet
- Pydantic/dataclass equivalents → walk enumerable properties

- [ ] **Step 2: Write tests**

Test with mock objects mimicking each framework's shape:
- OpenAI Agent shape: `{ name, model, instructions, tools: [{ name, description, params_json_schema, execute }], handoffs: [...] }` → verify raw_config has model, instructions, tools with `_worker_ref`
- ADK LlmAgent shape: `{ model, instruction, tools: [FunctionTool shape], subAgents: [...] }` → verify extraction
- Simple callable → WorkerInfo with name + schema
- Tool object with embedded function → WorkerInfo
- Agent-as-tool → recursive serialization
- Circular reference → doesn't crash

- [ ] **Step 3: Run tests, commit**

### Task 3: Build LangGraph serializer

**Files:**
- Create: `sdk/typescript/src/frameworks/langgraph-serializer.ts`
- Create: `sdk/typescript/tests/unit/frameworks/langgraph-serializer.test.ts`

- [ ] **Step 1: Write langgraph-serializer.ts**

Two extraction paths (NO passthrough):

```typescript
/**
 * Serialize a LangGraph CompiledStateGraph into (rawConfig, WorkerInfo[]).
 * Tries full extraction first, then graph-structure. Throws if both fail.
 */
export function serializeLangGraph(graph: unknown): [Record<string, unknown>, WorkerInfo[]];
```

**Full extraction** (for createReactAgent + tool-calling graphs):
- `_findModelInGraph(graph)` — walk `graph.nodes`, look for objects with model attributes. In TypeScript, check for `.model`, `.modelName`, `.model_name` properties.
- `_findToolsInGraph(graph)` — find ToolNode, extract `tools_by_name` or equivalent
- `_extractSystemPrompt(graph)` — check for prompt/system message in graph config
- Produce: `{ name, model, instructions, tools: [{ _worker_ref, description, parameters }] }`

**Graph-structure** (for custom StateGraph):
- `_extractNodeFunctions(graph)` — walk `graph.nodes`, extract callable from each node
- `_extractEdges(graph)` — simple edges from `graph.builder?.edges` or equivalent
- `_extractConditionalEdges(graph)` — conditional edges with target mapping
- Each node → WorkerInfo (SIMPLE task worker)
- Each conditional edge → router WorkerInfo
- Produce: `{ name, model, _graph: { nodes: [...], edges: [...], conditional_edges: [...] } }`

**Error when extraction fails:**
```typescript
throw new ConfigurationError(
  `Cannot extract from LangGraph CompiledStateGraph '${name}'. ` +
  `No model or tools detected. Use createReactAgent() or create a native agentspan Agent.`
);
```

- [ ] **Step 2: Write tests**

Test with real `@langchain/langgraph` objects (from local node_modules):
- `createReactAgent({ llm, tools })` → verify full extraction produces model + tools
- Simple `StateGraph` with 2 nodes + edge → verify graph-structure extraction
- Graph with no model → verify error thrown

- [ ] **Step 3: Run tests, commit**

### Task 4: Build LangChain serializer

**Files:**
- Create: `sdk/typescript/src/frameworks/langchain-serializer.ts`
- Create: `sdk/typescript/tests/unit/frameworks/langchain-serializer.test.ts`

- [ ] **Step 1: Write langchain-serializer.ts**

```typescript
export function serializeLangChain(executor: unknown): [Record<string, unknown>, WorkerInfo[]];
```

- Extract model from `executor.agent` or chain steps (look for `ChatOpenAI` instances)
- Extract tools from `executor.tools` (each has `.name`, `.description`, `.schema`)
- For `RunnableSequence`: each step becomes a WorkerInfo
- Produce same raw_config format

- [ ] **Step 2: Write tests, commit**

---

## Chunk 2: Runtime Rewrite + Server Normalizer

### Task 5: Rewrite runtime._runFramework()

**Files:**
- Modify: `sdk/typescript/src/runtime.ts`

- [ ] **Step 1: Replace passthrough with extraction**

The new `_runFramework()` flow:

```typescript
private async _runFramework(agent: object, prompt: string, frameworkId: FrameworkId, options?: RunOptions): Promise<AgentResult> {
  // 1. Serialize framework agent to (rawConfig, workers)
  const [rawConfig, workers] = this._serializeFrameworkAgent(agent, frameworkId);

  // 2. Register tool workers for extracted callables
  for (const worker of workers) {
    if (worker.func) {
      await this.workerManager.registerTaskDef(worker.name);
      this.workerManager.addWorker(worker.name, async (inputData) => {
        const result = await worker.func!(inputData);
        return typeof result === 'object' ? result : { result };
      });
    }
  }

  this.workerManager.startPolling();

  try {
    // 3. POST /agent/start with framework + rawConfig
    const startResponse = await this._httpRequest('POST', '/agent/start', {
      framework: frameworkId,
      rawConfig,
      prompt,
      sessionId: options?.sessionId ?? '',
      media: options?.media ?? [],
    }, options?.signal);

    const executionId = startResponse.executionId as string;

    // 4. Stream/poll for result (same as native agent path)
    // ... SSE stream or poll ...

    return result;
  } finally {
    this.workerManager.stopPolling();
  }
}

private _serializeFrameworkAgent(agent: object, frameworkId: FrameworkId): [Record<string, unknown>, WorkerInfo[]] {
  switch (frameworkId) {
    case 'langgraph': return serializeLangGraph(agent);
    case 'langchain': return serializeLangChain(agent);
    case 'openai':
    case 'google_adk':
      return serializeFrameworkAgent(agent); // generic serializer
    default:
      throw new ConfigurationError(`Unsupported framework: ${frameworkId}`);
  }
}
```

- [ ] **Step 2: Remove passthrough-specific code**

Remove: `_getWorkerFactory()`, `makeXWorker` imports, 600s timeout for passthrough, `_fw_task` handling, `__workflowInstanceId__` injection, event-push references.

- [ ] **Step 3: Update _startFramework() and stream path similarly**

- [ ] **Step 4: Run tests, commit**

### Task 6: Rewrite VercelAINormalizer on server

**Files:**
- Modify: `server/src/main/java/dev/agentspan/runtime/normalizer/VercelAINormalizer.java`
- Modify: `server/src/test/java/dev/agentspan/runtime/normalizer/VercelAINormalizerTest.java`

- [ ] **Step 1: Rewrite VercelAINormalizer to do real extraction**

Model it after `OpenAINormalizer.java` — extract model, tools, instructions from raw_config. Since Vercel AI SDK users will now use native Agent (not framework detection), this normalizer is mostly for backward compatibility. But if someone sends `framework: "vercel_ai"` with a proper raw_config, it should work.

- [ ] **Step 2: Update tests**

Verify raw_config with model + tools produces AgentConfig with model, tools[], not `_framework_passthrough`.

- [ ] **Step 3: Remove `_framework_passthrough` from VercelAINormalizer**

The normalizer must NOT set `_framework_passthrough: true`. It should produce a real AgentConfig.

- [ ] **Step 4: Build and test server**

```bash
cd server && ./gradlew test
```

- [ ] **Step 5: Commit**

---

## Chunk 3: Rewrite Examples

### Task 7: Rewrite Vercel AI examples

**Files:**
- Rewrite: `sdk/typescript/examples/vercel-ai/*.ts` (10 files)

- [ ] **Step 1: Rewrite all 10 examples to use native Agent + superset tools**

Instead of duck-typed wrapper → `runtime.run(wrapper, prompt)`, use:

```typescript
import { tool } from 'ai';
import { Agent, AgentRuntime } from '../../src/index.js';

const weatherTool = tool({ description: '...', parameters: z.object({...}), execute: ... });

const agent = new Agent({
  name: 'weather_agent',
  model: 'openai/gpt-4o-mini',
  instructions: 'You are helpful.',
  tools: [weatherTool],
});

const runtime = new AgentRuntime();
const result = await runtime.run(agent, 'What is the weather?');
result.printResult();
await runtime.shutdown();
```

- [ ] **Step 2: Validate each example runs and produces multi-task workflow**

```bash
AGENTSPAN_SERVER_URL=http://localhost:6767/api npx tsx examples/vercel-ai/01-basic-agent.ts
```

Verify workflow has LLM_CHAT_COMPLETE + SIMPLE tasks (not single _fw_task).

- [ ] **Step 3: Commit**

### Task 8: Verify OpenAI, ADK, LangGraph, LangChain examples

**Files:**
- Modify: `sdk/typescript/examples/openai/*.ts` (10 files)
- Modify: `sdk/typescript/examples/adk/*.ts` (10 files)
- Modify: `sdk/typescript/examples/langgraph/*.ts` (10 files)
- Modify: `sdk/typescript/examples/langchain/*.ts` (10 files)

- [ ] **Step 1: Run each framework's examples and verify multi-task workflows**

After the extraction rewrite, `runtime.run(openaiAgent, prompt)` should:
1. Detect as OpenAI framework
2. Serialize via generic serializer → raw_config with model + tools
3. POST /agent/start → OpenAINormalizer → AgentConfig → AgentCompiler
4. Produce workflow with LLM_CHAT_COMPLETE + SIMPLE per tool

Verify by checking workflow structure:
```bash
curl http://localhost:6767/api/workflow/{executionId}?includeTasks=true
```

- [ ] **Step 2: Fix any examples that fail extraction**

If an example can't be extracted, adjust to use patterns that ARE extractable per spec §5.3.

- [ ] **Step 3: Run validation**

```bash
npx tsx validation/runner.ts --config validation/runs.toml.example --run smoke
npx tsx validation/runner.ts --config validation/runs.toml.example --run vercel_ai
npx tsx validation/runner.ts --config validation/runs.toml.example --run openai_sdk
npx tsx validation/runner.ts --config validation/runs.toml.example --run langgraph
npx tsx validation/runner.ts --config validation/runs.toml.example --run langchain
npx tsx validation/runner.ts --config validation/runs.toml.example --run adk
```

- [ ] **Step 4: Commit**

---

## Chunk 4: E2E Verification

### Task 9: E2E extraction tests

**Files:**
- Create: `sdk/typescript/tests/unit/frameworks/extraction-e2e.test.ts`

- [ ] **Step 1: Write E2E tests that verify workflow structure**

For each framework, verify the FULL chain: framework agent → serializer → raw_config → POST /compile → WorkflowDef:
- WorkflowDef has multiple tasks (NOT single _fw_task)
- Has LLM_CHAT_COMPLETE system task (for agents with model)
- Has SIMPLE tasks for each extracted tool
- Tool tasks have correct names matching the framework's tool names

- [ ] **Step 2: Run all tests**

```bash
npx vitest run
```

- [ ] **Step 3: Final validation run**

```bash
./scripts/test.sh
```

- [ ] **Step 4: Commit**

```bash
git commit -m "feat(ts-sdk): framework extraction — agents compile to multi-task workflows"
```
