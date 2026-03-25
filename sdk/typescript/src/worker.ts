import type { ToolContext } from './types.js';
import { AgentAPIError } from './errors.js';
import { extractExecutionToken, setCredentialContext, clearCredentialContext } from './credentials.js';

// ── Type coercion (base spec §14.1) ─────────────────────

/**
 * Coerce a value from Conductor's type system to the expected target type.
 * All failures are silent — returns original value, never throws.
 */
export function coerceValue(value: unknown, targetType?: string): unknown {
  // Rule 1: null/empty or unknown target → return unchanged
  if (value == null || targetType == null || targetType === '') {
    return value;
  }

  const t = targetType.toLowerCase();

  // Rule 3: type match short-circuit
  if (t === 'string' && typeof value === 'string') return value;
  if (t === 'number' && typeof value === 'number') return value;
  if (t === 'boolean' && typeof value === 'boolean') return value;
  if ((t === 'object' || t === 'array') && typeof value === 'object') return value;

  // Rule 4: String → object/array via JSON.parse
  if (typeof value === 'string' && (t === 'object' || t === 'array')) {
    try {
      return JSON.parse(value);
    } catch {
      return value;
    }
  }

  // Rule 5: object/array → string via JSON.stringify
  if (typeof value === 'object' && t === 'string') {
    try {
      return JSON.stringify(value);
    } catch {
      return value;
    }
  }

  // Rule 6: String → number
  if (typeof value === 'string' && t === 'number') {
    const n = Number(value);
    if (Number.isNaN(n)) return value;
    return n;
  }

  // Rule 6: String → boolean
  if (typeof value === 'string' && t === 'boolean') {
    const lower = value.toLowerCase();
    if (lower === 'true' || lower === '1' || lower === 'yes') return true;
    if (lower === 'false' || lower === '0' || lower === 'no') return false;
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
  const ctx = inputData['__agentspan_ctx__'];
  if (ctx == null || typeof ctx !== 'object') return null;

  const raw = ctx as Record<string, unknown>;
  return {
    sessionId: (raw.sessionId as string) ?? '',
    workflowId: (raw.workflowId as string) ?? '',
    agentName: (raw.agentName as string) ?? '',
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
  if (result != null && typeof result === 'object' && !Array.isArray(result)) {
    return { ...(result as Record<string, unknown>), _state_updates: stateUpdates };
  }
  return { result, _state_updates: stateUpdates };
}

/** Simple deep equality check for state diffing. */
function deepEqual(a: unknown, b: unknown): boolean {
  if (a === b) return true;
  if (a == null || b == null) return false;
  if (typeof a !== typeof b) return false;
  if (typeof a !== 'object') return false;

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
  delete cleaned['_agent_state'];
  delete cleaned['method'];
  delete cleaned['__agentspan_ctx__'];
  return cleaned;
}

// ── WorkerManager ───────────────────────────────────────

export type WorkerHandler = (inputData: Record<string, unknown>) => Promise<unknown>;

interface QueuedWorker {
  taskName: string;
  handler: WorkerHandler;
}

interface TaskData {
  taskId: string;
  workflowInstanceId: string;
  inputData?: Record<string, unknown>;
  taskType?: string;
}

/**
 * Raw fetch-based task polling worker manager.
 * NO dependency on @io-orkes/conductor-javascript.
 */
export class WorkerManager {
  readonly serverUrl: string;
  readonly headers: Record<string, string>;
  readonly pollIntervalMs: number;

  private workers: QueuedWorker[] = [];
  private pollers: ReturnType<typeof setInterval>[] = [];
  private workerId: string;

  constructor(
    serverUrl: string,
    headers: Record<string, string>,
    pollIntervalMs: number = 100,
  ) {
    this.serverUrl = serverUrl;
    this.headers = headers;
    this.pollIntervalMs = pollIntervalMs;
    this.workerId = `ts-worker-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
  }

  /**
   * Queue a worker for the given task name.
   * Replaces any existing worker with the same task name.
   */
  addWorker(taskName: string, handler: WorkerHandler): void {
    const idx = this.workers.findIndex((w) => w.taskName === taskName);
    if (idx >= 0) {
      this.workers[idx] = { taskName, handler };
    } else {
      this.workers.push({ taskName, handler });
    }
  }

  /**
   * Register a task definition with the server.
   */
  async registerTaskDef(
    taskName: string,
    config?: { timeoutSeconds?: number },
  ): Promise<void> {
    const taskDef = {
      name: taskName,
      retryCount: 2,
      retryLogic: 'LINEAR_BACKOFF',
      retryDelaySeconds: 2,
      timeoutSeconds: config?.timeoutSeconds ?? 120,
      responseTimeoutSeconds: config?.timeoutSeconds ?? 120,
    };

    const url = `${this.serverUrl}/metadata/taskdefs`;
    const response = await fetch(url, {
      method: 'POST',
      headers: {
        ...this.headers,
        'Content-Type': 'application/json',
      },
      body: JSON.stringify([taskDef]),
    });

    if (!response.ok) {
      const body = await response.text();
      throw new AgentAPIError(
        `Failed to register task def '${taskName}': ${response.status}`,
        response.status,
        body,
      );
    }
  }

  /**
   * Start polling for all queued workers.
   * Stops any existing pollers first to prevent duplicates.
   */
  startPolling(): void {
    this.stopPolling();
    for (const worker of this.workers) {
      const poller = setInterval(async () => {
        await this._pollAndExecute(worker);
      }, this.pollIntervalMs);
      this.pollers.push(poller);
    }
  }

  /**
   * Stop all polling intervals.
   */
  stopPolling(): void {
    for (const poller of this.pollers) {
      clearInterval(poller);
    }
    this.pollers = [];
  }

  /**
   * Poll for a single task of the given type.
   */
  async pollTask(taskType: string): Promise<TaskData | null> {
    const url = `${this.serverUrl}/tasks/poll/${taskType}?workerid=${encodeURIComponent(this.workerId)}`;
    const response = await fetch(url, {
      method: 'GET',
      headers: this.headers,
    });

    if (response.status === 204 || response.status === 404) {
      return null;
    }

    if (!response.ok) {
      const body = await response.text();
      throw new AgentAPIError(
        `Failed to poll task '${taskType}': ${response.status}`,
        response.status,
        body,
      );
    }

    const text = await response.text();
    if (!text || text.trim() === '') return null;

    try {
      return JSON.parse(text) as TaskData;
    } catch {
      return null;
    }
  }

  /**
   * Report successful task completion.
   */
  async reportSuccess(
    taskId: string,
    workflowInstanceId: string,
    outputData: unknown,
  ): Promise<void> {
    const url = `${this.serverUrl}/tasks`;
    const response = await fetch(url, {
      method: 'POST',
      headers: {
        ...this.headers,
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        taskId,
        workflowInstanceId,
        status: 'COMPLETED',
        outputData,
      }),
    });

    if (!response.ok) {
      const body = await response.text();
      throw new AgentAPIError(
        `Failed to report success for task '${taskId}': ${response.status}`,
        response.status,
        body,
      );
    }
  }

  /**
   * Report task failure.
   */
  async reportFailure(
    taskId: string,
    workflowInstanceId: string,
    error: Error,
  ): Promise<void> {
    const url = `${this.serverUrl}/tasks`;
    const response = await fetch(url, {
      method: 'POST',
      headers: {
        ...this.headers,
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        taskId,
        workflowInstanceId,
        status: 'FAILED',
        reasonForIncompletion: error.message,
      }),
    });

    if (!response.ok) {
      const body = await response.text();
      throw new AgentAPIError(
        `Failed to report failure for task '${taskId}': ${response.status}`,
        response.status,
        body,
      );
    }
  }

  /**
   * Internal: poll a single task and execute its handler.
   */
  private async _pollAndExecute(worker: QueuedWorker): Promise<void> {
    try {
      // Check circuit breaker
      if (isCircuitBreakerOpen(worker.taskName)) {
        return;
      }

      const task = await this.pollTask(worker.taskName);
      if (!task) return;

      const inputData = task.inputData ?? {};

      // Extract ToolContext
      const toolContext = extractToolContext(inputData);

      // Snapshot state for mutation capture
      const stateSnapshot = toolContext
        ? { ...toolContext.state }
        : {};

      // Strip internal keys
      const cleanedInput = stripInternalKeys(inputData);

      // Inject workflowInstanceId so framework passthrough workers can push events
      cleanedInput['__workflowInstanceId__'] = task.workflowInstanceId;

      // If ToolContext has state, inject it into the handler context
      if (toolContext) {
        cleanedInput['__toolContext__'] = toolContext;
      }

      // Set up credential context so getCredential() works inside handlers
      const executionToken = extractExecutionToken(inputData);
      if (executionToken) {
        setCredentialContext(this.serverUrl, this.headers, executionToken);
      }

      try {
        let result = await worker.handler(cleanedInput);

        // Capture state mutations
        if (toolContext) {
          const updates = captureStateMutations(stateSnapshot, toolContext.state);
          if (updates) {
            result = appendStateUpdates(result, updates);
          }
        }

        recordSuccess(worker.taskName);
        await this.reportSuccess(task.taskId, task.workflowInstanceId, result);
      } catch (error) {
        recordFailure(worker.taskName);
        await this.reportFailure(
          task.taskId,
          task.workflowInstanceId,
          error instanceof Error ? error : new Error(String(error)),
        );
      } finally {
        if (executionToken) {
          clearCredentialContext();
        }
      }
    } catch {
      // Swallow poll-level errors to keep the polling loop alive
    }
  }
}
