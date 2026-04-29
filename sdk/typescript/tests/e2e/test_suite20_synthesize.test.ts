/**
 * Suite 20: synthesize flag — plan-based structural assertions.
 *
 * No LLM execution — only compilation checks.
 * COUNTERFACTUAL: tests must fail if the synthesize flag has no effect.
 */

import { describe, it, expect, beforeAll } from 'vitest';
import { Agent, AgentRuntime, tool } from '@agentspan-ai/sdk';
import { checkServerHealth, MODEL } from './helpers';

let runtime: AgentRuntime;

beforeAll(async () => {
  const healthy = await checkServerHealth();
  if (!healthy) throw new Error('Server not available — skipping e2e tests');
  runtime = new AgentRuntime();
  return () => runtime.shutdown();
});

// ── Helpers ─────────────────────────────────────────────────────────────

function getAgentDef(plan: Record<string, unknown>): Record<string, unknown> {
  const wf = plan.workflowDef as Record<string, unknown>;
  const meta = wf.metadata as Record<string, unknown>;
  return meta.agentDef as Record<string, unknown>;
}

/** Recursively flatten all tasks in a workflow definition. */
function allTasksFlat(wf: Record<string, unknown>): Record<string, unknown>[] {
  const result: Record<string, unknown>[] = [];
  function walk(tasks: unknown[]) {
    for (const t of tasks) {
      if (!t || typeof t !== 'object') continue;
      const task = t as Record<string, unknown>;
      result.push(task);
      if (Array.isArray(task.loopOver)) walk(task.loopOver);
      const dc = task.decisionCases as Record<string, unknown[]> | undefined;
      if (dc) for (const v of Object.values(dc)) if (Array.isArray(v)) walk(v);
      if (Array.isArray(task.defaultCase)) walk(task.defaultCase);
      if (Array.isArray(task.forkTasks)) for (const fork of task.forkTasks) if (Array.isArray(fork)) walk(fork);
    }
  }
  walk((wf.tasks ?? []) as unknown[]);
  return result;
}

function countFinalTasks(wf: Record<string, unknown>, agentName: string): number {
  const expectedRef = agentName.replace(/-/g, '_') + '_final';
  return allTasksFlat(wf).filter((t) => t.taskReferenceName === expectedRef).length;
}

// ── Sub-agent factory ─────────────────────────────────────────────────

function makeSubAgent(name: string): Agent {
  const dummyTool = tool(async (_args: { x: string }) => 'ok', {
    name: `e2e_ts_synth_tool_${name}`,
    description: 'Dummy tool',
    inputSchema: { type: 'object', properties: { x: { type: 'string' } }, required: ['x'] },
  });
  return new Agent({ name, model: MODEL, instructions: `You are ${name}`, tools: [dummyTool] });
}

// ── Tests ────────────────────────────────────────────────────────────────

describe('Suite 20: synthesize flag', { timeout: 60_000 }, () => {

  it('handoff default — _final task present, no synthesize in agentDef', async () => {
    const agent = new Agent({
      name: 'e2e_ts_synth_default_handoff',
      model: MODEL,
      strategy: 'handoff',
      agents: [makeSubAgent('e2e_ts_sub_alpha'), makeSubAgent('e2e_ts_sub_beta')],
    });
    const plan = await runtime.plan(agent);
    const agentDef = getAgentDef(plan as unknown as Record<string, unknown>);

    // Default synthesize=true must NOT appear in serialized config (only emitted when false)
    expect(
      agentDef.synthesize,
      '[default handoff] synthesize should NOT be in agentDef when default',
    ).toBeUndefined();

    const wf = (plan as unknown as Record<string, unknown>).workflowDef as Record<string, unknown>;
    const finalCount = countFinalTasks(wf, 'e2e_ts_synth_default_handoff');
    expect(finalCount, '[default handoff] expected exactly 1 _final task').toBe(1);
  });

  it('handoff synthesize=false — no _final task, synthesize=false in agentDef', async () => {
    const agent = new Agent({
      name: 'e2e_ts_synth_false_handoff',
      model: MODEL,
      strategy: 'handoff',
      agents: [makeSubAgent('e2e_ts_sub_gamma'), makeSubAgent('e2e_ts_sub_delta')],
      synthesize: false,
    });
    const plan = await runtime.plan(agent);
    const agentDef = getAgentDef(plan as unknown as Record<string, unknown>);

    expect(
      agentDef.synthesize,
      '[synthesize=false handoff] agentDef.synthesize must be false',
    ).toBe(false);

    const wf = (plan as unknown as Record<string, unknown>).workflowDef as Record<string, unknown>;
    const finalCount = countFinalTasks(wf, 'e2e_ts_synth_false_handoff');
    expect(finalCount, '[synthesize=false handoff] workflow must NOT have a _final task').toBe(0);
  });

  it('router synthesize=false — no _final task', async () => {
    const routerAgent = new Agent({
      name: 'e2e_ts_synth_router_llm',
      model: MODEL,
      instructions: 'Pick the right agent.',
    });
    const agent = new Agent({
      name: 'e2e_ts_synth_false_router',
      model: MODEL,
      strategy: 'router',
      router: routerAgent,
      agents: [makeSubAgent('e2e_ts_sub_epsilon'), makeSubAgent('e2e_ts_sub_zeta')],
      synthesize: false,
    });
    const plan = await runtime.plan(agent);
    const agentDef = getAgentDef(plan as unknown as Record<string, unknown>);

    expect(
      agentDef.synthesize,
      '[synthesize=false router] agentDef.synthesize must be false',
    ).toBe(false);

    const wf = (plan as unknown as Record<string, unknown>).workflowDef as Record<string, unknown>;
    const finalCount = countFinalTasks(wf, 'e2e_ts_synth_false_router');
    expect(finalCount, '[synthesize=false router] workflow must NOT have a _final task').toBe(0);
  });

  it('swarm synthesize=false — no _final task', async () => {
    const agent = new Agent({
      name: 'e2e_ts_synth_false_swarm',
      model: MODEL,
      strategy: 'swarm',
      agents: [makeSubAgent('e2e_ts_sub_eta'), makeSubAgent('e2e_ts_sub_theta')],
      synthesize: false,
    });
    const plan = await runtime.plan(agent);
    const agentDef = getAgentDef(plan as unknown as Record<string, unknown>);

    expect(
      agentDef.synthesize,
      '[synthesize=false swarm] agentDef.synthesize must be false',
    ).toBe(false);

    const wf = (plan as unknown as Record<string, unknown>).workflowDef as Record<string, unknown>;
    const finalCount = countFinalTasks(wf, 'e2e_ts_synth_false_swarm');
    expect(finalCount, '[synthesize=false swarm] workflow must NOT have a _final task').toBe(0);
  });
});
