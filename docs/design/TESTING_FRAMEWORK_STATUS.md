# Testing Framework — Current State

> Last updated: 2026-04-07
> Branch: `feat/testing-examples-and-capture`
> Status: **Full Python ↔ TypeScript parity achieved**

This document captures the complete current state of the Agentspan testing framework across both SDKs.

---

## Architecture Overview

The testing framework has two layers:

1. **Mock layer** — deterministic, local, no LLM. Used for unit testing agent orchestration.
2. **Eval layer** — runs agents via server, checks structural expectations. Used for behavioral/quality testing.

Both SDKs use the same **scripted event model** and share the same assertion/fluent API surface.

```python
# Python
from agentspan.agents.testing import mock_run, MockEvent, expect, ...
```

```typescript
// TypeScript
import { mockRun, MockEvent, expect, ... } from "@agentspan-ai/sdk/testing";
```

---

## Python SDK — Testing Module

**Location**: `sdk/python/src/agentspan/agents/testing/`
**Files**: 9
**Unit tests**: 81 tests across 4 test files
**Status**: Fully implemented

### Files

| File | Purpose | Status |
|------|---------|--------|
| `__init__.py` | Public exports (24 symbols) | Complete |
| `mock.py` | `MockEvent` factory + `mock_run()` | Complete |
| `assertions.py` | 17 assertion functions | Complete |
| `expect.py` | Fluent `expect()` API (18 chainable methods) | Complete |
| `recording.py` | `record()` / `replay()` JSON serialization | Complete |
| `eval_runner.py` | `CorrectnessEval`, `EvalCase`, auto-capture | Complete |
| `semantic.py` | `assert_output_satisfies()` LLM judge (litellm) | Complete |
| `strategy_validators.py` | 6 strategy validators + constrained transitions | Complete |
| `pytest_plugin.py` | Fixtures (`mock_agent_run`, `event`) + markers | Complete |

---

## TypeScript SDK — Testing Module

**Location**: `sdk/typescript/src/testing/`
**Files**: 8
**Unit tests**: 109 tests across 4 test files + 49 example tests across 5 files
**Status**: Fully implemented — **full parity with Python**

### Files

| File | Purpose | Status |
|------|---------|--------|
| `index.ts` | Public exports | Complete |
| `mock.ts` | `MockEvent` factory (10 methods) + synchronous `mockRun()` | Complete |
| `assertions.ts` | 17 assertion functions | Complete |
| `expect.ts` | Fluent `expect()` API (18 chainable methods) | Complete |
| `recording.ts` | `record()` / `replay()` JSON serialization | Complete |
| `eval.ts` | `CorrectnessEval` with `EvalCase` structural checks | Complete |
| `capture.ts` | `evalCaseFromResult()`, `captureEvalCase()` | Complete |
| `strategy.ts` | 6 strategy validators + constrained transitions | Complete |

### Mock System

TypeScript now uses the same **scripted event model** as Python: you provide a list of `MockEvent` objects that define exactly what the agent "does", and `mockRun()` builds an `AgentResult` from them.

```typescript
const result = mockRun(agent, "Search for laptops", {
  events: [
    MockEvent.toolCall("search_products", { query: "laptops" }),
    MockEvent.toolResult("search_products", [{ name: "MacBook Pro" }]),
    MockEvent.done({ result: "Found 1 laptop." }),
  ],
});
```

**MockEvent factory methods** (10):

| Method | Description |
|--------|-------------|
| `MockEvent.done(output)` | Final output, completes run |
| `MockEvent.toolCall(name, args?)` | Agent invokes a tool |
| `MockEvent.toolResult(name, result)` | Tool return value |
| `MockEvent.handoff(target)` | Delegation to sub-agent |
| `MockEvent.thinking(content)` | LLM reasoning step |
| `MockEvent.message(content)` | Conversational message |
| `MockEvent.error(content)` | Error, marks run as FAILED |
| `MockEvent.waiting(content?)` | HITL pause |
| `MockEvent.guardrailPass(name, content?)` | Guardrail passed |
| `MockEvent.guardrailFail(name, content?)` | Guardrail blocked |

**`autoExecuteTools`**: When `true` (default), real tool functions execute on `tool_call` events. When `false`, you must script both `toolCall` and `toolResult`.

