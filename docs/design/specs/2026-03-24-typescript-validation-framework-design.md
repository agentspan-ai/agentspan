# TypeScript SDK Validation Framework Design

**Date:** 2026-03-24
**Status:** Approved
**Depends on:** `docs/superpowers/specs/2026-03-23-typescript-sdk-design.md`

---

## 1. Overview

The validation framework runs every TypeScript SDK example, verifies correctness through algorithmic checks and LLM judging, and for framework examples, compares agentspan passthrough output against native framework execution.

### 1.1 Design Principles

| Principle | Decision |
|-----------|----------|
| Tools are NOT optional | Every tool_call must have a successful tool_result. No silent failures. |
| Event-level auditing | Check individual events, not just workflow status |
| LLM-in-the-loop verification | Every agent with a model must produce thinking events |
| Dual execution for 3P | Framework examples run both natively and on agentspan |
| PASS = algorithmic green + judge >= 3 | Both must pass, not just one |

### 1.2 Two Execution Modes

**Mode 1: Agentspan execution** — run example via `npx tsx`, collect events from SSE stream, run algorithmic checks, LLM judge output.

**Mode 2: Native framework execution** (3P only) — bypass agentspan, call framework SDK directly, collect output, LLM judge compares native vs agentspan.

---

## 2. Algorithmic Checks

### 2.1 Check Interface

```typescript
interface AlgorithmicChecks {
  workflowCompleted: boolean;
  noUnhandledErrors: boolean;
  toolAudit: ToolAuditEntry[];
  allToolsSucceeded: boolean;
  llmEngaged: boolean;
  outputNonEmpty: boolean;
}

interface ToolAuditEntry {
  toolName: string;
  called: boolean;
  succeeded: boolean;
  retriedAndFixed: boolean;
  failedPermanently: boolean;
}
```

### 2.2 Tool Audit Logic

For each `tool_call` event in the event stream:
1. Walk forward looking for a matching `tool_result` with the same `toolName`
2. If `tool_result` exists and is NOT an error → `succeeded: true`
3. If `tool_result` is an error:
   a. Check if a subsequent `tool_call` for the same tool exists
   b. If yes, and its `tool_result` succeeds → `retriedAndFixed: true`
   c. If no retry or retry also failed → `failedPermanently: true`
4. If no `tool_result` at all → `failedPermanently: true`

`allToolsSucceeded = toolAudit.every(t => t.succeeded || t.retriedAndFixed)`

### 2.3 LLM Engagement Check

```
llmEngaged = events.some(e => e.type === 'thinking')
```

Exception: framework passthrough examples may not emit thinking events (the framework handles LLM calls internally). For examples in VERCEL_AI, LANGGRAPH, LANGCHAIN, OPENAI, ADK groups, `llmEngaged` check is relaxed to just `workflowCompleted`.

### 2.4 Error Detection

```
noUnhandledErrors = !events.some(e =>
  e.type === 'error' &&
  !isFollowedByRetrySuccess(e, events)
)
```

An error event followed by a successful retry of the same operation is NOT a failure.

---

## 3. LLM Judge

### 3.1 Individual Scoring

Applied to every example's output:

```
Rubric (1-5):
  1 = Failed: empty, error/traceback, or completely unrelated to prompt
  2 = Poor: attempted but mostly wrong/incomplete
  3 = Partial: relevant but missing key elements
  4 = Good: completed correctly, minor omissions OK
  5 = Excellent: fully addresses prompt
```

### 3.2 Framework Comparison Scoring

Applied to 3P examples — compares agentspan output vs native output:

```
Rubric (1-5):
  1 = Agentspan failed, native succeeded
  2 = Agentspan missed critical elements native covered
  3 = Partial, missing some key elements
  4 = Good, minor differences
  5 = Equivalent or better than native

Special:
  - Different-but-valid approaches = 5
  - Both failed = 3
  - Native failed, agentspan succeeded = 5
```

### 3.3 PASS Criteria

```
PASS = allAlgorithmicChecksGreen && judgeScore >= 3
WARN = allAlgorithmicChecksGreen && judgeScore < 3
FAIL = anyAlgorithmicCheckFailed (regardless of judge score)
```

### 3.4 Caching

- Output hashed (SHA-256, first 16 chars) per example
- If output hash matches previous run, skip judge call and reuse score
- Cache stored in `output/judge_cache.json`

---

## 4. Native Framework Runners

### 4.1 Shim Pattern

Each example imports `AgentRuntime` from `../../src/index.js`. The native shim intercepts this import and redirects execution:

```typescript
// When native=true in TOML config, set env var AGENTSPAN_NATIVE_MODE=1
// Each example checks this and runs the native path instead
```

Each example already has two execution paths (per the hard requirement). The runner just sets the env var to select which path.

