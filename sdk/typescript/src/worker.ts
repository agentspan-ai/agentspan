import { createConductorClient, TaskManager, NonRetryableException } from "@io-orkes/conductor-javascript";
import type { ConductorWorker, Task, TaskResult } from "@io-orkes/conductor-javascript";
import type { ToolContext } from "./types.js";
import { TerminalToolError } from "./errors.js";
import {
  extractExecutionToken,
  setCredentialContext,
  clearCredentialContext,
  resolveCredentials,
  injectCredentials,
} from "./credentials.js";

// ── Type coercion (base spec §14.1) ─────────────────────

/**
 * Coerce a value from Conductor's type system to the expected target type.
 * All failures are silent — returns original value, never throws.
 */
export function coerceValue(value: unknown, targetType?: string): unknown {
  // Rule 1: null/empty or unknown target → return unchanged
  if (value == null || targetType == null || targetType === "") {
    return value;
  }

  const t = targetType.toLowerCase();

  // Rule 3: type match short-circuit
  if (t === "string" && typeof value === "string") return value;
  if (t === "number" && typeof value === "number") return value;
  if (t === "boolean" && typeof value === "boolean") return value;
  if ((t === "object" || t === "array") && typeof value === "object") return value;

  // Rule 4: String → object/array via JSON.parse
  if (typeof value === "string" && (t === "object" || t === "array")) {
    try {
      return JSON.parse(value);
    } catch {
      return value;
    }
  }

  // Rule 5: object/array → string via JSON.stringify
  if (typeof value === "object" && t === "string") {
    try {
      return JSON.stringify(value);
    } catch {
      return value;
    }
  }

  // Rule 6: String → number
  if (typeof value === "string" && t === "number") {
    const n = Number(value);
    if (Number.isNaN(n)) return value;
    return n;
  }

  // Rule 6: String → boolean
  if (typeof value === "string" && t === "boolean") {
    const lower = value.toLowerCase();
    if (lower === "true" || lower === "1" || lower === "yes") return true;
    if (lower === "false" || lower === "0" || lower === "no") return false;
    return value;
  }

  // Rule 7: Fallback — return unchanged
  return value;
}

// ── Circuit breaker (base spec §14.2) ───────────────────

const CIRCUIT_BREAKER_THRESHOLD = 10;

/** Per-tool consecutive failure counters. */
const failureCounts = new Map<string, number>();

/** Set of open (disabled) tool names. */
const openBreakers = new Set<string>();

/**
 * Record a failure for a tool. After threshold, open the breaker.
 */
export function recordFailure(toolName: string): void {
  const count = (failureCounts.get(toolName) ?? 0) + 1;
  failureCounts.set(toolName, count);
  if (count >= CIRCUIT_BREAKER_THRESHOLD) {
    openBreakers.add(toolName);
  }
}

/**
 * Record a success for a tool. Resets the failure counter.
 */
export function recordSuccess(toolName: string): void {
  failureCounts.set(toolName, 0);
  openBreakers.delete(toolName);
}

/**
 * Check if a tool's circuit breaker is open (disabled).
 */
export function isCircuitBreakerOpen(toolName: string): boolean {
  return openBreakers.has(toolName);
}

/**
 * Reset the circuit breaker for a specific tool.
 */
export function resetCircuitBreaker(toolName: string): void {
  failureCounts.delete(toolName);
  openBreakers.delete(toolName);
}

/**
 * Reset all circuit breakers.
 */
export function resetAllCircuitBreakers(): void {
  failureCounts.clear();
  openBreakers.clear();
}

// ── ToolContext extraction ───────────────────────────────

/**
 * Extract ToolContext from task inputData.
 * Reads `__agentspan_ctx__` from inputData and builds a ToolContext.
 */
export function extractToolContext(inputData: Record<string, unknown>): ToolContext | null {
  const ctx = inputData["__agentspan_ctx__"];
  if (ctx == null || typeof ctx !== "object") return null;

  const raw = ctx as Record<string, unknown>;
  return {
    sessionId: (raw.sessionId as string) ?? "",
    executionId: (raw.executionId as string) ?? "",
    agentName: (raw.agentName as string) ?? "",
    metadata: (raw.metadata as Record<string, unknown>) ?? {},
    dependencies: (raw.dependencies as Record<string, unknown>) ?? {},
    // Mutable copy of state
    state: { ...((raw.state as Record<string, unknown>) ?? {}) },
  };
}

