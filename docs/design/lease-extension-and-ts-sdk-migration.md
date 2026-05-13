# Lease Extension & TS SDK Conductor Migration

**Date:** 2026-04-18 (updated 2026-04-21)
**Status:** Draft
**Scope:** Conductor JS SDK lease extension, Agentspan TS SDK migration, Agentspan Python SDK integration

---

## Problem

Agentspan workers execute tasks that can exceed the Conductor server's `responseTimeoutSeconds` window (e.g., LLM calls, tool executions, framework passthrough). When a task exceeds its timeout, Conductor marks it as timed out and may reschedule it — causing duplicate execution, wasted compute, and user-visible failures.

**Current gaps:**

| Component | Lease Extension | Uses Conductor SDK |
|---|---|---|
| Conductor Python SDK (`conductor-python`) | Yes (added on `lease_extend` branch) | N/A — is the SDK |
| Conductor JS SDK (`@io-orkes/conductor-javascript`) | **No** | N/A — is the SDK |
| Agentspan Python SDK | Yes — all workers set `lease_extend_enabled=True`, `response_timeout_seconds=10` | Yes — uses `conductor-python` |
| Agentspan TS SDK | **No** — `timeoutSeconds` default is `0` (disabled) until lease extension is added | **No** — custom `fetch`-based `WorkerManager` |

---

## Goals

1. **Add lease extension to Conductor JS SDK** — port the heartbeat mechanism from `conductor-python`
2. **Migrate Agentspan TS SDK** from custom `WorkerManager` to `@io-orkes/conductor-javascript`
3. **Enable lease extension by default** for all Agentspan TS workers (matching Python SDK behavior)

---

## Part 1: Lease Extension for Conductor JS SDK

### 1.1 How It Works (Python Reference)

The Python SDK implementation (on the `lease_extend` branch) follows this pattern:

```
Poll loop iteration:
  1. _send_due_heartbeats()     ← check all tracked tasks, send heartbeats for overdue ones
  2. poll for new task
  3. execute task (in thread pool)
     ├─ _track_lease(task)      ← start tracking before execution
     ├─ run worker function
     ├─ _untrack_lease(task_id) ← stop tracking after completion
     └─ update task result (v2 chaining may return next task)
```

**Heartbeat mechanism:**
- `TaskResult` with `extend_lease: true` sent via `POST /tasks` (same update endpoint)
- Server resets `task.updateTime`, giving a fresh `responseTimeoutSeconds` window
- Interval: 80% of `responseTimeoutSeconds` (constant: `LEASE_EXTEND_DURATION_FACTOR = 0.8`)
- Retry: 3 attempts with backoff (`0.5 * (attempt + 2)` seconds)

**Key data structure:**
```typescript
interface LeaseInfo {
  taskId: string;
  workflowInstanceId: string;
  responseTimeoutSeconds: number;
  lastHeartbeatTime: number;    // performance.now() or Date.now()
  intervalMs: number;           // responseTimeoutSeconds * 0.8 * 1000
}
```

### 1.2 Design for JS SDK

**Files to create/modify in `conductor-oss/javascript-sdk`:**

#### New: `src/worker/lease_tracker.ts`

