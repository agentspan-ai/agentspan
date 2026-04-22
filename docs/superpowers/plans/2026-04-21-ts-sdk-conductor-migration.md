# TS SDK Conductor Migration & Lease Extension

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the custom fetch-based `WorkerManager` with `@io-orkes/conductor-javascript` SDK, then enable lease extension so long-running tasks survive via heartbeat.

**Architecture:** A thin `ConductorWorkerManager` adapter wraps the conductor SDK's `TaskManager`. All agentspan-specific middleware (ToolContext extraction, credential injection, state capture, circuit breaker, error mapping) runs inside each worker's `execute()` function. The adapter preserves the exact `addWorker()`/`startPolling()`/`stopPolling()` interface so `runtime.ts` changes are minimal.

**Tech Stack:** `@io-orkes/conductor-javascript@v3.0.3` (GitHub tag, not yet on npm), TypeScript, Node.js >=18

---

## File Structure

| File | Action | Responsibility |
|------|--------|----------------|
| `sdk/typescript/package.json` | Modify | Add `@io-orkes/conductor-javascript` dependency |
| `sdk/typescript/src/conductor-adapter.ts` | Create | `ConductorWorkerManager` adapter wrapping conductor SDK |
| `sdk/typescript/src/runtime.ts` | Modify | Swap `WorkerManager` → `ConductorWorkerManager`, await async start/stop |
| `sdk/typescript/src/worker.ts` | Keep | Utility functions stay; `WorkerManager` class kept but unused |
| `sdk/typescript/src/index.ts` | Modify | Export `ConductorWorkerManager` |
| `sdk/typescript/src/agent.ts` | Modify (Phase 2) | `timeoutSeconds` default `0` → `10` |

---

## Chunk 1: Phase 1 — Migration to Conductor SDK

### Task 1: Install conductor SDK dependency

**Files:**
- Modify: `sdk/typescript/package.json`

- [ ] **Step 1: Add dependency from GitHub tag**

```bash
cd sdk/typescript
npm install @io-orkes/conductor-javascript@github:conductor-oss/javascript-sdk#v3.0.3
```

If the GitHub install doesn't resolve the package name correctly, use the tarball URL instead:

```bash
npm install https://github.com/conductor-oss/javascript-sdk/archive/refs/tags/v3.0.3.tar.gz
```

- [ ] **Step 2: Verify the package installed correctly**

```bash
cd sdk/typescript
node -e "const pkg = require('./node_modules/@io-orkes/conductor-javascript/package.json'); console.log(pkg.name, pkg.version)"
```

Expected: `@io-orkes/conductor-javascript 3.0.3` (or similar)

If the import name is different, note it — all subsequent imports must use the actual name.

- [ ] **Step 3: Verify key exports are accessible**

```bash
cd sdk/typescript
npx tsx -e "
import { createConductorClient, TaskManager, NonRetryableException } from '@io-orkes/conductor-javascript';
console.log('createConductorClient:', typeof createConductorClient);
console.log('TaskManager:', typeof TaskManager);
console.log('NonRetryableException:', typeof NonRetryableException);
"
```

Expected: All three print their types. If any import fails, check the package's actual export paths and adjust.

- [ ] **Step 4: Commit**

```bash
git add sdk/typescript/package.json sdk/typescript/package-lock.json
git commit -m "feat(ts-sdk): add @io-orkes/conductor-javascript dependency from v3.0.3"
```

---

### Task 2: Create ConductorWorkerManager adapter

**Files:**
- Create: `sdk/typescript/src/conductor-adapter.ts`

The adapter must:
1. Collect workers via `addWorker()` (before start)
2. Initialize the conductor `Client` in `startPolling()` (async)
3. Wrap each handler with all agentspan middleware (ToolContext, credentials, state capture, circuit breaker, error mapping)
4. Create a `TaskManager` with the wrapped workers and start it
5. Stop the `TaskManager` in `stopPolling()`

- [ ] **Step 1: Create the adapter file**

Create `sdk/typescript/src/conductor-adapter.ts` with the following content:

