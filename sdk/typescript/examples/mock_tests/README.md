# Mock Tests — TypeScript SDK

## Table of Contents

- [What Is This?](#what-is-this)
- [Why Mock Test Agents?](#why-mock-test-agents)
- [When to Use Mock Tests](#when-to-use-mock-tests)
- [Setup](#setup)
- [Run](#run)
- [Examples](#examples)
- [Quick Reference](#quick-reference)
  - [mockRun](#mockrun)
  - [mockTools](#mocktools)
  - [Assertions](#assertions)
  - [Fluent API](#fluent-api)
  - [AgentResult](#agentresult)
- [Strategy Validation](#strategy-validation)
- [Record / Replay](#record--replay)
- [CorrectnessEval — LLM Judge Evaluation](#correctnesseval--llm-judge-evaluation)
- [Testing Pyramid for Agents](#testing-pyramid-for-agents)
- [FAQ](#faq)

---

## What Is This?

The Agentspan testing framework lets you write **deterministic, reproducible tests for AI agents** — without calling an LLM, connecting to a server, or spending API credits. You provide mock tool implementations, run the agent locally with `mockRun()`, and assert that the agent's structure and behavior are correct.

This is the agent equivalent of unit testing. Just as you wouldn't hit a real database to test your request handler logic, you don't need a real LLM to test that your agent routes to the right specialist, calls tools in the right order, or respects guardrail boundaries.

## Why Mock Test Agents?

**Fast feedback loop.** Mock tests run in milliseconds. No network calls, no token costs, no flaky LLM responses. You can run hundreds of test cases in seconds as part of CI.

**Test orchestration logic, not LLM quality.** The hardest bugs in multi-agent systems aren't about what the LLM says — they're about *routing*: did the right agent get picked? Did tools fire in the right order? Did the guardrail block before the agent acted? Did the pipeline skip a stage? Mock tests catch these structural bugs deterministically.

**Catch regressions early.** When you refactor agent definitions, change tool signatures, or restructure your agent hierarchy, mock tests tell you immediately if the orchestration contract broke — before you burn time on expensive live runs.

**Test edge cases you can't reproduce with an LLM.** What happens when a guardrail fails and retries? When two agents transfer back and forth in a loop? When a tool throws an error mid-pipeline? Mock tests let you script exact scenarios that would be nearly impossible to trigger reliably with a real model.

**Complement live evals, don't replace them.** Mock tests verify *structure* (correct routing, tool usage, event ordering). Live evals with `CorrectnessEval` verify *quality* (did the LLM produce a good answer?). Use both: mock tests in CI for fast structural checks, live evals periodically for behavioral validation.

## When to Use Mock Tests

- **CI/CD pipelines** — run on every commit, zero cost, sub-second execution
- **Developing new agents** — validate orchestration logic before wiring up real LLMs
- **Refactoring** — ensure agent restructuring doesn't break routing or tool contracts
- **Edge case coverage** — guardrail failures, error recovery, HITL flows, transfer loops
- **Strategy validation** — verify sequential order, parallel completeness, round-robin alternation, transition constraints
- **Regression testing** — record a known-good run, replay and re-assert later

## Setup

The testing module ships with the SDK under a dedicated sub-export. No extra dependencies needed for mock tests.

```bash
# Install the SDK (if not already installed)
npm install @agentspan-ai/sdk

# The testing module is available at:
#   import { mockRun, expectResult, ... } from "@agentspan-ai/sdk/testing";
```

For running tests, use [Vitest](https://vitest.dev/):

```bash
npm install -D vitest
```

## Run

```bash
# All mock tests
npx vitest run examples/mock_tests/

# Single file
npx vitest run examples/mock_tests/01-basic-agent.test.ts

# Watch mode (re-runs on file changes)
npx vitest watch examples/mock_tests/

# Only tests matching a name pattern
npx vitest run examples/mock_tests/ -t "routes docs question"
```

## Examples

| # | File | Topics |
|---|------|--------|
| 01 | `01-basic-agent.test.ts` | `mockRun`, status/output assertions, `expectResult()` fluent API, mock credentials |
| 02 | `02-tool-assertions.test.ts` | Mock tool overrides, call ordering via tracking, output validation, error in tools, token usage budget |
| 03 | `03-multi-agent-strategies.test.ts` | Handoff, Sequential, Parallel, Router — `assertAgentRan`, `assertHandoffTo`, tool isolation |
| 04 | `04-guardrails-and-errors.test.ts` | Guardrail events, finish reasons, error handling, token limits, guardrails in multi-agent flows |
| 05 | `05-advanced-patterns.test.ts` | `record`/`replay` fixtures, `validateStrategy`, nested strategies, complex tool chains, session ID |

Start with `01-basic-agent.test.ts` and work through in order — each file builds on concepts from the previous one.

## Quick Reference

### mockRun

`mockRun()` executes an agent locally with mock tool implementations and returns an `AgentResult` you can assert against. No LLM or server is involved.

```typescript
import { mockRun } from "@agentspan-ai/sdk/testing";

const result = await mockRun(agent, "user prompt", {
  mockTools: {
    search: async (args) => ({ results: ["found it"] }),
  },
  mockCredentials: { API_KEY: "test-key" },
  sessionId: "custom-session",
});
```

**Options:**

| Option | Type | Description |
|--------|------|-------------|
| `mockTools` | `Record<string, Function>` | Override tool implementations by name. The function receives the tool's args and returns the result. |
| `mockCredentials` | `Record<string, string>` | Mock credentials injected into the tool context. |
| `sessionId` | `string` | Optional session ID for conversation continuity testing. |

### mockTools

`mockTools` is a dictionary mapping tool names to async functions. When the agent calls a tool, the mock function runs instead of the real implementation.

```typescript
const result = await mockRun(agent, "Search for shoes", {
  mockTools: {
    // Simple return value
    search_products: async (args: { query: string }) => [
      { name: "Red Shoe", price: 89.99 },
    ],

    // Simulate an error
    checkout: async () => {
      throw new Error("Payment failed");
    },

    // Track calls for ordering assertions
    get_details: async (args: { id: string }) => {
      callLog.push("get_details");
      return { id: args.id, name: "Widget" };
    },
  },
});
```

If a tool is called but not present in `mockTools`, the agent's real tool implementation runs (if it has one). To override all tools, provide a mock for each.

### Assertions

All assertion functions take an `AgentResult` and throw `Error` on failure:

| Function | What it checks |
|----------|---------------|
| `assertStatus(result, status)` | Result status matches (e.g. `"COMPLETED"`, `"FAILED"`) |
| `assertNoErrors(result)` | No `error` events in the trace |
| `assertToolUsed(result, name)` | Tool was called at least once |
| `assertAgentRan(result, name)` | Agent participated (via handoff or subResults) |
| `assertHandoffTo(result, target)` | A handoff to this agent occurred |
| `assertGuardrailPassed(result, name)` | Named guardrail passed |

```typescript
import {
  assertStatus,
  assertNoErrors,
  assertToolUsed,
  assertAgentRan,
  assertHandoffTo,
  assertGuardrailPassed,
} from "@agentspan-ai/sdk/testing";
```

For assertions not covered by the built-in functions (tool args, call order, output regex), use Vitest's `expect()` directly on the `result.events` and `result.toolCalls` arrays:

```typescript
// Check tool args
const searchCall = result.toolCalls.find(c => c.name === "search");
expect(searchCall?.args).toEqual({ query: "shoes" });

// Check tool call order
const toolNames = result.toolCalls.map(c => c.name);
expect(toolNames).toEqual(["search", "get_details", "checkout"]);

// Check output text
expect(JSON.stringify(result.output)).toContain("order confirmed");
```

### Fluent API

The `expectResult()` API chains multiple assertions in a single expression. Every method returns `this`, so you keep chaining. It throws on the first failure.

```typescript
import { expectResult } from "@agentspan-ai/sdk/testing";

expectResult(result)
  .toBeCompleted()                        // status === "COMPLETED"
  .toHaveUsedTool("search")              // tool was called
  .toContainOutput("answer")             // output JSON contains text
  .toHavePassedGuardrail("pii_check")    // guardrail passed
  .toHaveFinishReason("stop")            // finished naturally
  .toHaveTokenUsageBelow(10000);         // within token budget
```

You can also assert failure:

```typescript
expectResult(result).toBeFailed();  // status !== "COMPLETED"
```

### AgentResult

`mockRun()` returns an `AgentResult` with these key properties:

| Property | Type | Description |
|----------|------|-------------|
| `result.output` | `Record<string, unknown>` | The final answer (normalized to a record) |
| `result.status` | `Status` | `"COMPLETED"`, `"FAILED"`, `"TERMINATED"`, or `"TIMED_OUT"` |
| `result.events` | `AgentEvent[]` | Full execution trace — every tool call, handoff, guardrail, etc. |
| `result.toolCalls` | `unknown[]` | All tool invocations with names and arguments |
| `result.messages` | `unknown[]` | Conversation history |
| `result.error` | `string?` | Error message if the run failed |
| `result.executionId` | `string` | Unique execution identifier |
| `result.finishReason` | `FinishReason` | `"stop"`, `"error"`, `"guardrail"`, `"timeout"`, etc. |
| `result.isSuccess` | `boolean` | `true` if status is `"COMPLETED"` |
| `result.isFailed` | `boolean` | `true` if status is `"FAILED"` or `"TIMED_OUT"` |
| `result.subResults` | `Record<string, unknown>?` | Per-agent results (parallel strategy) |
| `result.tokenUsage` | `TokenUsage?` | Token usage stats |

Each `AgentEvent` has:

| Property | Type | Description |
|----------|------|-------------|
| `event.type` | `EventType` | `"tool_call"`, `"handoff"`, `"done"`, `"error"`, `"guardrail_pass"`, etc. |
| `event.target` | `string?` | Agent name (for handoff events) |
| `event.name` | `string?` | Tool or guardrail name |
| `event.content` | `unknown?` | Event payload |

**EventType values:** `"thinking"`, `"tool_call"`, `"tool_result"`, `"handoff"`, `"message"`, `"waiting"`, `"error"`, `"done"`, `"guardrail_pass"`, `"guardrail_fail"`

---

## Strategy Validation

`validateStrategy(agent, strategy)` verifies that the agent's declared strategy matches what you expect. This is a structural check on the agent definition itself — catching cases where an agent was accidentally configured with the wrong strategy (e.g. `"parallel"` when you meant `"sequential"`).

In the Python SDK, strategy validation goes deeper — it inspects the full execution trace to verify that the orchestration rules were followed. The TypeScript equivalent focuses on the agent's declared strategy, which you combine with runtime assertions (`assertAgentRan`, `assertHandoffTo`, etc.) to verify the full picture.

```typescript
import { validateStrategy } from "@agentspan-ai/sdk/testing";

// Passes silently if the agent's strategy matches
validateStrategy(agent, "handoff");
validateStrategy(agent, "parallel");
validateStrategy(agent, "sequential");

// Throws if there's a mismatch
// e.g. agent is configured as "handoff" but you expected "parallel"
validateStrategy(agent, "parallel"); // throws!
```

Each strategy implies specific runtime behavior that you verify with assertions:

| Strategy | What to verify with assertions |
|----------|-------------------------------|
| **Sequential** | `assertAgentRan()` for every agent in the pipeline. Track execution order with a `callLog` array in mock tools. |
| **Parallel** | `assertAgentRan()` for all agents. Order doesn't matter — just verify none were skipped. |
| **Handoff** | `assertHandoffTo()` for the expected specialist. Verify the wrong specialist was NOT picked. |
| **Router** | `assertHandoffTo()` for exactly one specialist. Verify only that agent ran. |
| **Round Robin** | Track handoff order and verify alternation pattern. Check turn count against `maxTurns`. |

Combine `validateStrategy` with runtime assertions for full coverage:

```typescript
// Verify the agent definition
validateStrategy(auditTeam, "parallel");

// Verify the execution trace
const result = await mockRun(auditTeam, "Audit the checkout page", { ... });
assertAgentRan(result, "security-auditor");
assertAgentRan(result, "performance-auditor");
assertAgentRan(result, "accessibility-auditor");
assertNoErrors(result);
```

---

## Record / Replay

Record/replay lets you capture an `AgentResult` to a JSON fixture file, then load it back later to re-run assertions against it. **Replay does not re-execute anything** — no server, no LLM, no mock run. It simply deserializes the saved result into an `AgentResult` object so you can assert against the same frozen snapshot.

This is the foundation for **regression testing** — you record a known-good result once, commit the fixture to version control, and your CI re-asserts against it on every build. If someone changes the agent definition and the assertions start failing, you know the contract broke.

**How it works:**

```
record(agent, prompt, opts)  →  runs mockRun + saves AgentResult to JSON on disk
replay(path)                 →  reads JSON back into an AgentResult (no execution)
```

The execution happens inside `record()` — it calls `mockRun()` with your mock tools, then serializes the resulting `AgentResult` to the fixture file. `replay()` loads that JSON back into an `AgentResult`. No server, no LLM, no re-execution.

**Why this matters:** Agent definitions evolve — you add tools, restructure sub-agents, change instructions. Without regression fixtures, the only way to know if you broke something is to run a live eval (slow, expensive, non-deterministic). With record/replay, you get instant deterministic regression checks.

**Typical workflow:**

1. Run your agent via `record()` and verify it behaves correctly
2. Commit the fixture JSON to version control
3. In CI, `replay()` the fixture and re-assert — if assertions fail, the agent's contract changed

```typescript
import { record, replay, expectResult, assertHandoffTo } from "@agentspan-ai/sdk/testing";

// Step 1: Record a known-good execution (runs mockRun internally)
const result = await record(agent, "Track order #123", {
  fixturePath: "__fixtures__/track_order.json",
  mockTools: {
    track_shipment: async () => ({ status: "delivered" }),
  },
});

// Step 2: Later (in CI, after refactoring, etc.)
// replay() just loads the JSON — nothing is executed
const replayed = replay("__fixtures__/track_order.json");

expectResult(replayed)
  .toBeCompleted()
  .toHaveUsedTool("track_shipment")
  .toContainOutput("delivered");
assertHandoffTo(replayed, "shipping-specialist");
```

The fixture JSON contains the full execution snapshot:

```json
{
  "agent": { "name": "shipping-support", "model": "openai/gpt-4o" },
  "prompt": "Track order #123",
  "events": [
    { "type": "handoff", "target": "shipping-specialist" },
    { "type": "tool_call", "name": "track_shipment", "args": { "trackingId": "TRK-001" } },
    { "type": "tool_result", "name": "track_shipment", "result": { "status": "delivered" } },
    { "type": "done", "output": "Your package has been delivered!" }
  ],
  "result": {
    "output": { ... },
    "status": "COMPLETED",
    "finishReason": "stop",
    "toolCalls": [ ... ],
    "messages": [ ... ]
  },
  "timestamp": 1712100000000
}
```

The fixture is human-readable and diffable, so you can review what changed when a regression test fails. Commit fixtures alongside your test files in `__fixtures__/` or a similar directory.

---

## CorrectnessEval — LLM Judge Evaluation

`CorrectnessEval` is the **live counterpart to mock tests**. While `mockRun()` tests agents locally without an LLM, `CorrectnessEval` uses an **LLM judge** to evaluate the quality of your agent's output against rubrics you define.

This is where you test whether the agent produced a *good* answer — not just that the orchestration wiring is correct.

**What it requires:**
- An `AgentResult` to evaluate (from `mockRun()` or a live server run)
- An API key for the judge model (e.g. `OPENAI_API_KEY` for `gpt-4o`)
- Real token costs (each evaluation makes an LLM call to the judge)

**How it works:**

1. You run your agent and get an `AgentResult` (via `mockRun()` or live execution)
2. You define rubrics — named criteria the judge scores on a 1-5 scale
3. `CorrectnessEval.evaluate()` sends the result to the judge LLM
4. The judge scores each rubric and returns pass/fail with reasoning

```typescript
import { Agent } from "@agentspan-ai/sdk";
import { mockRun, CorrectnessEval } from "@agentspan-ai/sdk/testing";

// Run the agent (mock or live)
const result = await mockRun(agent, "Explain quantum computing", {
  mockTools: { search: async () => "Quantum computing uses qubits..." },
});

// Evaluate with an LLM judge
const evaluator = new CorrectnessEval({
  model: "openai/gpt-4o-mini",
  apiKey: process.env.OPENAI_API_KEY,
  maxOutputChars: 3000,  // truncate long outputs before judging
  maxTokens: 300,        // max tokens for judge response
});

const evalResult = await evaluator.evaluate(result, {
  rubrics: [
    { name: "accuracy", description: "Is the answer factually correct?", weight: 2 },
    { name: "completeness", description: "Does it cover all key concepts?", weight: 1 },
    { name: "clarity", description: "Is it well-explained for a beginner?", weight: 1 },
  ],
  passThreshold: 3.5,  // weighted average must be >= 3.5 out of 5
});

console.log(`Passed: ${evalResult.passed}`);
console.log(`Weighted average: ${evalResult.weightedAverage}`);
console.log(`Scores:`, evalResult.scores);       // { accuracy: 4, completeness: 5, clarity: 3 }
console.log(`Reasoning:`, evalResult.reasoning);  // per-rubric explanations from the judge
```

**CorrectnessEval constructor options:**

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `model` | `string` | — | Judge model (e.g. `"openai/gpt-4o-mini"`) |
| `apiKey` | `string?` | env var | API key for the judge model |
| `maxOutputChars` | `number` | `3000` | Truncate agent output before sending to judge |
| `maxTokens` | `number` | `300` | Max tokens for the judge's response |
| `endpoint` | `string?` | OpenAI default | Custom API endpoint for the judge |

**Rubric definition:**

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `name` | `string` | — | Rubric identifier (e.g. `"accuracy"`) |
| `description` | `string` | — | What the judge should evaluate (becomes part of the judge prompt) |
| `weight` | `number` | `1` | Relative weight for the weighted average |

**EvalResult fields:**

| Field | Type | Description |
|-------|------|-------------|
| `passed` | `boolean` | `true` if weighted average >= `passThreshold` |
| `scores` | `Record<string, number>` | 1-5 score per rubric |
| `weightedAverage` | `number` | Weighted average across all rubrics |
| `reasoning` | `Record<string, string>` | Per-rubric explanation from the judge LLM |

---

## Testing Pyramid for Agents

| Layer | Tool | Runs against | Cost | Speed | What it catches | CI cadence |
|-------|------|-------------|------|-------|-----------------|------------|
| **Unit** | `mockRun` | Local mock tools | Free | Milliseconds | Broken routing, wrong tool order, missing agents | Every commit |
| **Structural** | `validateStrategy` | Agent definition | Free | Milliseconds | Strategy misconfiguration, wrong strategy type | Every commit |
| **Regression** | `record` / `replay` | Saved JSON fixture | Free | Milliseconds | Changes to orchestration contracts after refactoring | Every commit |
| **Quality** | `CorrectnessEval` | LLM judge | API credits | Seconds per eval | Bad answers, incomplete responses, wrong tone | Nightly / weekly |

Start from the bottom — write mock tests first, add strategy validation, record fixtures, and run LLM judge evals periodically.

---

## FAQ

### Do I need a running server for mock tests?

No. `mockRun()` is entirely local. No server, no LLM, no network calls, no API keys. That's the whole point.

### Do I need a running server for `record()` / `replay()`?

No. `record()` calls `mockRun()` internally and saves the result to JSON. `replay()` reads it back. Neither touches a server.

### Does `CorrectnessEval` need a running Agentspan server?

No. It needs an API key for the **judge model** (e.g. OpenAI), not an Agentspan server. It evaluates an `AgentResult` you already have — it doesn't run the agent. You can pass it results from `mockRun()` or from a live server run.

### How do I test tool call ordering?

Track calls with a `callLog` array in your mock tools:

```typescript
const callLog: string[] = [];
const result = await mockRun(agent, "Buy a widget", {
  mockTools: {
    search: async () => { callLog.push("search"); return []; },
    checkout: async () => { callLog.push("checkout"); return {}; },
  },
});
expect(callLog).toEqual(["search", "checkout"]);
```

### How do I test tool arguments?

Access `result.toolCalls` directly:

```typescript
const searchCall = result.toolCalls.find((c: any) => c.name === "search");
expect(searchCall?.args).toEqual({ query: "red shoes" });
```

### How do I test that an agent does NOT hand off to a specific agent?

Check the events directly:

```typescript
const handoffs = result.events
  .filter(e => e.type === "handoff")
  .map(e => e.target);
expect(handoffs).not.toContain("wrong-agent");
```

### Can I mix the assertion functions with Vitest's `expect()`?

Yes. The SDK assertions (`assertToolUsed`, etc.) throw on failure, which Vitest catches. Use SDK assertions for common checks and Vitest's `expect()` for anything custom:

```typescript
assertToolUsed(result, "search");
assertNoErrors(result);
expect(result.toolCalls).toHaveLength(2);  // Vitest native
```

### What happens if a mock tool throws an error?

The agent handles it like a real tool error. The error is captured in the events trace and you can assert on it:

```typescript
const errorEvents = result.events.filter(e => e.type === "error");
expect(errorEvents.length).toBeGreaterThan(0);
```

### Can I use `CorrectnessEval` to judge mock results?

Yes. `CorrectnessEval` takes any `AgentResult` — it doesn't care whether it came from `mockRun()` or a live server. This is useful for testing output quality of your mock tool responses, or for evaluating recorded fixtures.

### How do I run only live eval tests in CI?

Separate your test files and use Vitest's `--include` flag or file name conventions:

```bash
# Only mock tests
npx vitest run examples/mock_tests/

# Only live eval tests (put them in a separate directory)
npx vitest run examples/eval_tests/
```

Or use `describe.skipIf` to skip live tests when env vars are missing:

```typescript
describe.skipIf(!process.env.OPENAI_API_KEY)("Live Evals", () => {
  // ...
});
```