// ── State mutation capture (spec §14.6 / §24.1) ────────

/**
 * Capture state mutations by diffing before/after snapshots.
 * Returns new state entries (added or modified keys).
 */
export function captureStateMutations(
  original: Record<string, unknown>,
  current: Record<string, unknown>,
): Record<string, unknown> | null {
  const updates: Record<string, unknown> = {};
  let hasUpdates = false;

  for (const [key, value] of Object.entries(current)) {
    if (!(key in original) || !deepEqual(original[key], value)) {
      updates[key] = value;
      hasUpdates = true;
    }
  }

  return hasUpdates ? updates : null;
}

/**
 * Append _state_updates to a tool result per spec §14.6.
 * - If result is an object: merge _state_updates key
 * - If result is not an object: wrap as { result: <original>, _state_updates: {...} }
 */
export function appendStateUpdates(
  result: unknown,
  stateUpdates: Record<string, unknown>,
): unknown {
  if (result != null && typeof result === "object" && !Array.isArray(result)) {
    return { ...(result as Record<string, unknown>), _state_updates: stateUpdates };
  }
  return { result, _state_updates: stateUpdates };
}

/** Simple deep equality check for state diffing. */
function deepEqual(a: unknown, b: unknown): boolean {
  if (a === b) return true;
  if (a == null || b == null) return false;
  if (typeof a !== typeof b) return false;
  if (typeof a !== "object") return false;

  const aObj = a as Record<string, unknown>;
  const bObj = b as Record<string, unknown>;
  const aKeys = Object.keys(aObj);
  const bKeys = Object.keys(bObj);
  if (aKeys.length !== bKeys.length) return false;

  for (const key of aKeys) {
    if (!deepEqual(aObj[key], bObj[key])) return false;
  }
  return true;
}

// ── Key stripping ───────────────────────────────────────

/**
 * Strip internal keys (_agent_state, method) from task inputData
 * before passing to handler.
 */
export function stripInternalKeys(inputData: Record<string, unknown>): Record<string, unknown> {
  const cleaned = { ...inputData };
  delete cleaned["_agent_state"];
  delete cleaned["method"];
  delete cleaned["__agentspan_ctx__"];
  return cleaned;
}

// ── WorkerManager ───────────────────────────────────────

export type WorkerHandler = (inputData: Record<string, unknown>) => Promise<unknown>;

interface PendingWorker {
  taskName: string;
  handler: WorkerHandler;
  credentials?: string[];
}

/**
 * Manages Conductor worker processes for tool functions.
 *
 * Thin lifecycle wrapper around conductor-javascript's {@link TaskManager},
 * mirroring the Python SDK's ``WorkerManager`` pattern.  Workers are
 * collected via {@link addWorker} and started/stopped as a group.
 *
 * All agentspan-specific middleware (ToolContext extraction, credential
 * injection, state capture, circuit breaker, error mapping) runs inside
 * each worker's ``execute()`` callback.
 */
export class WorkerManager {
  readonly serverUrl: string;
  readonly headers: Record<string, string>;
  readonly pollIntervalMs: number;

  private pendingWorkers: PendingWorker[] = [];
  private taskManager: TaskManager | null = null;

  constructor(serverUrl: string, headers: Record<string, string>, pollIntervalMs: number = 100) {
    this.serverUrl = serverUrl;
    this.headers = headers;
    this.pollIntervalMs = pollIntervalMs;
  }

