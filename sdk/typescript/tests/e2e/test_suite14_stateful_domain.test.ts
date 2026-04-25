/**
 * Suite 14: Stateful Domain Propagation — verify workers register under the correct domain.
 *
 * When an agent has stateful=true, the server schedules all tasks under the
 * execution's unique domain UUID. Workers must register in that same domain
 * or tasks stay SCHEDULED with pollCount=0 forever.
 *
 * Tests:
 *   - Stateful tool completes (not stuck SCHEDULED)
 *   - Stateful stop_when executes in domain
 *   - Non-stateful agent works without domain (regression)
 *   - Concurrent stateful executions get different domains (isolation)
 *
 * No mocks. Real server. Algorithmic assertions.
 */

import { describe, it, expect, afterEach } from 'vitest';
import { Agent, AgentRuntime, tool } from '@agentspan-ai/sdk';
import type { ToolDef } from '@agentspan-ai/sdk';
import { checkServerHealth, getWorkflow, MODEL, TIMEOUT } from './helpers';

// ── Deterministic tools ─────────────────────────────────────

const echoTool = tool(
  (args: { message: string }) => `ECHO:${args.message}`,
  {
    name: 'echo_tool',
    description: 'Return the message with a prefix',
    inputSchema: {
      type: 'object',
      properties: { message: { type: 'string' } },
      required: ['message'],
    },
  },
) as ToolDef;

// ── Tests ────────────────────────────────────────────────────

describe('Suite 14: Stateful Domain Propagation', () => {
  let runtime: AgentRuntime;

  afterEach(async () => {
    await runtime?.shutdown();
  });

  it('stateful tool completes (not stuck SCHEDULED)', async () => {
    const healthy = await checkServerHealth();
    if (!healthy) throw new Error('Server not available');
    runtime = new AgentRuntime();

    const agent = new Agent({
      name: 'e2e_ts_s14_stateful_tool',
      model: MODEL,
      stateful: true,
      maxTurns: 3,
      instructions: "Call echo_tool with message='hello'. Then respond with the result.",
      tools: [echoTool],
    });

    const result = await runtime.run(agent, 'Call echo_tool with hello', { timeoutSeconds: TIMEOUT / 1000 });

    expect(String(result.status).toUpperCase()).toContain('COMPLETED');

    // Verify no tasks stuck in SCHEDULED
    const wf = await getWorkflow(result.executionId);
    const tasks = (wf.tasks ?? []) as Record<string, unknown>[];
    const scheduled = tasks.filter((t) => t.status === 'SCHEDULED');
    expect(scheduled.length).toBe(0);

    // Verify taskToDomain is set (stateful=true)
    const ttd = wf.taskToDomain as Record<string, string> | undefined;
    expect(ttd).toBeDefined();
    expect(Object.keys(ttd ?? {}).length).toBeGreaterThan(0);

    // Verify echo_tool task completed with correct domain
    const echoTasks = tasks.filter((t) =>
      String(t.taskDefName ?? '').includes('echo_tool'),
    );
    expect(echoTasks.length).toBeGreaterThan(0);
    for (const t of echoTasks) {
      expect(t.status).toBe('COMPLETED');
    }
  });

  it('stateful stop_when executes in domain', async () => {
    const healthy = await checkServerHealth();
    if (!healthy) throw new Error('Server not available');
    runtime = new AgentRuntime();

    const agent = new Agent({
      name: 'e2e_ts_s14_stateful_stop',
      model: MODEL,
      stateful: true,
      maxTurns: 5,
      instructions: "Call echo_tool with message='stop_test'. Then respond.",
      tools: [echoTool],
      stopWhen: (messages: unknown[]) => {
        const lastMsg = messages[messages.length - 1];
        return typeof lastMsg === 'string' && lastMsg.includes('ECHO:');
      },
    });

    const result = await runtime.run(agent, 'Call echo_tool with stop_test', { timeoutSeconds: TIMEOUT / 1000 });

    expect(String(result.status).toUpperCase()).toContain('COMPLETED');

    // Verify stop_when task executed
    const wf = await getWorkflow(result.executionId);
    const tasks = (wf.tasks ?? []) as Record<string, unknown>[];
    const stopTasks = tasks.filter((t) =>
      String(t.taskDefName ?? '').includes('stop_when'),
    );
    expect(stopTasks.length).toBeGreaterThan(0);
    const completedStops = stopTasks.filter((t) => t.status === 'COMPLETED');
    expect(completedStops.length).toBeGreaterThan(0);

    // No stuck tasks
    const scheduled = tasks.filter((t) => t.status === 'SCHEDULED');
    expect(scheduled.length).toBe(0);
  });

  it('agent without stateful flag works without domain', async () => {
    const healthy = await checkServerHealth();
    if (!healthy) throw new Error('Server not available');
    runtime = new AgentRuntime();

    const agent = new Agent({
      name: 'e2e_ts_s14_non_stateful',
      model: MODEL,
      // stateful NOT set (defaults to false)
      maxTurns: 3,
      instructions: "Call echo_tool with message='non_stateful'. Respond.",
      tools: [echoTool],
    });

    const result = await runtime.run(agent, 'Call echo_tool', { timeoutSeconds: TIMEOUT / 1000 });

    expect(String(result.status).toUpperCase()).toContain('COMPLETED');

    // taskToDomain should be empty for non-stateful
    const wf = await getWorkflow(result.executionId);
    const ttd = wf.taskToDomain as Record<string, string> | undefined;
    expect(Object.keys(ttd ?? {}).length).toBe(0);
  });

  it('concurrent stateful executions get different domains', async () => {
    const healthy = await checkServerHealth();
    if (!healthy) throw new Error('Server not available');

    // Use separate runtimes for isolation
    const rt1 = new AgentRuntime();
    const rt2 = new AgentRuntime();

    try {
      const makeAgent = (suffix: string) =>
        new Agent({
          name: `e2e_ts_s14_concurrent_${suffix}`,
          model: MODEL,
          stateful: true,
          maxTurns: 3,
          instructions: "Call echo_tool with message='concurrent'. Respond.",
          tools: [echoTool],
        });

      const [result1, result2] = await Promise.all([
        rt1.run(makeAgent('a'), 'Run 1', { timeoutSeconds: TIMEOUT / 1000 }),
        rt2.run(makeAgent('b'), 'Run 2', { timeoutSeconds: TIMEOUT / 1000 }),
      ]);

      expect(String(result1.status).toUpperCase()).toContain('COMPLETED');
      expect(String(result2.status).toUpperCase()).toContain('COMPLETED');
      expect(result1.executionId).not.toBe(result2.executionId);

      // Different domains
      const wf1 = await getWorkflow(result1.executionId);
      const wf2 = await getWorkflow(result2.executionId);
      const ttd1 = wf1.taskToDomain as Record<string, string> | undefined;
      const ttd2 = wf2.taskToDomain as Record<string, string> | undefined;

      expect(Object.keys(ttd1 ?? {}).length).toBeGreaterThan(0);
      expect(Object.keys(ttd2 ?? {}).length).toBeGreaterThan(0);

      const domains1 = new Set(Object.values(ttd1 ?? {}));
      const domains2 = new Set(Object.values(ttd2 ?? {}));

      // Domains should not overlap
      for (const d of domains1) {
        expect(domains2.has(d)).toBe(false);
      }
    } finally {
      await rt1.shutdown();
      await rt2.shutdown();
    }
  });
});
