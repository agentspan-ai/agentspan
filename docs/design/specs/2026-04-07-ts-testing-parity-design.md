# TypeScript Testing Module — Python Parity Rewrite

> Date: 2026-04-07
> Status: Approved
> Branch: `feat/testing-examples-and-capture`

## Goal

Replace the TypeScript testing module with a Python-aligned implementation. Full API parity with `sdk/python/src/agentspan/agents/testing/`. No backwards compatibility constraints — no existing users.

## Scope

Rewrite all 8 files in `sdk/typescript/src/testing/`:

| File | Change |
|------|--------|
| `mock.ts` | Full rewrite — MockEvent factory + scripted mockRun |
| `assertions.ts` | Full rewrite — 17 assertion functions |
| `expect.ts` | Full rewrite — 18 chainable methods, `expect()` entry point |
| `strategy.ts` | Full rewrite — 6 trace-level validators + StrategyViolation |
| `eval.ts` | Full rewrite — CorrectnessEval with EvalCase server-execution model |
| `recording.ts` | Full rewrite — record(result, path) / replay(path) |
| `capture.ts` | Update — align with new types |
| `index.ts` | Update — new exports |

Rewrite all 4 unit test files in `sdk/typescript/tests/unit/testing/`.

## Design

### 1. MockEvent + mockRun (mock.ts)

**MockEvent** — static factory class. Each method returns an `AgentEvent`.

```typescript
class MockEvent {
  static done(output: unknown): AgentEvent
  static toolCall(name: string, args?: Record<string, unknown>): AgentEvent
  static toolResult(name: string, result: unknown): AgentEvent
  static handoff(target: string): AgentEvent
  static thinking(content: string): AgentEvent
  static message(content: string): AgentEvent
  static error(content: string): AgentEvent
  static waiting(content: string): AgentEvent
  static guardrailPass(name: string, content?: string): AgentEvent
  static guardrailFail(name: string, content: string): AgentEvent
}
```

**mockRun** — synchronous. Builds AgentResult from scripted events.

```typescript
function mockRun(
  agent: Agent,
  prompt: string,
  options: {
    events: AgentEvent[];
    autoExecuteTools?: boolean; // default: true
  }
): AgentResult
```

Behavior:
- Walks the events list sequentially
- Collects tool_call events into `toolCalls` array
- When `autoExecuteTools=true` and a `tool_call` event is encountered, resolves the tool function from `agent.tools` and executes it (result becomes the tool_result)
- When `autoExecuteTools=false`, expects explicit `toolResult` events
- Last `done` event sets `output`; `error` event sets status to `FAILED`
- Builds `messages` from prompt + output
- Returns `AgentResult` via `makeAgentResult`

### 2. Assertions (assertions.ts)

17 functions, all taking `AgentResult` as first arg, all throwing `Error` on failure.

**Tool assertions:**
- `assertToolUsed(result, name)` — at least one tool_call with name
- `assertToolNotUsed(result, name)` — no tool_call with name
- `assertToolCalledWith(result, name, args)` — subset arg match (every key in `args` must match)
- `assertToolCallOrder(result, names)` — subsequence: names appear in this order (gaps OK)
- `assertToolsUsedExactly(result, names)` — set equality of tool names used

**Output assertions:**
- `assertOutputContains(result, text, opts?)` — substring match, `opts.caseSensitive` default true
- `assertOutputMatches(result, pattern)` — regex on stringified output
- `assertOutputType(result, typeName)` — typeof check (e.g. "string", "object")

**Status assertions:**
- `assertStatus(result, status)` — exact match
- `assertNoErrors(result)` — no events with type "error"

**Event assertions:**
- `assertEventsContain(result, eventType, opts?)` — event type exists, `opts.expected` default true
- `assertEventSequence(result, types)` — subsequence of event types

**Multi-agent assertions:**
- `assertHandoffTo(result, agentName)` — handoff event with target
- `assertAgentRan(result, agentName)` — delegates to assertHandoffTo

**Guardrail assertions:**
- `assertGuardrailPassed(result, name)` — guardrail_pass event with name
- `assertGuardrailFailed(result, name)` — guardrail_fail event with name

**Budget assertion:**
- `assertMaxTurns(result, n)` — count of tool_call + done events ≤ n

### 3. Fluent API (expect.ts)

