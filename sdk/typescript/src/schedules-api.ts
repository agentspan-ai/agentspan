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

function client(runtime?: AgentRuntime) {
  return (runtime ?? getRuntime()).schedulesClient();
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

export async function runNow(name: string, opts: { runtime?: AgentRuntime } = {}): Promise<string> {
  const c = client(opts.runtime);
  const info = await c.get(name);
  return c.runNow(info);
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
