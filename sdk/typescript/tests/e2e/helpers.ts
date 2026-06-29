/**
 * Shared helpers for TypeScript e2e tests.
 *
 * Provides workflow inspection, diagnostic formatting, and assertion utilities.
 * All validation is algorithmic — no LLM output parsing.
 */

const SERVER_URL = process.env.AGENTSPAN_SERVER_URL ?? 'http://localhost:6767/api';
const BASE_URL = SERVER_URL.replace(/\/api$/, '');
export const MODEL = process.env.AGENTSPAN_LLM_MODEL ?? 'openai/gpt-4o-mini';
export const CLI_PATH = process.env.AGENTSPAN_CLI_PATH ?? 'agentspan';
export const MCP_TESTKIT_URL = process.env.MCP_TESTKIT_URL ?? 'http://localhost:3001';
export const TIMEOUT = 300_000; // 5 min per run — CI runners are slower

// ── Workflow API ────────────────────────────────────────────────────────

export async function getWorkflow(executionId: string): Promise<Record<string, unknown>> {
  const resp = await fetch(`${BASE_URL}/api/workflow/${executionId}`, {
    signal: AbortSignal.timeout(10_000),
  });
  if (!resp.ok) throw new Error(`Workflow fetch failed: ${resp.status}`);
  return resp.json() as Promise<Record<string, unknown>>;
}

export function getOutputText(result: { output: unknown }): string {
  const output = result.output as Record<string, unknown> | undefined;
  if (!output) return '';
  if (typeof output === 'object' && 'result' in output) {
    const results = output.result;
    if (typeof results === 'string') return results;
    if (Array.isArray(results)) {
      return results
        .map((r: unknown) => {
          if (typeof r === 'string') return r;
          if (typeof r === 'object' && r !== null) {
            const obj = r as Record<string, unknown>;
            return (obj.text ?? obj.content ?? JSON.stringify(r)) as string;
          }
          return String(r);
        })
        .join('');
    }
    return String(output);
  }
  return String(output);
}

export function runDiagnostic(result: Record<string, unknown>): string {
  const parts: string[] = [
    `status=${result.status}`,
    `executionId=${result.executionId}`,
  ];
  const output = result.output as Record<string, unknown> | undefined;
  if (output && typeof output === 'object') {
    parts.push(`outputKeys=${Object.keys(output)}`);
    if ('finishReason' in output) parts.push(`finishReason=${output.finishReason}`);
  }
  return parts.join(' | ');
}

// ── Credential helper ────────────────────────────────────────────────────
// Writes directly to the server's secret store (PUT/DELETE /api/secrets/{name}) —
// the same store the agentspan CLI targets, and what tools resolve at runtime.
// Using the API keeps these tests deterministic regardless of the local CLI's
// ambient config (~/.agentspan/config.json may point at a different/managed server).

