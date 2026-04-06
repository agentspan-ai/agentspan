# TypeScript Framework Serializer Parity Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make TypeScript SDK framework serializers produce identical rawConfig output as Python SDK, verified via `plan()` on all 91 TypeScript framework examples.

**Architecture:** Enhance `langgraph-serializer.ts` to match Python's 3-path extraction (full → graph-structure → passthrough) with LLM/subgraph/human node detection, dynamic fanout, reducers, retry policies, and input_key. Fix `langchain-serializer.ts` to add passthrough fallback. Verify OpenAI/ADK generic serializers produce matching output. Use monkey-patching on LLM objects (not closure inspection) for JS-compatible interception.

**Tech Stack:** TypeScript, LangGraph JS, LangChain JS, OpenAI Agents SDK, Google ADK

---

## File Structure

**Modify:**
- `sdk/typescript/src/frameworks/langgraph-serializer.ts` — Major enhancement: LLM/subgraph/human detection, prep/finish workers, reducers, retry, input_key, passthrough
- `sdk/typescript/src/frameworks/langchain-serializer.ts` — Add passthrough fallback
- `sdk/typescript/src/frameworks/serializer.ts` — Minor: ensure OpenAI/ADK produce same rawConfig as Python
- `sdk/typescript/src/runtime.ts` — Already done: `plan()` handles framework agents

**No new files needed** — all changes are in existing serializer files.

---

## Chunk 1: LangGraph Serializer — Graph Structure Enhancement

### Task 1: Fix _agentspan metadata short-circuit

The `_agentspan` metadata currently bypasses ALL graph introspection. When a LangGraph graph has `_agentspan` set, the serializer returns a simple agent config, losing the entire graph topology.

**Fix:** When `_agentspan` is present, use it for model/instructions hints but still attempt graph-structure extraction. Only fall back to metadata-only if graph extraction fails.

**Files:**
- Modify: `sdk/typescript/src/frameworks/langgraph-serializer.ts:24-61`

- [ ] **Step 1: Restructure serializeLangGraph entry point**

Change the priority order from:
```
1. _agentspan metadata → return immediately
2. Full extraction
3. Graph-structure
```
To:
```
1. Extract model/instructions from _agentspan (hints only)
2. Graph-structure extraction (always attempted first for StateGraph)
3. Full extraction (for react agents with ToolNode)
4. Passthrough fallback
```

The key change: `_agentspan` provides hints (model string, instructions) but does NOT bypass graph extraction.

- [ ] **Step 2: Build and verify debate agents produce _graph config**

Run: `cd /tmp/readme-tests/ts && npx tsx plan-debate.ts`
Expected: Output contains `_graph` with nodes `[pro, con, judge]`, edges, and conditional_edges

- [ ] **Step 3: Commit**

---

### Task 2: Add LLM node detection

Python detects LLM nodes by inspecting `func.__code__.co_names` and `func.__globals__` for LLM objects. In JS, we can't inspect bytecode, but we CAN:

1. Search the node's bound object tree for LLM-like instances (ChatOpenAI, ChatAnthropic, etc.)
2. Search the graph-level scope for LLM objects shared across nodes
3. Check if the node function's `.toString()` contains `.invoke(` patterns

**Files:**
- Modify: `sdk/typescript/src/frameworks/langgraph-serializer.ts`

- [ ] **Step 1: Implement `_findLLMInNode` function**

```typescript
function _findLLMInNode(
  nodeFunc: Function,
  nodeObj: unknown,
  graph: unknown,
): { varPath: string; llm: unknown } | null {
  // Strategy 1: Search the node's bound object properties for LLM instances
  // Look for objects with model_name/modelName that pass _tryGetModelString
  // Strategy 2: Search graph-level for module-scope LLM objects
  // Walk graph.nodes values, check .bound properties
  // Strategy 3: Check function source for .invoke patterns
  // Use nodeFunc.toString() to detect LLM call patterns
}
```