```typescript
class AgentResultExpectation {
  constructor(result: AgentResult)

  // Status
  completed(): this
  failed(): this
  status(s: string): this
  noErrors(): this

  // Tools
  usedTool(name: string, opts?: { args?: Record<string, unknown> }): this
  didNotUseTool(name: string): this
  toolCallOrder(names: string[]): this
  toolsUsedExactly(names: string[]): this

  // Output
  outputContains(text: string, opts?: { caseSensitive?: boolean }): this
  outputMatches(pattern: string | RegExp): this
  outputType(typeName: string): this

  // Events
  eventsContain(eventType: string, opts?: { expected?: boolean }): this
  eventSequence(types: string[]): this

  // Multi-agent
  handoffTo(agentName: string): this
  agentRan(agentName: string): this

  // Guardrails
  guardrailPassed(name: string): this
  guardrailFailed(name: string): this

  // Budget
  maxTurns(n: number): this
}

function expect(result: AgentResult): AgentResultExpectation
```

### 4. Strategy Validators (strategy.ts)

**StrategyViolation** — custom error class:

```typescript
class StrategyViolation extends Error {
  strategy: string;
  violations: string[];
}
```

**6 validators** — each takes (agent, result), throws StrategyViolation:

- `validateSequential` — all agents ran, in definition order, exactly once
- `validateParallel` — all agents ran (order irrelevant)
- `validateRoundRobin` — correct alternation, no consecutive repeats, respects maxTurns
- `validateRouter` — exactly one sub-agent selected
- `validateHandoff` — at least one handoff to valid sub-agent
- `validateSwarm` — valid transfers, no loops (pair > 2), respects maxTurns

**Constrained transitions:**
- `validateConstrainedTransitions(agent, result)` — every (src → dst) in allowedTransitions

**Dispatcher:**
- `validateStrategy(agent, result)` — reads agent.strategy, dispatches to correct validator, also runs constrained transitions if agent.allowedTransitions exists

### 5. CorrectnessEval (eval.ts)

Replace LLM judge with Python's server-execution model.

```typescript
interface EvalCase {
  name: string;
  agent: Agent;
  prompt: string;
  expectTools?: string[];
  expectToolsNotUsed?: string[];
  expectToolArgs?: Record<string, Record<string, unknown>>;
  expectHandoffTo?: string;
  expectNoHandoffTo?: string[];
  expectOutputContains?: string[];
  expectOutputMatches?: string;
  expectStatus?: string;           // default: "COMPLETED"
  expectNoErrors?: boolean;        // default: true
  validateOrchestration?: boolean; // default: true
  customAssertions?: Array<(result: AgentResult) => void>;
  tags?: string[];
}

interface EvalCheckResult {
  check: string;
  passed: boolean;
  message: string;
}

interface EvalCaseResult {
  name: string;
  passed: boolean;
  checks: EvalCheckResult[];
  result?: AgentResult;
  error?: string;
  tags: string[];
}

interface EvalSuiteResult {
  cases: EvalCaseResult[];
  allPassed: boolean;
  passCount: number;
  failCount: number;
  total: number;
  failedCases(): EvalCaseResult[];
  printSummary(): void;
}

class CorrectnessEval {
  constructor(runtime: { run(agent: Agent, prompt: string): Promise<AgentResult> })
  async run(cases: EvalCase[], opts?: { tags?: string[] }): Promise<EvalSuiteResult>
}
```

### 6. Recording (recording.ts)

```typescript
function record(result: AgentResult, path: string): void   // serialize to JSON
function replay(path: string): AgentResult                  // deserialize from JSON
```

Handles all event types, token usage, finish reasons, metadata.

### 7. Capture (capture.ts)

```typescript
function evalCaseFromResult(result: AgentResult, opts: {
  agent: Agent;
  prompt: string;
  name?: string;
  includeToolArgs?: boolean;
  tags?: string[];
}): EvalCase

async function captureEvalCase(runtime: any, agent: Agent, prompt: string, opts?: {
  name?: string;
  includeToolArgs?: boolean;
  tags?: string[];
}): Promise<[EvalCase, AgentResult]>
```

### 8. Exports (index.ts)

```typescript
// Mock
export { MockEvent, mockRun } from './mock.js';

// Assertions (17)
export { assertToolUsed, assertToolNotUsed, assertToolCalledWith, ... } from './assertions.js';

// Fluent
export { expect, AgentResultExpectation } from './expect.js';

// Strategy
export { validateStrategy, StrategyViolation } from './strategy.js';
export { validateSequential, validateParallel, ... } from './strategy.js';

// Eval
export { CorrectnessEval, EvalCase, EvalCaseResult, EvalSuiteResult } from './eval.js';

// Recording
export { record, replay } from './recording.js';

// Capture
export { evalCaseFromResult, captureEvalCase, CapturedEvalCase } from './capture.js';
```

## Non-goals

- Updating the example test files (those can be updated separately)
- Semantic assertions via litellm (Python-specific dep)
- Pytest plugin (Python-specific)