### 4.2 Per-Framework Native Execution

| Framework | Native Execution |
|-----------|-----------------|
| Vercel AI | `await generateText({ model, tools, prompt })` or `agent.generate({ prompt })` |
| LangGraph | `await graph.invoke({ messages: [new HumanMessage(prompt)] })` |
| LangChain | `await chain.invoke({ input: prompt })` |
| OpenAI Agents | `await run(agent, prompt)` |
| Google ADK | `await runner.runAsync(sessionId, prompt)` |

---

## 5. Executor

### 5.1 Subprocess Execution

```typescript
async function executeExample(
  examplePath: string,
  env: Record<string, string>,
  timeout: number,
): Promise<ExecutionResult> {
  // Run: npx tsx <examplePath>
  // Capture: stdout, stderr, exit code, duration
  // Parse: output, events, status from stdout
}
```

### 5.2 Event Collection

For agentspan execution, the example itself prints events via the streaming API. The executor captures stdout and parses:
- Agent output from result.printResult() boundary markers
- Tool call count
- Status (COMPLETED/FAILED)
- Workflow ID

### 5.3 Parallel Execution

- Configurable `max_workers` (default 8)
- `Promise.allSettled()` with concurrency limiter
- Abort support via `AbortController`

---

## 6. Reporting

### 6.1 JSON Results

```json
{
  "timestamp": "2026-03-24T...",
  "runs": {
    "openai_agentspan": {
      "model": "openai/gpt-4o-mini",
      "results": {
        "01-basic-agent": {
          "status": "PASS",
          "duration": 3.2,
          "checks": { ... },
          "judgeScore": 5,
          "judgeReason": "Fully addresses prompt",
          "output": "..."
        }
      }
    }
  }
}
```

### 6.2 HTML Report

- Score heatmap (example × run, color-coded 1-5)
- Summary cards (total, pass, fail, avg score per run)
- Filter: All / PASS / FAIL / WARN
- Dark mode toggle
- Expandable details per example (output, events, judge reasoning)
- Framework comparison section (native vs agentspan side-by-side)

---

## 7. TOML Config

```toml
[defaults]
timeout = 300
parallel = true
max_workers = 8

[judge]
model = "openai/gpt-4o-mini"
max_output_chars = 3000
max_tokens = 300
rate_limit = 0.5
pass_threshold = 3

[[runs]]
name = "smoke"
model = "openai/gpt-4o-mini"
group = "SMOKE_TEST"

[[runs]]
name = "vercel_native"
model = "openai/gpt-4o-mini"
group = "VERCEL_AI"
native = true

[[runs]]
name = "langgraph_native"
model = "openai/gpt-4o-mini"
group = "LANGGRAPH"
native = true
```

---

## 8. File Structure

```
sdk/typescript/validation/
  runner.ts              # CLI entry point
  config.ts              # TOML parsing
  discovery.ts           # Find examples by group
  executor.ts            # Subprocess execution + output parsing
  groups.ts              # Example group definitions
  checks/
    algorithmic.ts       # All algorithmic checks
    event-audit.ts       # tool_call → tool_result matching
  judge/
    llm.ts               # LLM scoring (individual + comparison)
    rubrics.ts           # Scoring criteria text
    cache.ts             # Output hash caching
  reporting/
    html.ts              # HTML report generation
    json.ts              # JSON results
  runs.toml.example      # Example config
```

---

## 9. CLI

```bash
# Run all examples in SMOKE_TEST group
npx tsx validation/runner.ts --config validation/runs.toml

# Run specific group
npx tsx validation/runner.ts --config runs.toml --group VERCEL_AI

# Run with LLM judge
npx tsx validation/runner.ts --config runs.toml --judge

# Generate HTML report
npx tsx validation/runner.ts --config runs.toml --judge --report

# Dry run (list examples, don't execute)
npx tsx validation/runner.ts --config runs.toml --dry-run

# Run specific examples
npx tsx validation/runner.ts --config runs.toml --run 01-basic-agent,02-tools
```

---

## 10. Example Groups

```typescript
const GROUPS = {
  SMOKE_TEST: ['01-basic-agent', '02-tools', '03-structured-output', '05-handoffs', '06-sequential-pipeline'],
  VERCEL_AI: ['vercel-ai/01-passthrough', 'vercel-ai/02-tools-compat', 'vercel-ai/03-streaming', ...],
  LANGGRAPH: ['langgraph/01-hello-world', 'langgraph/02-react-with-tools', ...],
  LANGCHAIN: ['langchain/01-hello-world', 'langchain/02-react-with-tools', ...],
  OPENAI: ['openai/01-basic-agent', 'openai/02-function-tools', ...],
  ADK: ['adk/00-hello-world', 'adk/01-basic-agent', ...],
  ALL: [...all examples],
};
```
