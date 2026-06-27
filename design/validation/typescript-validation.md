# TypeScript SDK — Validation & E2E

**Status:** Refreshed 2026-06-26

**Scope:** TypeScript SDK validation spans two surfaces: (1) a **deterministic E2E suite** (`sdk/typescript/tests/e2e/`) that exercises real agents against a live server with purely algorithmic, no-LLM-judging assertions, and (2) an **examples-quality validation framework** (`sdk/typescript/validation/`) that runs every shipped example, audits its event stream algorithmically, scores output with an LLM judge, and compares `conductor`-passthrough output against native framework execution. The deterministic suite is the CI gate; the framework is the examples-correctness harness. The SDK ships as `@conductoross/conductor-agent-sdk`. See methodology [`README.md`](README.md), implementation [`../sdk-design/languages/typescript-implementation.md`](../sdk-design/languages/typescript-implementation.md), and overall design [`../sdk-design.md`](../sdk-design.md).

---

## 1. Overview

| Surface | Location | Validation style | Runs in CI |
|---------|----------|------------------|------------|
| Deterministic E2E suites | `sdk/typescript/tests/e2e/` | Algorithmic only — workflow status, task audit, substring checks. No LLM judging. | Yes — `typescript-e2e` job |
| Examples-quality framework | `sdk/typescript/validation/` | Event-level algorithmic checks + LLM judge + dual (conductor vs native) execution | No — run on demand for examples QA |
| Unit tests | `sdk/typescript/tests/unit/` | Pure unit, mocked | Yes — `typescript-unit-tests` job |

Both E2E surfaces talk to a real server (default `http://localhost:6767/api`) and use the same env contract: `AGENTSPAN_SERVER_URL`, `AGENTSPAN_CLI_PATH`, `AGENTSPAN_LLM_MODEL`, `MCP_TESTKIT_URL`, `AGENTSPAN_AUTO_START_SERVER`, and the `agentspan` CLI binary. These names are the cross-SDK runtime contract and are intentional — they are not the npm package name.

---

## 2. Deterministic E2E Suites

Per the project rule, e2e tests do **not** use an LLM for validation (only for judging quality/output in evals — which is the separate framework in §3). Every assertion in `tests/e2e/` is algorithmic: workflow status, task presence/status in the Conductor workflow graph, and substring presence/absence in output.

### 2.1 Layout

```
sdk/typescript/tests/e2e/
  helpers.ts                             # shared API + assertion utilities (no test cases)
  generate-report.ts                     # junit XML → styled HTML report
  test_suite1_basic_validation.test.ts
  test_suite2_tool_calling.test.ts
  test_suite3_cli_tools.test.ts
  test_suite4_mcp_tools.test.ts
  test_suite5_http_tools.test.ts
  test_suite6_pdf_tools.test.ts
  test_suite7_media_tools.test.ts
  test_suite8_guardrails.test.ts
  test_suite9_handoffs.test.ts
  test_suite10_code_execution.test.ts
  test_suite11_langgraph.test.ts
  test_suite12_termination_gates.test.ts
  test_suite13_callbacks.test.ts
  test_suite14_lease_extension.test.ts
  test_suite14_stateful_domain.test.ts   # regression for worker domain-rebuild bug
  test_suite15_behavioral_correctness.test.ts
  test_suite15_skills.test.ts
  test_suite16_streaming.test.ts
  test_suite17_guardrail_matrix.test.ts  # 3×3×3 guardrail matrix
  test_suite18_multi_agent_matrix.test.ts
  test_suite19_token_usage.test.ts
  test_suite20_plan_execute.test.ts
  test_suite21_scheduling.test.ts
  test_suite22_wait_for_message_tool.test.ts
  test_suite23_agent_client.test.ts
```

25 suites total. Each imports the SDK from `@conductoross/conductor-agent-sdk` (aliased to `src/index.ts` by `vitest.config.ts` — see §4).

### 2.2 Shared helpers (`helpers.ts`)

`helpers.ts` holds no test cases — only inspection and assertion utilities, all algorithmic:

- **Config** — `MODEL` (`AGENTSPAN_LLM_MODEL`, default `openai/gpt-4o-mini`), `CLI_PATH` (`AGENTSPAN_CLI_PATH`, default `agentspan`), `MCP_TESTKIT_URL`, `TIMEOUT` (300 s), `SERVER_URL` (`AGENTSPAN_SERVER_URL`, default `http://localhost:6767/api`).
- **Workflow API** — `getWorkflow(executionId)` fetches the full Conductor workflow JSON; `checkServerHealth()` polls `/health` and returns `healthy === true`.
- **Output extraction** — `getOutputText(result)` flattens `output.result` (string or array of `{text|content}`) into a single string for substring assertions; `runDiagnostic(result)` formats a one-line status/keys/finishReason summary for failure messages.
- **Credentials** — `credentialSet(name, value)` / `credentialDelete(name)` write directly to the server secret store via `PUT/DELETE /api/secrets/{name}` (not via the CLI) so tests are deterministic regardless of ambient `~/.agentspan/config.json`.
- **Task finders** — `findToolTasks(executionId, toolNames)` and `findToolTasksDeep(...)` (recurses one level through `SUB_WORKFLOW` tasks, depth ≤ 3) locate tool execution tasks in the workflow graph, skipping system task types (`LLM_CHAT_COMPLETE`, `SWITCH`, `DO_WHILE`, `FORK`, `JOIN`, `SUB_WORKFLOW`, etc.). Each returns `{ status, output, input, ref, taskDef, taskType, reason }` plus a flat `allTasks` listing for diagnostics.