```typescript
/**
 * Adapter that wraps @io-orkes/conductor-javascript TaskManager
 * while preserving all agentspan-specific worker middleware.
 *
 * Drop-in replacement for the raw fetch-based WorkerManager.
 */
import { createConductorClient, TaskManager, NonRetryableException } from "@io-orkes/conductor-javascript";
import type { ConductorWorker, Task, TaskResult } from "@io-orkes/conductor-javascript";
import type { WorkerHandler } from "./worker.js";
import {
  extractToolContext,
  stripInternalKeys,
  captureStateMutations,
  appendStateUpdates,
  isCircuitBreakerOpen,
  recordSuccess,
  recordFailure,
} from "./worker.js";
import { TerminalToolError } from "./errors.js";
import {
  extractExecutionToken,
  setCredentialContext,
  clearCredentialContext,
  resolveCredentials,
  injectCredentials,
} from "./credentials.js";

interface PendingWorker {
  taskName: string;
  handler: WorkerHandler;
  credentials?: string[];
}

/**
 * Bridges agentspan's worker registration model to the conductor SDK's TaskManager.
 *
 * Usage mirrors the old WorkerManager:
 *   1. addWorker(name, handler, creds?)   — queue workers
 *   2. await startPolling()               — init client + start TaskManager
 *   3. await stopPolling()                — graceful shutdown
 */
export class ConductorWorkerManager {
  /** Base Agentspan server URL (includes /api). */
  private readonly serverUrl: string;
  /** Auth headers for Agentspan API requests. */
  private readonly headers: Record<string, string>;
  /** Poll interval passed to each TaskRunner. */
  private readonly pollIntervalMs: number;

  /** Workers queued via addWorker() before startPolling(). */
  private pendingWorkers: PendingWorker[] = [];
  /** Active TaskManager (created on startPolling). */
  private taskManager: TaskManager | null = null;

  constructor(
    serverUrl: string,
    headers: Record<string, string>,
    pollIntervalMs: number = 100,
  ) {
    this.serverUrl = serverUrl;
    this.headers = headers;
    this.pollIntervalMs = pollIntervalMs;
  }

  /**
   * Queue a worker. Replaces any existing worker with the same task name.
   * Must be called BEFORE startPolling().
   */
  addWorker(taskName: string, handler: WorkerHandler, credentials?: string[]): void {
    const idx = this.pendingWorkers.findIndex((w) => w.taskName === taskName);
    if (idx >= 0) {
      this.pendingWorkers[idx] = { taskName, handler, credentials };
    } else {
      this.pendingWorkers.push({ taskName, handler, credentials });
    }
  }

  /**
   * No-op: task definitions are registered server-side during agent compilation.
   */
  async registerTaskDef(_taskName: string, _config?: { timeoutSeconds?: number }): Promise<void> {
    return;
  }

  /**
   * Initialize the conductor client and start polling for all queued workers.
   */
  async startPolling(): Promise<void> {
    // Stop any existing manager first
    await this.stopPolling();

    if (this.pendingWorkers.length === 0) return;

    // Conductor SDK paths include /api/ prefix, so strip it from the base URL.
    // Agentspan serverUrl: "http://host:port/api" → conductor baseUrl: "http://host:port"
    const conductorBaseUrl = this.serverUrl.replace(/\/api\/?$/, "");

    // Capture headers for the custom fetch closure
    const authHeaders = this.headers;

    const client = await createConductorClient(
      { serverUrl: conductorBaseUrl, disableHttp2: true },
      // Inject agentspan auth headers into every request
      (url: string | URL | Request, init?: RequestInit) => {
        const h = new Headers(init?.headers);
        for (const [k, v] of Object.entries(authHeaders)) {
          h.set(k, v);
        }
        return globalThis.fetch(url, { ...init, headers: h });
      },
    );

    // Convert pending workers to ConductorWorker[]
    const conductorWorkers = this.pendingWorkers.map((pw) =>
      this._wrapWorker(pw),
    );

    this.taskManager = new TaskManager(client, conductorWorkers, {
      options: { pollInterval: this.pollIntervalMs },
    });
    this.taskManager.startPolling();
  }

  /**
   * Stop polling and tear down the TaskManager.
   */
  async stopPolling(): Promise<void> {
    if (this.taskManager) {
      await this.taskManager.stopPolling();
      this.taskManager = null;
    }
  }

  // ── Private: wrap agentspan handler into ConductorWorker ──

  /**
   * Wrap an agentspan WorkerHandler into a conductor ConductorWorker.
   *
   * The execute() method reproduces the full middleware chain from the
   * old WorkerManager._pollAndExecute():
   *   1. Circuit breaker check
   *   2. ToolContext extraction
   *   3. State snapshot
   *   4. Internal key stripping
   *   5. __workflowInstanceId__ injection
   *   6. __toolContext__ injection
   *   7. Credential context setup
   *   8. Credential resolution + env injection
   *   9. Handler execution
   *  10. State mutation capture
   *  11. Output wrapping (primitives → object)
   */
  private _wrapWorker(pw: PendingWorker): ConductorWorker {
    const self = this;
    return {
      taskDefName: pw.taskName,
      pollInterval: this.pollIntervalMs,
      concurrency: 1,
      leaseExtendEnabled: true,

      async execute(
        task: Task,
      ): Promise<Omit<TaskResult, "workflowInstanceId" | "taskId">> {
        // 1. Circuit breaker
        if (isCircuitBreakerOpen(pw.taskName)) {
          throw new NonRetryableException(
            `Circuit breaker open for ${pw.taskName}`,
          );
        }

        const inputData: Record<string, unknown> = (task.inputData as Record<string, unknown>) ?? {};

        // 2. ToolContext extraction
        const toolContext = extractToolContext(inputData);

        // 3. State snapshot
        const stateSnapshot = toolContext ? { ...toolContext.state } : {};

        // 4. Strip internal keys
        const cleanedInput = stripInternalKeys(inputData);

        // 5. Inject workflowInstanceId for framework passthrough workers
        cleanedInput["__workflowInstanceId__"] = task.workflowInstanceId;

        // 6. Inject ToolContext
        if (toolContext) {
          cleanedInput["__toolContext__"] = toolContext;
        }

        // 7. Credential context setup
        const executionToken = extractExecutionToken(inputData);
        if (executionToken) {
          setCredentialContext(self.serverUrl, self.headers, executionToken);
        }

        // 8. Credential resolution + env injection
        let cleanupCredentials: (() => void) | null = null;
        if (pw.credentials?.length) {
          if (!executionToken) {
            throw new NonRetryableException(
              `Required credentials not found: ${pw.credentials.join(", ")}. ` +
              `No execution token available. Store credentials on the server with: agentspan credentials set --name <NAME>`,
            );
          }
          try {
            const resolved = await resolveCredentials(
              self.serverUrl,
              self.headers,
              executionToken,
              pw.credentials,
            );
            cleanupCredentials = injectCredentials(
              self.serverUrl,
              self.headers,
              executionToken,
              resolved,
            );
          } catch (err) {
            throw new NonRetryableException(
              `Credential resolution failed for ${pw.taskName}: ${err instanceof Error ? err.message : String(err)}`,
            );
          }
        }

        try {
          // 9. Execute handler
          let result = await pw.handler(cleanedInput);

          // 10. State mutation capture
          if (toolContext) {
            const updates = captureStateMutations(stateSnapshot, toolContext.state);
            if (updates) {
              result = appendStateUpdates(result, updates);
            }
          }

          // 11. Output wrapping — conductor expects outputData to be an object
          const outputData =
            result != null && typeof result === "object" && !Array.isArray(result)
              ? (result as Record<string, unknown>)
              : { result };

          recordSuccess(pw.taskName);
          return { status: "COMPLETED", outputData };
        } catch (error) {
          recordFailure(pw.taskName);

          // Map TerminalToolError → NonRetryableException
          if (error instanceof TerminalToolError) {
            throw new NonRetryableException(error.message);
          }
          throw error;
        } finally {
          cleanupCredentials?.();
          if (executionToken) {
            clearCredentialContext();
          }
        }
      },
    };
  }
}
```