Shared constants and LeaseInfo interface (mirrors Python's `lease_tracker.py`):

```typescript
export const LEASE_EXTEND_RETRY_COUNT = 3;
export const LEASE_EXTEND_DURATION_FACTOR = 0.8;

export interface LeaseInfo {
  taskId: string;
  workflowInstanceId: string;
  responseTimeoutSeconds: number;
  lastHeartbeatTime: number;
  intervalMs: number;
}
```

#### Modified: `src/worker/TaskRunner.ts`

Add lease tracking to the existing `TaskRunner` class:

```
class TaskRunner {
  // Existing fields...
  private leaseInfo: Map<string, LeaseInfo> = new Map();
  private leaseExtendEnabled: boolean;

  // New methods:
  trackLease(task: Task): void
  untrackLease(taskId: string): void
  sendDueHeartbeats(): Promise<void>
  sendHeartbeat(info: LeaseInfo): Promise<void>
}
```

**Integration with existing poll loop:**

The JS SDK's `TaskRunner` uses a `Poller` that calls a `performWorkFunction`. The heartbeat check needs to run at the start of each poll cycle:

```
Poller.poll()
  → TaskRunner.performWork()
      1. await this.sendDueHeartbeats()   ← NEW: check and send heartbeats
      2. execute task handler
      3. update task result (v2 chaining)
```

**Alternative (preferred):** Since the JS SDK's `Poller` is fire-and-forget (dispatches task execution asynchronously), heartbeats should run on a **separate timer** rather than coupling to the poll loop:

```
TaskRunner.start():
  - Start Poller (existing)
  - Start heartbeat interval: setInterval(sendDueHeartbeats, 1000)

TaskRunner.stop():
  - Stop Poller (existing)
  - Clear heartbeat interval
```

This is cleaner because:
- Poll interval (100ms default) is too frequent for heartbeat checks
- Task execution is async/fire-and-forget — heartbeats must continue during execution
- Decoupled timer avoids blocking the poll loop with heartbeat I/O

**Heartbeat check frequency:** 1 second is sufficient since the minimum meaningful heartbeat interval is `1s * 0.8 = 0.8s` (for a 1s timeout). In practice, timeouts are 10s+ so the 1s check granularity has negligible overhead.

#### Modified: `src/worker/TaskHandler.ts`

Pass `leaseExtendEnabled` from worker config to `TaskRunner`:

```typescript
// In WorkerConfig or equivalent
interface WorkerConfig {
  // existing...
  leaseExtendEnabled?: boolean;  // default: false (SDK-level default)
}
```

#### API call

The heartbeat uses the same task update endpoint:

```typescript
// POST /tasks (or /api/tasks/update-v2)
{
  taskId: info.taskId,
  workflowInstanceId: info.workflowInstanceId,
  status: "IN_PROGRESS",  // required — TaskResult defaults to IN_PROGRESS in Python SDK
  extendLease: true
}
```

**Note:** The Python SDK's `TaskResult` constructor defaults `status` to `IN_PROGRESS` when not explicitly set. The JS implementation must include this — omitting `status` may cause the server to reject the update or mark the task as completed.

The JS SDK already has `updateTask()` / `updateTaskV2()` in its `TaskResource`. The heartbeat should use the same codepath. Verify the `extendLease` field is supported in the existing `TaskResult` type — if not, add it.

### 1.3 Async Safety

The JS SDK runs entirely in a single event loop (Node.js), so no mutex/lock is needed for the `leaseInfo` Map — matching the Python async runner's approach. The only concern is ensuring `sendDueHeartbeats()` doesn't overlap with itself if a previous invocation is still in-flight. Use a simple guard flag:

```typescript
private heartbeatInProgress = false;

async sendDueHeartbeats(): Promise<void> {
  if (this.heartbeatInProgress) return;
  this.heartbeatInProgress = true;
  try {
    // ... check and send
  } finally {
    this.heartbeatInProgress = false;
  }
}
```

### 1.4 Task Lifecycle Integration

Track/untrack must wrap the entire task execution:

```
onTaskReceived(task):
  trackLease(task)
  try:
    result = await executeHandler(task)
    untrackLease(task.taskId)
    nextTask = await updateTask(result)  // v2 chaining
    if nextTask:
      trackLease(nextTask)
      // ... continue
  catch:
    untrackLease(task.taskId)
  finally:
    // Safety net — untrack if still tracked
    untrackLease(task.taskId)
```

### 1.5 Worker Crash / Restart Behavior

If a worker process dies (OOM, deploy, exception) while tasks are lease-tracked:
- The heartbeat timer stops — no more heartbeats are sent
- The server times out the task after `responseTimeoutSeconds` and retries it
- When workers restart and resume polling, the server dispatches the retried task to the new workers
- **No graceful shutdown logic needed** — the server handles recovery automatically

### 1.6 Cleanup

On `TaskRunner.stop()` or `TaskHandler.stopWorkers()`:
- Clear the heartbeat interval
- Clear the `leaseInfo` Map (no need to send final heartbeats — server will time out naturally)

---

## Part 2: Agentspan TS SDK Migration

### 2.1 Current Architecture (Custom)

The agentspan TS SDK (`sdk/typescript/`) has a hand-rolled `WorkerManager` in `src/worker.ts`:

```
WorkerManager
  ├─ addWorker(taskName, handler, credentials?)
  ├─ startPolling()  → setInterval per worker
  ├─ stopPolling()   → clearInterval
  ├─ pollTask()      → GET /tasks/poll/{taskType}
  └─ _pollAndExecute()
       ├─ Circuit breaker check
       ├─ Poll for task
       ├─ Extract ToolContext from __agentspan_ctx__
       ├─ Strip internal keys
       ├─ Resolve & inject credentials
       ├─ Execute handler
       ├─ Capture state mutations
       └─ Report success/failure via POST /tasks
```

**Key agentspan-specific behaviors** that must survive migration:
1. **ToolContext extraction** — reads `__agentspan_ctx__` from inputData, provides `workflowInstanceId` to handler
2. **Credential resolution** — extracts execution token, resolves credential secrets, injects into `process.env`
3. **State mutation capture** — diffs agent state before/after execution, sends `_state_updates`
4. **Internal key stripping** — removes `_agent_state`, `method`, `__agentspan_ctx__` before passing to handler
5. **Value coercion** — converts string↔object, string↔number, string↔boolean per spec §14.1
6. **Circuit breaker** — disables failing tools after threshold
7. **Terminal error distinction** — `TerminalToolError` → `FAILED_WITH_TERMINAL_ERROR` vs retryable `FAILED`

### 2.2 Target Architecture

```
@io-orkes/conductor-javascript
  └─ TaskHandler
       └─ TaskManager
            └─ TaskRunner (per worker, with lease extension)
                 └─ Poller → batchPoll()

Agentspan wrapper layer:
  └─ AgentspanWorkerManager (thin adapter)
       ├─ Creates TaskHandler with conductor SDK
       ├─ Wraps handlers to inject agentspan-specific behavior:
       │    ├─ ToolContext extraction
       │    ├─ Credential resolution
       │    ├─ State mutation capture
       │    ├─ Value coercion
       │    └─ Circuit breaker
       ├─ Configures lease extension per worker
       └─ Maps agentspan errors to conductor task statuses
```

### 2.3 Migration Strategy

**Phase 1: Add `@io-orkes/conductor-javascript` dependency**

```json
// sdk/typescript/package.json
{
  "dependencies": {
    "dotenv": "^16.0.0",
    "@io-orkes/conductor-javascript": "^3.0.2"
  }
}
```

**Phase 2: Create adapter layer**

New file: `src/conductor-adapter.ts`

This wraps the conductor SDK's `TaskHandler` while preserving all agentspan-specific behavior:

```typescript
import { TaskHandler, WorkerConfig } from "@io-orkes/conductor-javascript";

export class ConductorWorkerManager {
  private taskHandler: TaskHandler;
  private workers: Map<string, AgentspanWorkerEntry>;

  constructor(serverUrl: string, authConfig: AuthConfig, pollIntervalMs: number) {
    // Initialize conductor client
    // Create TaskHandler
  }

  addWorker(taskName: string, handler: Function, credentials?: string[]): void {
    // Wrap handler with agentspan middleware:
    //   1. ToolContext extraction
    //   2. Credential resolution
    //   3. State mutation capture
    //   4. Value coercion
    //   5. Circuit breaker
    // Register with TaskHandler
  }

  async startPolling(): Promise<void> {
    await this.taskHandler.startWorkers();
  }

  async stopPolling(): Promise<void> {
    await this.taskHandler.stopWorkers();
  }
}
```

**Phase 3: Replace `WorkerManager` usage in `runtime.ts`**

```typescript
// Before:
this.workerManager = new WorkerManager(
  this.config.serverUrl,
  this.authHeaders,
  this.config.workerPollIntervalMs,
);

// After:
this.workerManager = new ConductorWorkerManager(
  this.config.serverUrl,
  this.authConfig,
  this.config.workerPollIntervalMs,
);
```

The `ConductorWorkerManager` must expose the same interface as the current `WorkerManager`:
- `addWorker(taskName, handler, credentials?)`
- `startPolling()`
- `stopPolling()`

This keeps changes in `runtime.ts` minimal.

**Phase 4: Enable lease extension**

All workers registered through `ConductorWorkerManager` should have `leaseExtendEnabled: true` by default:

```typescript
addWorker(taskName: string, handler: Function, credentials?: string[]): void {
  const config: WorkerConfig = {
    taskDefName: taskName,
    pollInterval: this.pollIntervalMs,
    leaseExtendEnabled: true,  // always on for agentspan
    concurrency: 1,
  };
  // ... register
}
```

### 2.4 What Gets Removed

- `src/worker.ts` — the custom `WorkerManager` class (replaced by `ConductorWorkerManager`)
- Manual `fetch()` calls for `GET /tasks/poll/` and `POST /tasks`
- Custom polling interval management (`setInterval`/`clearInterval`)

**What stays in `src/worker.ts`** (or moves to `src/conductor-adapter.ts`):
- `coerceValue()` — agentspan-specific type coercion
- `extractToolContext()` — agentspan-specific context extraction
- `stripInternalKeys()` — agentspan-specific key filtering
- `captureStateMutations()` / `appendStateUpdates()` — agentspan-specific state tracking
- Circuit breaker functions — agentspan-specific error handling
- Credential resolution logic — agentspan-specific auth

### 2.5 Auth Mapping

Current agentspan TS SDK uses static headers:
```typescript
new WorkerManager(serverUrl, { "X-Authorization": token }, pollIntervalMs)
```

Conductor JS SDK uses `OrkesApiConfig`:
```typescript
{
  serverUrl: "...",
  keyId: "...",
  keySecret: "...",
}
```

The adapter needs to bridge this. Options:
1. **If agentspan uses key/secret auth:** Pass `keyId`/`keySecret` to `OrkesApiConfig`
2. **If agentspan uses token auth:** The conductor SDK supports custom headers — inject via config or interceptor
3. **Check if conductor SDK supports raw header injection** — if not, may need a small PR

### 2.6 Task Definition Registration

Current agentspan TS SDK: `registerTaskDef()` is a no-op (server handles it during agent compilation).

After migration: Set `registerTaskDef: false` in conductor SDK config to maintain the same behavior. The conductor SDK supports this — `WorkerConfig.registerTaskDef` defaults to `false`.

### 2.7 Risks & Considerations

| Risk | Mitigation |
|---|---|
| Bundle size increase from conductor SDK dependency | Conductor SDK has minimal deps (`reflect-metadata`, optional `undici`). Acceptable trade-off. |
| Breaking change in worker behavior | The adapter layer preserves the exact same handler interface. All agentspan-specific behavior lives in middleware wrappers. |
| Auth incompatibility | Investigate conductor SDK's auth model early. May need header injection support. |
| HTTP/2 behavior differences | Conductor SDK uses HTTP/2 by default (`undici`). Test with agentspan server. `disableHttp2: true` available as fallback. |
| V2 task update endpoint | Conductor SDK tries `/api/tasks/update-v2` first, falls back to `/api/tasks`. Agentspan server must support at least one. |

---

## Part 3: Agentspan Python SDK (Completed)

For reference, the Python SDK changes are already implemented:

### 3.1 Task Definition Defaults

**`runtime.py` — `_default_task_def()`:**
- `response_timeout_seconds`: 120 → **10**
- All other defaults unchanged (retry_count=2, timeout_seconds=0, etc.)

**`runtime.py` — `_passthrough_task_def()`:**
- `response_timeout_seconds`: 120 → **10**
- `timeout_seconds`: 600 (unchanged — overall task timeout for framework passthrough)

### 3.2 Lease Extension Enabled

All 17 `worker_task()` call sites now include `lease_extend_enabled=True`:

| Registration Path | File | Count |
|---|---|---|
| Native `@tool` workers | `tool_registry.py` | 1 |
| Framework workers (prepare) | `runtime.py` | 1 |
| Framework workers (register) | `runtime.py` | 1 |
| Passthrough workers | `runtime.py` | 1 |
| Graph workers | `runtime.py` | 1 |
| Skill workers | `runtime.py` | 1 |
| System workers (guardrails, router, handoff, etc.) | `runtime.py` | 10 |
| Late-registered workers | `worker_manager.py` | 1 (was already `True`) |

### 3.3 Conductor Python SDK

The `conductor-python` repo (`lease_extend` branch) implements the actual heartbeat mechanism:

- `lease_tracker.py` — shared `LeaseInfo` dataclass and constants
- `task_runner.py` — sync implementation with `threading.Lock`
- `async_task_runner.py` — async implementation (no lock, single event loop)

---

## Implementation Order

```
Phase 1: Conductor JS SDK — Lease Extension
  ├─ 1a. Add LeaseInfo type and constants (lease_tracker.ts)
  ├─ 1b. Add heartbeat methods to TaskRunner
  ├─ 1c. Add leaseExtendEnabled to WorkerConfig
  ├─ 1d. Wire heartbeat timer into TaskRunner lifecycle
  ├─ 1e. Add extendLease field to TaskResult type (if missing)
  └─ 1f. Test: verify heartbeat sent at 80% of responseTimeoutSeconds

Phase 2: Agentspan TS SDK — Migration
  ├─ 2a. Add @io-orkes/conductor-javascript dependency
  ├─ 2b. Create ConductorWorkerManager adapter
  ├─ 2c. Migrate agentspan-specific middleware (ToolContext, credentials, state, coercion)
  ├─ 2d. Replace WorkerManager in runtime.ts
  ├─ 2e. Enable leaseExtendEnabled=true for all workers
  ├─ 2f. Change timeoutSeconds default from 0 → 10 (safe now that heartbeats keep tasks alive)
  └─ 2g. E2E test: run agent, verify lease heartbeats in server logs

Phase 3: Validation
  ├─ 3a. Run existing agentspan e2e tests with new worker implementation
  ├─ 3b. Test long-running tool (>10s) — verify heartbeat keeps it alive
  ├─ 3c. Test framework passthrough (LangGraph/LangChain) — verify passthrough timeout works
  └─ 3d. Test credential resolution — verify secrets still inject correctly
```

---

## Open Questions

1. **Conductor JS SDK contribution model** — Is the lease extension a PR to `conductor-oss/javascript-sdk`, or a fork?
2. **Auth bridging** — Does the conductor JS SDK support raw header injection, or does agentspan need to adapt to key/secret auth?
3. **V2 task endpoint** — Does the agentspan server support `/api/tasks/update-v2`? If not, the conductor SDK will fall back to `/api/tasks` (which works, but without task chaining).
4. **`extendLease` in TaskResult** — Verify the conductor server accepts `extendLease: true` in the JS task update payload. The Python SDK sends `extend_lease=True` (snake_case) — confirm the JS API uses camelCase. The heartbeat must also include `status: "IN_PROGRESS"` (Python SDK's `TaskResult` defaults this).
5. ~~**Passthrough worker timeout**~~ **Resolved:** The TS SDK default `timeoutSeconds` is currently `0` (no timeout). It will be changed to `10` only after lease extension is wired in (Phase 2, step 2f). The TS SDK does not currently have a `_passthrough_task_def` equivalent — during migration, the adapter should allow per-worker timeout overrides for framework passthrough workers (matching Python's 600s `timeout_seconds` + 10s `response_timeout_seconds` pattern).
