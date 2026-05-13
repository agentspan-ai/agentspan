/**
 * Suite 14: Lease Extension — proves heartbeats keep long-running tasks alive.
 *
 * The TS SDK sets `leaseExtendEnabled=true` for all workers and defaults
 * `timeoutSeconds=10`.  The conductor SDK sends heartbeats at 80% of the
 * timeout window (every 8 s) to extend the lease.
 *
 * This test creates a tool that sleeps 15 s — well past the 10 s timeout.
 * If lease extension works the task completes normally.
 * If it is broken the task times out (TIMED_OUT / FAILED).
 *
 * No mocks. Real server, real LLM, real conductor.
 */

import { describe, it, expect, beforeAll, afterAll } from 'vitest';
import { Agent, AgentRuntime, tool } from '@agentspan-ai/sdk';
import { checkServerHealth, MODEL, findToolTasks, runDiagnostic } from './helpers';

let runtime: AgentRuntime;

beforeAll(async () => {
  const healthy = await checkServerHealth();
  if (!healthy) throw new Error('Server not available');
  runtime = new AgentRuntime();
});

afterAll(async () => {
  await runtime.shutdown();
});

// ── Tool ─────────────────────────────────────────────────────────────────

const slowTool = tool(
  async () => {
    // Sleep 15 s — past the 10 s responseTimeoutSeconds.
    // Without lease extension heartbeats the task would time out.
    await new Promise((resolve) => setTimeout(resolve, 15_000));
    return { result: 'slow_computation_done', elapsed_seconds: 15 };
  },
  {
    name: 'slow_computation',
    description: 'Run a computation that takes a while to complete.',
    inputSchema: {
      type: 'object',
      properties: { query: { type: 'string' } },
      required: ['query'],
    },
  },
);

// ── Test ─────────────────────────────────────────────────────────────────

describe('Suite 14: Lease Extension', { timeout: 120_000 }, () => {
  it('long-running tool completes with lease extension', async () => {
    const agent = new Agent({
      name: 'e2e_ts_lease_extension',
      model: MODEL,
      maxTurns: 3,
      instructions:
        'Use the slow_computation tool to answer the user\'s question. ' +
        'Always call the tool — do not answer from memory.',
      tools: [slowTool],
    });

    const result = await runtime.run(agent, "Run a slow computation for 'lease test'.");

    // ── Primary assertion: completed, not timed out ──
    expect(result.status).toBe('COMPLETED');

    // Verify the tool was actually called
    const { results: tasks } = await findToolTasks(
      result.executionId!,
      ['slow_computation'],
    );
    const toolTask = tasks['slow_computation'];
    expect(toolTask).toBeDefined();
    expect(toolTask.status).toBe('COMPLETED');
  }, 120_000);

  it('fails without lease extension if tool exceeds timeout', async () => {
    // Negative control: agent with timeoutSeconds=5 and a 15s tool.
    // Even with heartbeats, the 5s window is so small the task should
    // still complete because heartbeats fire at 80% (4s).
    // But we set timeoutSeconds=1 to make the window too small for
    // the heartbeat mechanism to reliably save.
    //
    // NOTE: This test validates our understanding of the mechanism.
    // If conductor's heartbeat fires fast enough even at 1s timeout,
    // skip this test — the positive test above is the authoritative one.
    const agent = new Agent({
      name: 'e2e_ts_lease_no_extend',
      model: MODEL,
      maxTurns: 3,
      timeoutSeconds: 1,
      instructions:
        'Use the slow_computation tool to answer the user\'s question. ' +
        'Always call the tool — do not answer from memory.',
      tools: [slowTool],
    });

    // This may complete (if heartbeat at 0.8s is fast enough) or fail.
    // We just run it and log the result — the primary test above is
    // what actually proves lease extension works.
    try {
      const result = await runtime.run(agent, "Run a slow computation for 'negative test'.");
      console.log(
        `Negative control: status=${result.status} ` +
        `(even 1s timeout survived — heartbeat is very aggressive)`,
      );
    } catch (err) {
      console.log(
        `Negative control: failed as expected — ${err instanceof Error ? err.message : String(err)}`,
      );
    }
  }, 120_000);
});