### 2.3 Deterministic checks

Assertions assert against ground truth, never model judgment:

- **Workflow status** — e.g. `expect(spec.validStatuses).toContain(status)` where valid statuses are explicit (`["COMPLETED", "FAILED"]`).
- **Task audit** — confirm the expected tool/MCP/CLI task ran and reached the expected status using the task finders.
- **Substring presence/absence** — `notContains` (e.g. a leaked credit-card/SSN/marker string must NOT appear after a guardrail blocks/fixes) and `contains` (e.g. a `[REDACTED]` marker MUST appear after a fix policy).

Example — Suite 17 (`test_suite17_guardrail_matrix.test.ts`) is the canonical pattern. It builds a 3×3×3 matrix: position (agent output, tool input, tool output) × type (regex, LLM, custom) × policy (retry, raise, fix) = 27 specs. In `beforeAll` all 27 workflows fire concurrently via `runtime.start(agent, prompt)`, then a round-robin poll loop calls `handle.getStatus()` until `isComplete` or an 8-min budget elapses (workflows still pending are marked `TIMEOUT`). Each `it` then calls `checkResult(num)`, which asserts the workflow reached one of `validStatuses` and applies the `contains`/`notContains` substring checks only when `status === "COMPLETED"`. The guardrail policies/patterns themselves are deterministic (regex patterns, custom JS functions like `MARKER42 → [REDACTED]`); the LLM-type guardrails are part of the system under test, not the validator.

If `checkServerHealth()` fails in `beforeAll`, the suite throws (skips) rather than producing false failures.

---

## 3. Validation Framework (examples quality)

This is the LLM-in-the-loop harness for examples QA (`sdk/typescript/validation/`). It is the one place an LLM is used for validation — for judging output quality/equivalence, which the project rule explicitly permits.

### 3.1 Design principles

| Principle | Decision |
|-----------|----------|
| Tools are NOT optional | Every `tool_call` must have a successful `tool_result`. No silent failures. |
| Event-level auditing | Check individual events, not just workflow status. |
| LLM-in-the-loop verification | Every agent with a model must produce thinking events. |
| Dual execution for 3P | Framework examples run both natively and on Conductor (passthrough). |
| PASS = algorithmic green + judge ≥ 3 | Both must pass, not just one. |

### 3.2 Two execution modes

- **Mode 1 — Conductor execution:** run the example via `npx tsx`, collect events from the SSE stream, run algorithmic checks, LLM-judge the output.
- **Mode 2 — Native framework execution (3P only):** bypass Conductor, call the framework SDK directly, collect output, and LLM-judge native vs Conductor output for equivalence. Selected via `native = true` in the run config, which sets `AGENTSPAN_NATIVE_MODE=1`; each framework example carries both execution paths and branches on that env var.

### 3.3 Algorithmic checks (`validation/checks/`)

```typescript
interface AlgorithmicChecks {
  workflowCompleted: boolean;
  noUnhandledErrors: boolean;
  toolAudit: ToolAuditEntry[];
  allToolsSucceeded: boolean;
  llmEngaged: boolean;
  outputNonEmpty: boolean;
}
```

- **Tool audit** (`event-audit.ts`): for each `tool_call`, walk forward for a matching non-error `tool_result` (`succeeded`); on error, look for a subsequent successful retry of the same tool (`retriedAndFixed`); otherwise `failedPermanently`. `allToolsSucceeded = toolAudit.every(t => t.succeeded || t.retriedAndFixed)`.
- **LLM engagement**: `events.some(e => e.type === 'thinking')`. Relaxed to just `workflowCompleted` for framework-passthrough groups (`VERCEL_AI`, `LANGGRAPH`, `LANGCHAIN`, `OPENAI`, `ADK`), where the framework handles LLM calls internally.
- **Error detection**: an `error` event is a failure unless followed by a successful retry of the same operation.

### 3.4 LLM judge (`validation/judge/`)