Detection criteria (matches Python's `_find_llm_in_func`):
- Object has `model_name` or `modelName` property
- `_tryGetModelString(obj)` returns non-null
- Object has `.invoke()` method
- Object is NOT a compiled graph (check for `.nodes` Map)

- [ ] **Step 2: Implement `_findLLMReference` helper**

Search the graph scope for the actual LLM object that the node function references:

```typescript
function _findLLMReference(
  graph: unknown,
  nodeKey: string,
): { llm: unknown; path: string } | null {
  // Search: graph.nodes.get(nodeKey).bound properties
  // Search: graph-level properties
  // Return the LLM object and the property path to it
}
```

- [ ] **Step 3: Test LLM detection on debate agents graph**

The debate agents graph has `const llm = new ChatOpenAI(...)` used by all 3 nodes. All 3 should be detected as LLM nodes.

- [ ] **Step 4: Commit**

---

### Task 3: Add LLM prep/finish workers

When an LLM node is detected, create two workers instead of one:
- **Prep worker**: Runs the node function with a capture proxy on the LLM, extracts the messages being sent to the LLM
- **Finish worker**: Runs the node function with a mock LLM that returns the server-provided response

**Files:**
- Modify: `sdk/typescript/src/frameworks/langgraph-serializer.ts`

- [ ] **Step 1: Implement CapturedLLMCall error class**

```typescript
class CapturedLLMCall extends Error {
  constructor(public messages: unknown[]) {
    super('LLM call captured');
  }
}
```

- [ ] **Step 2: Implement `makeLLMPrepWorker`**

```typescript
function makeLLMPrepWorker(
  nodeFunc: Function,
  nodeName: string,
  llmObj: unknown,
): (task: { inputData: Record<string, unknown> }) => Promise<Record<string, unknown>> {
  return async (task) => {
    const state = task.inputData.state as Record<string, unknown>;

    // Monkey-patch the LLM's invoke method
    const originalInvoke = (llmObj as any).invoke;
    (llmObj as any).invoke = async (messages: unknown[]) => {
      throw new CapturedLLMCall(messages);
    };

    try {
      const result = await (nodeFunc as any)(state);
      // Node completed without calling LLM — skip LLM
      return { messages: [], state: { ...state, ...result }, result: _stateToResult(result), _skip_llm: true };
    } catch (e) {
      if (e instanceof CapturedLLMCall) {
        const serialized = _serializeMessages(e.messages);
        return { messages: serialized, state };
      }
      throw e;
    } finally {
      (llmObj as any).invoke = originalInvoke;
    }
  };
}
```

- [ ] **Step 3: Implement `makeLLMFinishWorker`**

```typescript
function makeLLMFinishWorker(
  nodeFunc: Function,
  nodeName: string,
  llmObj: unknown,
): (task: { inputData: Record<string, unknown> }) => Promise<Record<string, unknown>> {
  return async (task) => {
    const state = task.inputData.state as Record<string, unknown>;
    const llmResult = task.inputData.llm_result as string;

    // Monkey-patch invoke to return mock response
    const originalInvoke = (llmObj as any).invoke;
    (llmObj as any).invoke = async () => {
      // Return a mock AIMessage-like response
      return { content: llmResult };
    };

    try {
      const result = await (nodeFunc as any)(state);
      const merged = { ...state, ...result };
      return { state: merged, result: _stateToResult(result) };
    } finally {
      (llmObj as any).invoke = originalInvoke;
    }
  };
}
```

- [ ] **Step 4: Implement `_serializeMessages`**

Convert LangChain message objects to the server's format:

```typescript
function _serializeMessages(messages: unknown[]): Array<Record<string, unknown>> {
  return messages.map((msg: any) => {
    const role = msg._getType?.() === 'human' ? 'user'
      : msg._getType?.() === 'system' ? 'system'
      : msg._getType?.() === 'ai' ? 'assistant'
      : msg.role || 'user';
    return { role, message: msg.content || '' };
  });
}
```

- [ ] **Step 5: Wire LLM detection into _serializeGraphStructure**

In the node iteration loop, check `_findLLMInNode()` before creating a regular worker. If LLM detected:
- Create prep + finish workers
- Mark node with `_llm_node: true`, `_llm_prep_ref`, `_llm_finish_ref`

- [ ] **Step 6: Validate debate agents plan output matches Python**

Run plan() on both, compare:
- Python: 3 LLM nodes with prep/finish refs, DO_WHILE loop, router
- TypeScript: should now produce identical _graph structure

- [ ] **Step 7: Commit**

---

### Task 4: Add subgraph detection

**Files:**
- Modify: `sdk/typescript/src/frameworks/langgraph-serializer.ts`

- [ ] **Step 1: Implement `_findSubgraphInNode`**

```typescript
function _findSubgraphInNode(
  nodeFunc: Function,
  nodeObj: unknown,
  graph: unknown,
): { varPath: string; subgraph: unknown } | null {
  // Search node's bound object tree for compiled graph objects
  // Detection: has .nodes Map AND .invoke method AND (.getGraph OR .builder)
  // Must NOT be the parent graph itself
}
```

- [ ] **Step 2: Implement prep/finish workers for subgraphs**

Similar pattern to LLM interception — capture `.invoke()` input, return mock result.

```typescript
function makeSubgraphPrepWorker(nodeFunc: Function, nodeName: string, subgraphObj: unknown) { ... }
function makeSubgraphFinishWorker(nodeFunc: Function, nodeName: string, subgraphObj: unknown) { ... }
```

- [ ] **Step 3: Wire into _serializeGraphStructure**

Check for subgraph BEFORE LLM (a subgraph node might also contain LLMs, but the subgraph takes priority). If detected:
- Recursively call `_serializeGraphStructure` on the subgraph
- Mark node with `_subgraph_node: true`, `_subgraph_prep_ref`, `_subgraph_finish_ref`, `_subgraph_config`

- [ ] **Step 4: Validate on subgraph examples**

Run plan() on LangGraph examples that use subgraphs (e.g., `25-map-reduce.ts`, `26-subgraph.ts` if they exist).

- [ ] **Step 5: Commit**

---

### Task 5: Add human node, dynamic fanout, reducers, retry, input_key

**Files:**
- Modify: `sdk/typescript/src/frameworks/langgraph-serializer.ts`

- [ ] **Step 1: Add human node detection**

```typescript
// Check for _agentspan_human_task marker on node function
function _isHumanNode(nodeFunc: Function): boolean {
  return (nodeFunc as any)._agentspan_human_task === true;
}
```

In the node iteration: if human node, set `_human_node: true`, `_human_prompt`, and do NOT create a worker.

- [ ] **Step 2: Add dynamic fanout (Send API) detection**

```typescript
function _isSendRouter(routerFunc: Function): boolean {
  // Check function source for 'Send' reference
  const src = routerFunc.toString();
  return src.includes('Send');
}
```

In conditional edge processing: if Send detected, mark with `_dynamic_fanout: true`.
For dynamic fanout target nodes that are LLM nodes, also register a direct (non-intercepted) worker.

- [ ] **Step 3: Add reducer extraction**

```typescript
function _extractReducers(graph: unknown): Record<string, string> | null {
  const channels = (graph as any).channels;
  if (!channels) return null;
  const reducers: Record<string, string> = {};
  for (const [name, ch] of Object.entries(channels)) {
    if (name.startsWith('__') || name.startsWith('branch:')) continue;
    const typeName = ch?.constructor?.name || '';
    if (typeName === 'BinaryOperatorAggregate') {
      const op = (ch as any).operator;
      const opName = op?.name || String(op);
      reducers[name] = opName;
    }
  }
  return Object.keys(reducers).length > 0 ? reducers : null;
}
```

- [ ] **Step 4: Add retry policy extraction**

```typescript
function _extractRetryPolicies(graph: unknown): Record<string, Record<string, unknown>> | null {
  const builder = (graph as any).builder;
  if (!builder?._nodes) return null;
  const policies: Record<string, Record<string, unknown>> = {};
  for (const [name, nodeSpec] of Object.entries(builder._nodes)) {
    const retry = (nodeSpec as any).retry;
    if (retry) {
      policies[name] = {
        max_attempts: retry.maxAttempts ?? retry.max_attempts,
        initial_interval: retry.initialInterval ?? retry.initial_interval,
        backoff_factor: retry.backoffFactor ?? retry.backoff_factor,
        max_interval: retry.maxInterval ?? retry.max_interval,
      };
    }
  }
  return Object.keys(policies).length > 0 ? policies : null;
}
```

- [ ] **Step 5: Add input_key detection**

```typescript
function _extractInputKey(graph: unknown): string | null {
  // Try getInputJsonSchema if available
  const schema = (graph as any).getInputJsonSchema?.();
  if (!schema?.properties) return null;
  const required = schema.required || [];
  for (const field of required) {
    if (schema.properties[field]?.type === 'string') return field;
  }
  // Fallback: check first field
  return Object.keys(schema.properties)[0] || null;
}
```

- [ ] **Step 6: Add passthrough fallback**

When graph-structure extraction fails (no nodes found, or error):

```typescript
function _serializePassthrough(name: string, graph: unknown): [Record<string, unknown>, WorkerInfo[]] {
  const workerName = name;
  return [
    { name, _worker_name: workerName },
    [{ name: workerName, description: `Passthrough worker for ${name}`, inputSchema: {}, func: null }],
  ];
}
```

- [ ] **Step 7: Wire all into _serializeGraphStructure**

Add to the _graph config:
```typescript
if (inputKey) graphConfig.input_key = inputKey;
if (reducers) graphConfig._reducers = reducers;
if (retryPolicies) graphConfig._retry_policies = retryPolicies;
```

- [ ] **Step 8: Validate on representative examples**

Run plan() on examples that exercise each feature:
- Human nodes
- Dynamic fanout (Send API)
- State reducers
- Retry policies

- [ ] **Step 9: Commit**

---

## Chunk 2: LangChain Serializer + OpenAI/ADK Verification

### Task 6: Fix LangChain serializer — add passthrough fallback

Python's LangChain serializer tries full extraction, then falls back to passthrough. TypeScript throws an error.

**Files:**
- Modify: `sdk/typescript/src/frameworks/langchain-serializer.ts`

- [ ] **Step 1: Add passthrough fallback**

When model OR tools not found, return passthrough config instead of throwing:

```typescript
// Replace the ConfigurationError throw with:
const workerName = name;
return [
  { name, _worker_name: workerName },
  [{ name: workerName, description: `Passthrough for ${name}`, inputSchema: {}, func: null }],
];
```

- [ ] **Step 2: Commit**

---

### Task 7: Verify OpenAI serializer output

Both SDKs use generic serialization for OpenAI agents. Run plan() on matching examples and compare.

**Files:**
- Modify: `sdk/typescript/src/frameworks/serializer.ts` (if differences found)

- [ ] **Step 1: Create plan() comparison scripts**

For each OpenAI example that exists in both Python and TypeScript (10 examples), create plan scripts that call `runtime.plan(agent)` and output JSON.

- [ ] **Step 2: Run all 10 TS OpenAI examples with plan()**

- [ ] **Step 3: Run matching Python examples with plan()**

- [ ] **Step 4: Compare rawConfig output, fix any differences**

Key things to check:
- Tool extraction produces same `_worker_ref` entries
- Agent name matches
- Model string format matches (`openai/gpt-4o` vs `gpt-4o`)
- Handoff/transfer tool structure matches

- [ ] **Step 5: Commit if changes needed**

---

### Task 8: Verify ADK serializer output

Same approach as OpenAI — both use generic serialization.

- [ ] **Step 1: Run plan() on representative ADK examples (5-10)**
- [ ] **Step 2: Compare Python vs TypeScript output**
- [ ] **Step 3: Fix differences if any**
- [ ] **Step 4: Commit if changes needed**

---

## Chunk 3: Full Validation

### Task 9: Validate ALL LangGraph examples (45)

- [ ] **Step 1: Create batch plan() runner for TypeScript**

Script that runs `runtime.plan(graph)` on every LangGraph example and saves the rawConfig JSON.

- [ ] **Step 2: Run all 45 TypeScript LangGraph examples**
- [ ] **Step 3: Run all 45 Python LangGraph examples**
- [ ] **Step 4: Compare outputs, create diff report**

Compare key fields:
- `_graph.nodes` — same count, same names, same flags (_llm_node, _human_node, etc.)
- `_graph.edges` — same connections
- `_graph.conditional_edges` — same routing
- `_graph._reducers` — same reducer map
- `_graph.input_key` — same key
- `model` — same model string

- [ ] **Step 5: Fix any remaining mismatches**
- [ ] **Step 6: Commit**

---

### Task 10: Validate ALL OpenAI examples (10)

- [ ] **Step 1: Run plan() on all 10 TypeScript OpenAI examples**
- [ ] **Step 2: Run plan() on matching Python examples**
- [ ] **Step 3: Compare and fix**
- [ ] **Step 4: Commit**

---

### Task 11: Validate ALL ADK examples (36)

- [ ] **Step 1: Run plan() on all 36 TypeScript ADK examples**
- [ ] **Step 2: Run plan() on matching Python examples**
- [ ] **Step 3: Compare and fix**
- [ ] **Step 4: Commit**

---

### Task 12: Final build + integration test

- [ ] **Step 1: Full TypeScript SDK build**

```bash
cd sdk/typescript && npm run build
```

- [ ] **Step 2: Run existing TypeScript tests**

```bash
cd sdk/typescript && npm test
```

- [ ] **Step 3: Generate summary table**

Create a summary table:
| Example | Framework | Python plan() | TS plan() | Match? |
|---------|-----------|---------------|-----------|--------|

- [ ] **Step 4: Final commit with all changes**