- [ ] **Step 2: Verify it compiles**

```bash
cd sdk/typescript && npx tsc --noEmit src/conductor-adapter.ts
```

Expected: No errors. If there are import resolution issues with the conductor SDK types, adjust the import paths (e.g., the `Task` and `TaskResult` types may need to be imported from a sub-path).

Fix any type errors before proceeding.

- [ ] **Step 3: Commit**

```bash
git add sdk/typescript/src/conductor-adapter.ts
git commit -m "feat(ts-sdk): add ConductorWorkerManager adapter for conductor SDK integration"
```

---

### Task 3: Wire adapter into runtime.ts

**Files:**
- Modify: `sdk/typescript/src/runtime.ts:18,73,79-83,130,189,235,385,390,404,1205,1285,1305`

The changes:
1. Import `ConductorWorkerManager` instead of (or alongside) `WorkerManager`
2. Change the `workerManager` type and constructor call
3. `await` all `startPolling()` calls (now async)
4. `await` all `stopPolling()` calls (now async)

- [ ] **Step 1: Update import**

In `runtime.ts` line 18, change:

```typescript
import { WorkerManager } from "./worker.js";
```

to:

```typescript
import { ConductorWorkerManager } from "./conductor-adapter.js";
```

- [ ] **Step 2: Update type declaration and constructor**