### Assertions (17 functions)

| Category | Functions |
|----------|-----------|
| **Tool** | `assertToolUsed`, `assertToolNotUsed`, `assertToolCalledWith` (subset match), `assertToolCallOrder` (subsequence), `assertToolsUsedExactly` (set equality) |
| **Output** | `assertOutputContains` (substring, case flag), `assertOutputMatches` (regex), `assertOutputType` (typeof) |
| **Status** | `assertStatus`, `assertNoErrors` |
| **Events** | `assertEventsContain` (with attr filter), `assertEventSequence` (subsequence) |
| **Multi-agent** | `assertHandoffTo`, `assertAgentRan` |
| **Guardrails** | `assertGuardrailPassed`, `assertGuardrailFailed` |
| **Budget** | `assertMaxTurns` (counts tool_call + done events) |

### Fluent API (18 chainable methods)

```typescript
expect(result)
  .completed()
  .usedTool("search", { args: { q: "test" } })
  .didNotUseTool("delete")
  .toolCallOrder(["search", "checkout"])
  .outputContains("answer")
  .outputMatches(/ORD-\d+/)
  .handoffTo("specialist")
  .guardrailPassed("pii_check")
  .guardrailFailed("rate_limit")
  .maxTurns(10)
  .noErrors();
```

### Strategy Validators (6 + constrained transitions)

| Strategy | What it validates |
|----------|-------------------|
| `validateSequential` | All agents ran, in definition order, exactly once |
| `validateParallel` | All agents ran (order irrelevant) |
| `validateRoundRobin` | Correct alternation, no consecutive repeats, respects `maxTurns` |
| `validateRouter` | Exactly one sub-agent selected |
| `validateHandoff` | At least one handoff to a valid sub-agent |
| `validateSwarm` | Valid transfers, no infinite loops (pair repeat > 2), respects `maxTurns` |
| `validateConstrainedTransitions` | Every `(src → dst)` in `allowedTransitions[src]` |

Dispatched via `validateStrategy(agent, result)` which reads `agent.strategy`.

### Record / Replay

```typescript
record(result, "fixtures/run.json");           // AgentResult → JSON
const replayed = replay("fixtures/run.json");  // JSON → AgentResult
```

### Eval Runner (CorrectnessEval)

Runs agents against a runtime and checks structural expectations.

```typescript
const evaluator = new CorrectnessEval(runtime);
const results = await evaluator.run([
  {
    name: "billing_routes_correctly",
    agent: support,
    prompt: "I need a refund",
    expectHandoffTo: "billing",
    expectTools: ["lookup_order"],
    expectOutputContains: ["refund"],
  },
]);
results.printSummary();
```

**EvalCase fields** (15):

| Field | Type | Description |
|-------|------|-------------|
| `name` | `string` | Test case name |
| `agent` | `Agent` | Agent to test |
| `prompt` | `string` | User message |
| `expectTools` | `string[]?` | Tools that MUST be used |
| `expectToolsNotUsed` | `string[]?` | Tools that MUST NOT be used |
| `expectToolArgs` | `Record<string, Record<string, unknown>>?` | Tool arg expectations (subset match) |
| `expectHandoffTo` | `string?` | Required handoff target |
| `expectNoHandoffTo` | `string[]?` | Disallowed handoff targets |
| `expectOutputContains` | `string[]?` | Required output substrings |
| `expectOutputMatches` | `string?` | Output regex pattern |
| `expectStatus` | `string` | Expected status (default: `"COMPLETED"`) |
| `expectNoErrors` | `boolean` | No error events (default: `true`) |
| `validateOrchestration` | `boolean` | Run `validateStrategy()` (default: `true`) |
| `customAssertions` | `Array<(result) => void>` | Extra assertion functions |
| `tags` | `string[]` | For filtering eval cases |

### Eval Capture (auto-generation)

```typescript
// From an existing result
const evalCase = evalCaseFromResult(result, { agent, prompt: "..." });

// One-liner: run + generate
const [evalCase, result] = await captureEvalCase(runtime, agent, "Check stock");
```

---

## SDK Parity Matrix

