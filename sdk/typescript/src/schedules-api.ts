// Copyright (c) 2026 Agentspan
// Licensed under the MIT License. See LICENSE file in the project root for details.

/**
 * Module-level lifecycle API for schedules.
 *
 * Lifecycle calls are keyed by the **wire name** (the prefixed identifier
 * returned by `list()`). The user-supplied short name is only used at
 * `Schedule` construction time; once the schedule lands on the server,
 * it's identified by its prefixed wire name.
 *
 * Each function accepts an optional `runtime` parameter; if omitted, the
 * default singleton runtime is used.
 */

import { getRuntime, AgentRuntime } from "./runtime.js";
import type { Schedule as ScheduleClass, ScheduleInfo } from "./schedule.js";
import type { AgentResult, Status } from "./types.js";
import { makeAgentResult, TERMINAL_STATUSES } from "./result.js";

function client(runtime?: AgentRuntime) {
  return (runtime ?? getRuntime()).schedulesClient();
}

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

export async function list(opts: { agent: string; runtime?: AgentRuntime }): Promise<ScheduleInfo[]> {
  return client(opts.runtime).listForAgent(opts.agent);
}

export async function get(name: string, opts: { runtime?: AgentRuntime } = {}): Promise<ScheduleInfo> {
  return client(opts.runtime).get(name);
}

export async function pause(
  name: string,
  opts: { reason?: string; runtime?: AgentRuntime } = {},
): Promise<void> {
  await client(opts.runtime).pause(name, opts.reason);
}

export async function resume(name: string, opts: { runtime?: AgentRuntime } = {}): Promise<void> {
  await client(opts.runtime).resume(name);
}

export { deleteSchedule as delete };
async function deleteSchedule(name: string, opts: { runtime?: AgentRuntime } = {}): Promise<void> {
  await client(opts.runtime).delete(name);
}

/**
 * Fire the schedule's agent once with the schedule's stored input.
 *
 * Returns the workflow execution id immediately (non-blocking by default).
 * When `wait` is true, blocks until the workflow reaches a terminal state and
 * resolves the {@link AgentResult} (rejects after `timeoutMs`). Mirrors the
 * Python SDK's `run_now(name, wait=True)`.
 */
export async function runNow(
  name: string,
  opts: { runtime?: AgentRuntime; wait?: false },
): Promise<string>;
export async function runNow(
  name: string,
  opts: { runtime?: AgentRuntime; wait: true; timeoutMs?: number; pollIntervalMs?: number },
): Promise<AgentResult>;
export async function runNow(
  name: string,
  opts: {
    runtime?: AgentRuntime;
    wait?: boolean;
    timeoutMs?: number;
    pollIntervalMs?: number;
  } = {},
): Promise<string | AgentResult> {
  const runtime = opts.runtime ?? getRuntime();
  const c = runtime.schedulesClient();
  const info = await c.get(name);
  const executionId = await c.runNow(info);

  if (!opts.wait) {
    return executionId;
  }

  const timeoutMs = opts.timeoutMs ?? 600_000;
  const pollIntervalMs = opts.pollIntervalMs ?? 1_000;
  const deadline = Date.now() + timeoutMs;

  for (;;) {
    const wf = await runtime.workflows.getWorkflow(executionId, false);
    const status = wf.status ?? "";
    if (TERMINAL_STATUSES.has(status)) {
      return makeAgentResult({
        output: wf.output,
        executionId,
        status: status as Status,
        error: wf.reasonForIncompletion as string | undefined,
      });
    }
    if (Date.now() > deadline) {
      throw new Error(`runNow(${JSON.stringify(name)}) did not finish within ${timeoutMs}ms`);
    }
    await sleep(pollIntervalMs);
  }
}

/**
 * Convenience wrapper for `runNow(name, { wait: true, ... })`.
 */
export async function runNowAndWait(
  name: string,
  opts: { runtime?: AgentRuntime; timeoutMs?: number; pollIntervalMs?: number } = {},
): Promise<AgentResult> {
  return runNow(name, { ...opts, wait: true });
}

export async function previewNext(
  cron: string,
  opts: { n?: number; startAt?: number; endAt?: number; runtime?: AgentRuntime } = {},
): Promise<number[]> {
  const { runtime, ...rest } = opts;
  return client(runtime).previewNext(cron, rest);
}

export async function save(
  schedule: ScheduleClass,
  agent: string,
  opts: { runtime?: AgentRuntime } = {},
): Promise<void> {
  await client(opts.runtime).save(schedule, agent);
}