In `runtime.ts` line 73, change:

```typescript
  private readonly workerManager: WorkerManager;
```

to:

```typescript
  private readonly workerManager: ConductorWorkerManager;
```

In `runtime.ts` lines 79-83, change:

```typescript
    this.workerManager = new WorkerManager(
      this.config.serverUrl,
      this.authHeaders,
      this.config.workerPollIntervalMs,
    );
```

to:

```typescript
    this.workerManager = new ConductorWorkerManager(
      this.config.serverUrl,
      this.authHeaders,
      this.config.workerPollIntervalMs,
    );
```

- [ ] **Step 3: Await startPolling() at all 4 call sites**

Line 130 (`run()`):
```typescript
// Before:
this.workerManager.startPolling();
// After:
await this.workerManager.startPolling();
```

Line 235 (`start()`):
```typescript
// Before:
this.workerManager.startPolling();
// After:
await this.workerManager.startPolling();
```

Line 385 (`serve()`):
```typescript
// Before:
this.workerManager.startPolling();
// After:
await this.workerManager.startPolling();
```

Line 1205 (`_runFramework()`):
```typescript
// Before:
this.workerManager.startPolling();
// After:
await this.workerManager.startPolling();
```

Line 1305 (`_startFramework()`):
```typescript
// Before:
this.workerManager.startPolling();
// After:
await this.workerManager.startPolling();
```

- [ ] **Step 4: Await stopPolling() at all call sites**

Line 189 (`run()` finally block):
```typescript
// Before:
this.workerManager.stopPolling();
// After:
await this.workerManager.stopPolling();
```

Line 390 (`serve()` onSignal):
```typescript
// Before:
this.workerManager.stopPolling();
// After:
// Note: signal handler closures can't be async directly.
// Wrap in void async or change pattern:
void this.workerManager.stopPolling().then(() => resolve());
// Remove the old: this.workerManager.stopPolling(); resolve();
```

Line 404 (`shutdown()`):
```typescript
// Before:
this.workerManager.stopPolling();
// After:
await this.workerManager.stopPolling();
```

Line 1285 (`_runFramework()` finally block):
```typescript
// Before:
this.workerManager.stopPolling();
// After:
await this.workerManager.stopPolling();
```

- [ ] **Step 5: Verify it compiles**

```bash
cd sdk/typescript && npx tsc --noEmit
```

Expected: No errors. Fix any issues.

- [ ] **Step 6: Run build**

```bash
cd sdk/typescript && npm run build
```

Expected: Build succeeds.

- [ ] **Step 7: Commit**

```bash
git add sdk/typescript/src/runtime.ts
git commit -m "feat(ts-sdk): wire ConductorWorkerManager into runtime, replacing raw fetch WorkerManager"
```

---

### Task 4: Update exports in index.ts

**Files:**
- Modify: `sdk/typescript/src/index.ts:100-114`