| Feature | Python | TypeScript | Status |
|---------|--------|------------|--------|
| MockEvent factory (10 methods) | Yes | Yes | Parity |
| Scripted mockRun | Yes | Yes | Parity |
| autoExecuteTools | Yes | Yes | Parity |
| 17 assertion functions | Yes | Yes | Parity |
| Fluent API (18 methods) | Yes | Yes | Parity |
| 6 strategy validators | Yes | Yes | Parity |
| Constrained transitions | Yes | Yes | Parity |
| CorrectnessEval (server execution) | Yes | Yes | Parity |
| EvalCase (15 fields) | Yes | Yes | Parity |
| Record / Replay | Yes | Yes | Parity |
| Eval capture | Yes | Yes | Parity |
| Semantic assertions (litellm) | Yes | No | Python-only (litellm dep) |
| Pytest plugin | Yes | N/A | Python-only (framework-specific) |

### Python-only features (by design)

- **Semantic assertions** (`assert_output_satisfies`) — requires `litellm`, a Python-specific dependency
- **Pytest plugin** — framework-specific fixtures and markers

---

## Test Coverage

### Python

| Test file | Tests | What it covers |
|-----------|-------|----------------|
| `test_testing_mock.py` | 14 | MockEvent, mock_run, auto-execute, errors |
| `test_testing_assertions.py` | 43 | All 17 assertion functions, pass + fail cases |
| `test_testing_recording.py` | 8 | Record/replay roundtrip, token usage, events |
| `test_testing_eval_runner.py` | 16 | CorrectnessEval, EvalCase, suite results, tags |
| **Total** | **81** | |

### TypeScript

| Test file | Tests | What it covers |
|-----------|-------|----------------|
| `mock.test.ts` | 20 | MockEvent factory, mockRun, auto-execute, errors |
| `assertions.test.ts` | 40 | All 17 assertion functions, pass + fail cases |
| `expect.test.ts` | 25 | Fluent API, all 18 methods, chaining |
| `strategy.test.ts` | 24 | All 6 validators, constrained transitions, StrategyViolation |
| **Total** | **109** | |

### Example Tests (TypeScript)

| File | Tests | Coverage |
|------|-------|----------|
| `01-basic-agent.test.ts` | 7 | MockEvent + mockRun, basic assertions, fluent API |
| `02-tool-assertions.test.ts` | 9 | Tool assertions, full shopping flow, output validation |
| `03-multi-agent-strategies.test.ts` | 8 | Handoff, sequential, parallel, router strategies |
| `04-guardrails-and-errors.test.ts` | 10 | Guardrails, errors, thinking/waiting, multi-agent guardrails |
| `05-advanced-patterns.test.ts` | 15 | Record/replay, strategy validation, nested strategies |
| **Total** | **49** | |

---

## Known Issues

### Resolved (from previous version)

- ~~TypeScript only has 6 assertions~~ → Now has all 17
- ~~TypeScript uses mockTools model instead of MockEvent~~ → Now uses MockEvent scripted model
- ~~TypeScript validateStrategy only compares strings~~ → Now has 6 trace-level validators
- ~~TypeScript CorrectnessEval uses LLM judge~~ → Now uses structural checks like Python

### Current

1. **`assertToolCalledWith` uses shallow equality** — `===` comparison fails for nested objects/arrays. Same issue in `assertEventsContain` attrs check. Should use deep equality.
2. **`assertOutputContains` searches JSON string** — `JSON.stringify(result.output)` always contains key names like "result", causing potential false positives.
3. **`mockRun` async tool handling** — `autoExecuteTools` calls tool functions synchronously, but SDK tools are async. Promise objects stored as results instead of resolved values.
4. **`evalCaseFromResult` captures only first handoff** — Multi-agent strategies with multiple handoffs get incomplete expectations.
5. **`validateRouter` Rule 3 is dead code** — Filters to expected set then checks if not in expected set (always empty).
6. **`assertMaxTurns` counts `done` as a turn** — Inflates count by 1 vs intuitive expectation.
7. **No TERMINATED/TIMED_OUT mock support** — `mockRun` only produces COMPLETED or FAILED statuses.
8. **Missing unit tests** for `eval.ts`, `capture.ts`, `recording.ts` — other modules have thorough coverage.