  /**
   * Queue a worker for the given task name.
   * Replaces any existing worker with the same task name.
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
   * Create conductor client, build workers, start polling.
   */
  async startPolling(): Promise<void> {
    await this.stopPolling();
    if (this.pendingWorkers.length === 0) return;

    // Conductor SDK reads CONDUCTOR_SERVER_URL env var with priority over
    // config.serverUrl.  Override it so the SDK uses our configured URL
    // (from AgentConfig, which reads AGENTSPAN_SERVER_URL).
    const baseUrl = this.serverUrl.replace(/\/api\/?$/, "");
    process.env.CONDUCTOR_SERVER_URL = baseUrl;

    const authHeaders = this.headers;

    const client = await createConductorClient(
      { serverUrl: baseUrl, disableHttp2: true },
      (url: string | URL | Request, init?: RequestInit) => {
        // Conductor SDK passes Request objects — inject auth headers.
        if (url instanceof Request) {
          const h = new Headers(url.headers);
          for (const [k, v] of Object.entries(authHeaders)) h.set(k, v);
          return globalThis.fetch(new Request(url, { headers: h }));
        }
        const h = new Headers(init?.headers);
        for (const [k, v] of Object.entries(authHeaders)) h.set(k, v);
        return globalThis.fetch(url, { ...init, headers: h });
      },
    );

    const workers = this.pendingWorkers.map((pw) => this._wrapWorker(pw));
    this.taskManager = new TaskManager(client, workers, {
      options: { pollInterval: this.pollIntervalMs },
    });
    this.taskManager.startPolling();
  }

  /**
   * Stop the TaskManager.
   */
  async stopPolling(): Promise<void> {
    if (this.taskManager) {
      await this.taskManager.stopPolling();
      this.taskManager = null;
    }
  }

  /**
   * Wrap an agentspan handler into a {@link ConductorWorker}.
   *
   * Runs the full middleware chain: circuit breaker, ToolContext extraction,
   * credential injection, state capture, error mapping.
   */
  private _wrapWorker(pw: PendingWorker): ConductorWorker {
    const mgr = this;
    return {
      taskDefName: pw.taskName,
      pollInterval: this.pollIntervalMs,
      concurrency: 1,
      leaseExtendEnabled: true,

      async execute(
        task: Task,
      ): Promise<Omit<TaskResult, "workflowInstanceId" | "taskId">> {
        // Circuit breaker
        if (isCircuitBreakerOpen(pw.taskName)) {
          throw new NonRetryableException(`Circuit breaker open for ${pw.taskName}`);
        }

        const inputData = (task.inputData as Record<string, unknown>) ?? {};

        // ToolContext extraction + state snapshot
        const toolContext = extractToolContext(inputData);
        const stateSnapshot = toolContext ? { ...toolContext.state } : {};

        // Strip internal keys, inject runtime context
        const cleaned = stripInternalKeys(inputData);
        cleaned["__workflowInstanceId__"] = task.workflowInstanceId;
        if (toolContext) cleaned["__toolContext__"] = toolContext;

        // Credential setup
        const execToken = extractExecutionToken(inputData);
        if (execToken) setCredentialContext(mgr.serverUrl, mgr.headers, execToken);

        let cleanupCreds: (() => void) | null = null;
        if (pw.credentials?.length) {
          if (!execToken) {
            throw new NonRetryableException(
              `Required credentials not found: ${pw.credentials.join(", ")}. ` +
                `No execution token available.`,
            );
          }
          try {
            const resolved = await resolveCredentials(
              mgr.serverUrl,
              mgr.headers,
              execToken,
              pw.credentials,
            );
            cleanupCreds = injectCredentials(mgr.serverUrl, mgr.headers, execToken, resolved);
          } catch (err) {
            throw new NonRetryableException(
              `Credential resolution failed for ${pw.taskName}: ${err instanceof Error ? err.message : String(err)}`,
            );
          }
        }

        try {
          let result = await pw.handler(cleaned);

          // State mutation capture
          if (toolContext) {
            const updates = captureStateMutations(stateSnapshot, toolContext.state);
            if (updates) result = appendStateUpdates(result, updates);
          }

          // Wrap primitives — conductor expects outputData as an object
          const outputData =
            result != null && typeof result === "object" && !Array.isArray(result)
              ? (result as Record<string, unknown>)
              : { result };

          recordSuccess(pw.taskName);
          return { status: "COMPLETED", outputData };
        } catch (error) {
          recordFailure(pw.taskName);
          if (error instanceof TerminalToolError) {
            throw new NonRetryableException(error.message);
          }
          throw error;
        } finally {
          cleanupCreds?.();
          if (execToken) clearCredentialContext();
        }
      },
    };
  }
}