- [ ] **Step 1: Add ConductorWorkerManager export**

Add after the existing Worker Manager section (around line 114):

```typescript
// ── Conductor Adapter ──────────────────────────────────
export { ConductorWorkerManager } from "./conductor-adapter.js";
```

Keep the existing `WorkerManager` export for backward compatibility — it's still importable but no longer used internally.

- [ ] **Step 2: Build to verify exports**

```bash
cd sdk/typescript && npm run build
```

Expected: Build succeeds.

- [ ] **Step 3: Commit**

```bash
git add sdk/typescript/src/index.ts
git commit -m "feat(ts-sdk): export ConductorWorkerManager from public API"
```

---

### Task 5: Run existing tests to verify no regression

- [ ] **Step 1: Run unit tests**

```bash
cd sdk/typescript && npm test
```

Expected: All existing unit tests pass. The unit tests don't test `WorkerManager` directly (none exist), so they should all pass.

- [ ] **Step 2: Run typecheck**

```bash
cd sdk/typescript && npm run typecheck
```

Expected: No type errors.

- [ ] **Step 3: Run lint**

```bash
cd sdk/typescript && npm run lint
```

Expected: No lint errors (or only pre-existing ones).

---

### Task 6: Run e2e tests

This is the critical validation — existing e2e tests exercise the full worker lifecycle.

- [ ] **Step 1: Run the e2e test suite**

```bash
cd sdk/typescript && npm run test:e2e
```

Or if e2e tests require a running server:

```bash
cd sdk/typescript && AGENTSPAN_SERVER_URL=http://localhost:6767/api npx vitest run tests/e2e/
```

Expected: All e2e tests pass. If any fail, debug the adapter — the issue is likely in:
- Server URL construction (double `/api/api/` path)
- Auth header injection
- Output format differences between TaskResult and the old reportSuccess format
- Error handling differences

**Debugging tip:** If you see 404s from the conductor SDK, the server URL path is likely wrong. Check whether the conductor SDK's generated paths include `/api/` or not, and adjust `conductorBaseUrl` accordingly. The plan assumes paths include `/api/` so we strip it from the Agentspan URL.

- [ ] **Step 2: Commit if all pass**

```bash
git add -A
git commit -m "test(ts-sdk): verify e2e tests pass with conductor SDK migration"
```

---

## Chunk 2: Phase 2 — Enable Lease Extension

### Task 7: Change timeoutSeconds default

**Files:**
- Modify: `sdk/typescript/src/agent.ts:200`

With the conductor SDK and `leaseExtendEnabled: true` (already set in the adapter), heartbeats keep tasks alive past the `responseTimeoutSeconds` window. It's now safe to change the default.

- [ ] **Step 1: Change default from 0 to 10**

In `agent.ts` line 200, change:

```typescript
this.timeoutSeconds = options.timeoutSeconds ?? 0;
```

to:

```typescript
this.timeoutSeconds = options.timeoutSeconds ?? 10;
```

- [ ] **Step 2: Update unit tests that assert on the default**

Check `tests/unit/agent.test.ts` and `tests/unit/serializer.test.ts` for assertions like `expect(a.timeoutSeconds).toBe(0)` and change them to `toBe(10)`.

```bash
cd sdk/typescript && grep -rn "timeoutSeconds.*toBe(0)" tests/
```

Update each match.

- [ ] **Step 3: Run unit tests**

```bash
cd sdk/typescript && npm test
```

Expected: All pass with updated assertions.

- [ ] **Step 4: Commit**

```bash
git add sdk/typescript/src/agent.ts sdk/typescript/tests/
git commit -m "feat(ts-sdk): change timeoutSeconds default to 10s (lease extension keeps tasks alive)"
```

---

### Task 8: Write e2e lease extension test

**Files:**
- Create: `sdk/typescript/tests/e2e/test_lease_extension.test.ts`

This test proves the heartbeat mechanism works end-to-end: a tool that sleeps >10s completes successfully instead of timing out.

- [ ] **Step 1: Write the test**