export async function credentialSet(name: string, value: string): Promise<void> {
  const resp = await fetch(`${SERVER_URL}/secrets/${encodeURIComponent(name)}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'text/plain' },
    body: value,
    signal: AbortSignal.timeout(15_000),
  });
  if (!resp.ok) throw new Error(`credentialSet(${name}) failed: HTTP ${resp.status}`);
}

export async function credentialDelete(name: string): Promise<void> {
  try {
    await fetch(`${SERVER_URL}/secrets/${encodeURIComponent(name)}`, {
      method: 'DELETE',
      signal: AbortSignal.timeout(15_000),
    });
  } catch {
    // Ignore errors during cleanup (e.g., already deleted).
  }
}

// ── Server health check ─────────────────────────────────────────────────

export async function checkServerHealth(): Promise<boolean> {
  try {
    const resp = await fetch(`${BASE_URL}/health`, {
      signal: AbortSignal.timeout(5_000),
    });
    const data = (await resp.json()) as Record<string, unknown>;
    return data.healthy === true;
  } catch {
    return false;
  }
}

// ── Workflow task finders ───────────────────────────────────────────────

/** System task types to skip when searching for tool executions. */
const SYSTEM_TASK_TYPES = new Set([
  'LLM_CHAT_COMPLETE',
  'SWITCH',
  'DO_WHILE',
  'INLINE',
  'SET_VARIABLE',
  'FORK',
  'FORK_JOIN_DYNAMIC',
  'JOIN',
  'SUB_WORKFLOW',
  'TERMINATE',
  'WAIT',
  'EVENT',
  'DECISION',
]);

export interface TaskInfo {
  status: string;
  output: Record<string, unknown>;
  input: Record<string, unknown>;
  ref: string;
  taskDef: string;
  taskType: string;
  reason: string;
}

/**
 * Find tool tasks in a workflow by tool name.
 * Checks taskDefName, taskType, referenceTaskName, and inputData (for non-system tasks).
 */
export async function findToolTasks(
  executionId: string,
  toolNames: string[],
): Promise<{ results: Record<string, TaskInfo>; allTasks: string[] }> {
  const wf = await getWorkflow(executionId);
  const tasks = (wf.tasks ?? []) as Record<string, unknown>[];
  const results: Record<string, TaskInfo> = {};
  const allTasks: string[] = [];

  for (const task of tasks) {
    const ref = (task.referenceTaskName ?? '') as string;
    const taskDef = (task.taskDefName ?? '') as string;
    const taskType = (task.taskType ?? '') as string;
    const inputData = (task.inputData ?? {}) as Record<string, unknown>;
    allTasks.push(`${ref}[def=${taskDef},type=${taskType}]`);

    for (const name of toolNames) {
      if (results[name]) continue;

      const match =
        name === taskDef ||
        name === taskType ||
        ref.includes(name) ||
        // Only check inputData for tool execution tasks
        (!SYSTEM_TASK_TYPES.has(taskType) && JSON.stringify(inputData).includes(name));

      if (match) {
        results[name] = {
          status: (task.status ?? '') as string,
          output: (task.outputData ?? {}) as Record<string, unknown>,
          input: inputData,
          ref,
          taskDef,
          taskType,
          reason: (task.reasonForIncompletion ?? '') as string,
        };
      }
    }
  }

  return { results, allTasks };
}

/**
 * Find tool tasks recursively — traverses SUB_WORKFLOW tasks one level deep.
 * Needed for pipeline executions where each stage runs in its own sub-workflow.
 */
export async function findToolTasksDeep(
  executionId: string,
  toolNames: string[],
): Promise<{ results: Record<string, TaskInfo>; allTasks: string[] }> {
  const remaining = new Set(toolNames);
  const results: Record<string, TaskInfo> = {};
  const allTasks: string[] = [];

  async function scanWorkflow(wfId: string, depth: number): Promise<void> {
    if (remaining.size === 0 || depth > 3) return;
    const wf = await getWorkflow(wfId);
    const tasks = (wf.tasks ?? []) as Record<string, unknown>[];

    for (const task of tasks) {
      const ref = (task.referenceTaskName ?? '') as string;
      const taskDef = (task.taskDefName ?? '') as string;
      const taskType = (task.taskType ?? '') as string;
      const inputData = (task.inputData ?? {}) as Record<string, unknown>;
      allTasks.push(`${ref}[def=${taskDef},type=${taskType}]`);

      for (const name of [...remaining]) {
        const match =
          name === taskDef ||
          name === taskType ||
          ref.includes(name) ||
          (!SYSTEM_TASK_TYPES.has(taskType) && JSON.stringify(inputData).includes(name));

        if (match) {
          results[name] = {
            status: (task.status ?? '') as string,
            output: (task.outputData ?? {}) as Record<string, unknown>,
            input: inputData,
            ref,
            taskDef,
            taskType,
            reason: (task.reasonForIncompletion ?? '') as string,
          };
          remaining.delete(name);
        }
      }

      // Recurse into sub-workflows
      if (taskType === 'SUB_WORKFLOW' && remaining.size > 0) {
        const subId = ((task.outputData as Record<string, unknown>)?.subWorkflowId ??
          (task.inputData as Record<string, unknown>)?.subWorkflowId) as string | undefined;
        if (subId) {
          await scanWorkflow(subId, depth + 1);
        }
      }
    }
  }

  await scanWorkflow(executionId, 0);
  return { results, allTasks };
}