- **Individual scoring** (1–5 rubric): 1 = failed/empty/unrelated … 5 = fully addresses prompt.
- **Framework comparison scoring** (1–5): compares Conductor vs native output; different-but-valid approaches = 5, both failed = 3, native failed but Conductor succeeded = 5.
- **PASS criteria:** `PASS = allAlgorithmicChecksGreen && judgeScore >= 3`; `WARN = green && judgeScore < 3`; `FAIL = anyAlgorithmicCheckFailed` regardless of score.
- **Caching** (`cache.ts`): output hashed (SHA-256, first 16 chars); matching hash reuses the prior score, stored in `output/judge_cache.json`.

### 3.5 Executor, config, reporting

- **Executor** (`executor.ts`): subprocess `npx tsx <examplePath>`, capturing stdout/stderr/exit code/duration; parses output, tool-call count, status, and execution ID from stdout boundary markers. Parallel via a concurrency limiter (`max_workers`, default 8) with `AbortController` support.
- **Config** (`config.ts`, `runs.toml.example`): TOML with `[defaults]`, `[judge]` (model, thresholds, rate limit), and `[[runs]]` entries (name, model, group, optional `native = true`).
- **Discovery / groups** (`discovery.ts`, `groups.ts`): examples grouped as `SMOKE_TEST`, `VERCEL_AI`, `LANGGRAPH`, `LANGCHAIN`, `OPENAI`, `ADK`, `ALL`.
- **Reporting** (`reporting/`): `json.ts` machine-readable results; `html.ts` a score heatmap, summary cards, filters, dark mode, and per-example expandable detail incl. native-vs-Conductor side-by-side.

### 3.6 Framework comparison fixture

`tests/validation/vercel-ai-comparison.ts` is a standalone native-vs-Conductor comparison fixture for the Vercel AI framework wrapper, mirroring the dual-execution path above.

### 3.7 CLI

```bash
npx tsx validation/runner.ts --config validation/runs.toml          # run configured runs
npx tsx validation/runner.ts --config runs.toml --group VERCEL_AI   # one group
npx tsx validation/runner.ts --config runs.toml --judge --report    # judge + HTML report
npx tsx validation/runner.ts --config runs.toml --dry-run           # list, don't execute
npx tsx validation/runner.ts --config runs.toml --run 01-basic-agent,02-tools
```

---

## 4. Running Locally + CI

### 4.1 vitest configuration (`sdk/typescript/vitest.config.ts`)

- Aliases `@conductoross/conductor-agent-sdk` → `src/index.ts`, so tests exercise local source without a build step.
- Enables decorator support (`experimentalDecorators`, `emitDecoratorMetadata`).
- `pool: 'forks'` with `maxForks: 3` — runs 3 test files concurrently; credential names are unique per suite so suites don't collide, and suites 17/18 use no credentials.
- `testTimeout: 60_000`; suites with long-running workflow polling set their own per-`describe`/`beforeAll` budgets (e.g. Suite 17: 600 s describe timeout, 480 s internal poll budget).
- `include: ['tests/**/*.test.ts', '../../tests/e2e/*.test.ts']`; reporters `verbose` + `junit` → `../../e2e-results/junit-ts.xml`.

### 4.2 Running locally

Prerequisites: a running server (default `http://localhost:6767/api`), `mcp-testkit` on `:3001` for MCP suites, and `OPENAI_API_KEY` (and/or `ANTHROPIC_API_KEY`).

```bash
cd sdk/typescript
npm ci && npm run build

# Unit tests
npx vitest run tests/unit/

# Deterministic E2E (all suites)
npx vitest run tests/e2e/

# A single suite
npx vitest run tests/e2e/test_suite17_guardrail_matrix.test.ts

# HTML report from junit output
npx tsx tests/e2e/generate-report.ts ../../e2e-results/junit-ts.xml ../../e2e-results/report-ts.html
```

`npm test` runs `vitest run`. Suites self-skip (throw in `beforeAll`) if `checkServerHealth()` fails, so they never produce false failures against an absent server.

### 4.3 CI integration (`.github/workflows/ci.yml`)

- **`typescript-unit-tests`** — runs `npx vitest run tests/unit/` (fast, no server).
- **`typescript-e2e`** — `needs: [build-server, typescript-unit-tests]`, 45-min timeout. Steps: download the prebuilt server JAR, `go build -o agentspan` the CLI, `pip install mcp-testkit` and start it on `:3001`, launch the server on `:6767` and health-poll `/health`, `npm ci && npm run build`, then:
  ```
  npx vitest run tests/e2e/ --reporter=verbose --reporter=junit \
    --outputFile.junit=../../e2e-results/junit-ts.xml
  ```
  Then (always) `generate-report.ts` produces `report-ts.html`, and `e2e-results/` is uploaded as the `typescript-e2e-results` artifact (14-day retention). Env: `AGENTSPAN_SERVER_URL=http://localhost:6767/api`, `AGENTSPAN_CLI_PATH=../../cli/agentspan`, plus provider API keys from secrets.

The examples-quality framework (§3) is not wired into CI; it is run on demand for examples QA.