```typescript
import { describe, it, expect } from "vitest";
import { Agent, AgentRuntime, tool } from "../../src/index.js";

const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));

// Tool that takes 15s — well past the 10s responseTimeoutSeconds.
// Without lease extension heartbeats the task would time out.
const slowComputation = tool(
  async (input: { query: string }) => {
    await sleep(15_000);
    return { result: `Computed: ${input.query}`, elapsed: 15 };
  },
  {
    name: "slow_computation",
    description: "Run a computation that takes a while to complete.",
    parameters: {
      type: "object",
      properties: {
        query: { type: "string", description: "The query to compute" },
      },
      required: ["query"],
    },
  },
);

describe("Lease Extension", () => {
  it("long-running tool completes with lease extension heartbeats", async () => {
    const runtime = new AgentRuntime();
    const agent = new Agent({
      name: `e2e_lease_${Date.now()}`,
      model: process.env.AGENTSPAN_LLM_MODEL || "openai/gpt-4o-mini",
      tools: [slowComputation],
      instructions:
        "Use the slow_computation tool to answer. Always call the tool.",
    });

    const result = await runtime.run(
      agent,
      "Run a slow computation for 'lease test'.",
    );

    // Primary assertion: completed, not timed out
    expect(result.status).toBe("COMPLETED");
    expect(result.output).toBeTruthy();
  }, 120_000); // 2 minute timeout for the test itself
});
```

- [ ] **Step 2: Run the test**

```bash
cd sdk/typescript && AGENTSPAN_SERVER_URL=http://localhost:6767/api npx vitest run tests/e2e/test_lease_extension.test.ts
```

Expected: PASS — the tool sleeps 15s but heartbeats keep the lease alive past the 10s timeout.

- [ ] **Step 3: Commit**

```bash
git add sdk/typescript/tests/e2e/test_lease_extension.test.ts
git commit -m "test(ts-sdk): add e2e test proving lease extension keeps long-running tasks alive"
```

---

### Task 9: Update design doc

**Files:**
- Modify: `docs/design/lease-extension-and-ts-sdk-migration.md`

- [ ] **Step 1: Update the gap table**

In the gap table, update the TS SDK rows:

```markdown
| Conductor JS SDK (`@io-orkes/conductor-javascript`) | **Yes** (v3.0.3) | N/A — is the SDK |
| Agentspan TS SDK | **Yes** — all workers set `leaseExtendEnabled: true`, `timeoutSeconds: 10` | **Yes** — uses `@io-orkes/conductor-javascript` v3.0.3 |
```

- [ ] **Step 2: Mark Phase 2 as complete**

Add completion notes to the implementation order section, marking all Phase 2 steps as done.

- [ ] **Step 3: Resolve remaining open questions**

Update open questions 1-4 with resolution notes (e.g., Q1: "Resolved — contributed to conductor-oss, released as v3.0.3").

- [ ] **Step 4: Commit**

```bash
git add docs/design/lease-extension-and-ts-sdk-migration.md
git commit -m "docs: update design doc — TS SDK migration and lease extension complete"
```

---

## Key Design Decisions

### Auth bridging
The conductor SDK supports a custom `fetch` function. We inject agentspan's auth headers (`Authorization: Bearer ...` or `X-Auth-Key`/`X-Auth-Secret`) into every request. No key/secret auth needed.

### Server URL
Conductor SDK generated paths include `/api/` prefix (e.g., `/api/tasks/poll/batch/{tasktype}`). Agentspan's `config.serverUrl` already includes `/api`. The adapter strips it: `serverUrl.replace(/\/api\/?$/, "")`.

### Error mapping
`TerminalToolError` (agentspan) → `NonRetryableException` (conductor SDK) → `FAILED_WITH_TERMINAL_ERROR` status. Regular errors → `FAILED` (retryable).

### HTTP/2
Disabled via `disableHttp2: true`. The agentspan server is tested with HTTP/1.1. Can be enabled later if needed.

### Lease extension
Set `leaseExtendEnabled: true` on all workers in the adapter. The conductor SDK's `LeaseTracker` sends heartbeats at 80% of `responseTimeoutSeconds` (8s for a 10s timeout). This matches the Python SDK behavior.
