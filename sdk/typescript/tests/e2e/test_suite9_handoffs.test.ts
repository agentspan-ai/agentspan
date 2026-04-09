/**
 * Suite 9: Agent Handoffs — compilation and runtime behavior.
 *
 * Tests multi-agent orchestration strategies:
 *   - All 8 strategies compile correctly (plan-only)
 *   - Sequential execution with SUB_WORKFLOW tasks
 *   - Parallel execution with FORK tasks
 *   - Handoff delegation to sub-agents
 *   - Router selects correct agent
 *   - Swarm with OnTextMention handoff condition
 *   - Pipe operator creates sequential pipeline
 *
 * All validation is algorithmic — no LLM output parsing.
 */

import { describe, it, expect, beforeAll, afterAll } from 'vitest';
import {
  Agent,
  AgentRuntime,
  tool,
  OnTextMention,
} from '@agentspan-ai/sdk';
import type { AgentOptions } from '@agentspan-ai/sdk';
import {
  checkServerHealth,
  MODEL,
  TIMEOUT,
  getWorkflow,
  getOutputText,
  runDiagnostic,
} from './helpers';

let runtime: AgentRuntime;

beforeAll(async () => {
  const healthy = await checkServerHealth();
  if (!healthy) throw new Error('Server not available');
  runtime = new AgentRuntime();
});

afterAll(() => runtime.shutdown());

// ── Deterministic tools ──────────────────────────────────────────────────

const doMath = tool(
  async (args: { expr: string }) => `math_result:${args.expr}=${eval(args.expr)}`,
  {
    name: 'do_math',
    description: 'Evaluate math expression',
    inputSchema: {
      type: 'object',
      properties: { expr: { type: 'string', description: 'Math expression to evaluate' } },
      required: ['expr'],
    },
  },
);

const doText = tool(
  async (args: { text: string }) => `text_result:${args.text.split('').reverse().join('')}`,
  {
    name: 'do_text',
    description: 'Reverse text',
    inputSchema: {
      type: 'object',
      properties: { text: { type: 'string', description: 'Text to reverse' } },
      required: ['text'],
    },
  },
);

const doData = tool(
  async (args: { query: string }) => `data_result:${args.query}`,
  {
    name: 'do_data',
    description: 'Query data',
    inputSchema: {
      type: 'object',
      properties: { query: { type: 'string', description: 'Query string' } },
      required: ['query'],
    },
  },
);

// ── Child agents ─────────────────────────────────────────────────────────

// Factory functions (fresh instances per test, matching Python pattern)
function makeMathAgent() {
  return new Agent({
    name: 'math_agent',
    model: MODEL,
    instructions:
      'You are a math agent. When asked to compute something, call do_math with the expression. ' +
      'For example, for "3+4" call do_math with expr="3+4".',
    tools: [doMath],
  });
}

function makeTextAgent() {
  return new Agent({
    name: 'text_agent',
    model: MODEL,
    instructions:
      'You are a text agent. When asked to reverse text, call do_text with the text. ' +
      'For example, for "hello" call do_text with text="hello".',
    tools: [doText],
  });
}

function makeDataAgent() {
  return new Agent({
    name: 'data_agent',
    model: MODEL,
    instructions:
      'You are a data agent. When asked to query data, call do_data with the query.',
    tools: [doData],
  });
}

// Shared references for compile-only tests
const mathAgent = makeMathAgent();
const textAgent = makeTextAgent();
const dataAgent = makeDataAgent();

// ── Helpers ──────────────────────────────────────────────────────────────

function getAgentDef(plan: Record<string, unknown>): Record<string, unknown> {
  const wf = plan.workflowDef as Record<string, unknown>;
  const meta = wf.metadata as Record<string, unknown>;
  return meta.agentDef as Record<string, unknown>;
}

interface WorkflowTask {
  taskType: string;
  status: string;
  referenceTaskName: string;
  taskDefName: string;
  inputData: Record<string, unknown>;
  outputData: Record<string, unknown>;
}

async function getWorkflowTasks(executionId: string): Promise<WorkflowTask[]> {
  const wf = await getWorkflow(executionId);
  return (wf.tasks ?? []) as WorkflowTask[];
}

function findTasksByType(tasks: WorkflowTask[], taskType: string): WorkflowTask[] {
  return tasks.filter((t) => t.taskType === taskType);
}

// ── Tests ────────────────────────────────────────────────────────────────

describe('Suite 9: Agent Handoffs', { timeout: 1_800_000 }, () => { // 30 min for all multi-agent tests
  // ── Compilation tests ─────────────────────────────────────────────────

  it('all 8 strategies compile correctly', async () => {
    const strategies = [
      'handoff',
      'sequential',
      'parallel',
      'router',
      'round_robin',
      'random',
      'swarm',
      'manual',
    ] as const;

    // Shared children (matching Python pattern)
    const childA = new Agent({ name: 'child_a', model: MODEL, instructions: 'Child A.' });
    const childB = new Agent({ name: 'child_b', model: MODEL, instructions: 'Child B.' });
    const routerLead = new Agent({ name: 'router_lead', model: MODEL, instructions: 'Route tasks.' });

    for (const strategy of strategies) {
      const opts: Record<string, unknown> = {
        name: `e2e_ts_${strategy}_parent`,
        model: MODEL,
        instructions: `Parent with ${strategy} strategy.`,
        agents: [childA, childB],
        strategy,
      };

      if (strategy === 'router') {
        opts.router = routerLead;
      }

      const parent = new Agent(opts as unknown as AgentOptions);
      const plan = (await runtime.plan(parent)) as Record<string, unknown>;

      // Assert plan has required top-level keys
      expect(plan.workflowDef, `[${strategy}] plan missing workflowDef`).toBeDefined();
      expect(plan.requiredWorkers, `[${strategy}] plan missing requiredWorkers`).toBeDefined();

      const ad = getAgentDef(plan);

      // Assert strategy
      expect(ad.strategy, `Strategy '${strategy}' not reflected`).toBe(strategy);

      // Assert sub-agents
      const agents = (ad.agents ?? []) as Record<string, unknown>[];
      expect(agents.length, `[${strategy}] should have 2 sub-agents`).toBeGreaterThanOrEqual(2);
      const agentNames = agents.map((a) => a.name as string);
      expect(agentNames, `[${strategy}] missing child_a`).toContain('child_a');
      expect(agentNames, `[${strategy}] missing child_b`).toContain('child_b');
    }
  });

  it('router requires router argument', () => {
    // Pure SDK validation — no server needed
    expect(() => {
      new Agent({
        name: 'bad_router',
        model: MODEL,
        agents: [mathAgent, textAgent],
        strategy: 'router',
        // Missing router= argument
      });
    }).toThrow();
  });

  // ── Runtime tests ─────────────────────────────────────────────────────

  it('sequential execution produces SUB_WORKFLOW tasks', async () => {
    const parent = new Agent({
      name: 'e2e_ts_sequential_run',
      model: MODEL,
      instructions:
        'You are a sequential orchestrator. First delegate to math_agent to compute 3+4, ' +
        'then delegate to text_agent to reverse "hello". Report both results.',
      agents: [mathAgent, textAgent],
      strategy: 'sequential',
    });

    const result = await runtime.run(
      parent,
      'First compute 3+4, then reverse hello',
      { timeout: TIMEOUT },
    );

    const diag = runDiagnostic(result as unknown as Record<string, unknown>);
    expect(result.executionId).toBeTruthy();
    expect(result.status, `[Sequential] ${diag}`).toBe('COMPLETED');

    // Verify SUB_WORKFLOW tasks exist in the workflow
    const tasks = await getWorkflowTasks(result.executionId);
    const subWorkflows = findTasksByType(tasks, 'SUB_WORKFLOW');
    expect(
      subWorkflows.length,
      `[Sequential] Expected at least 2 SUB_WORKFLOW tasks. All tasks: ${tasks.map((t) => `${t.referenceTaskName}[${t.taskType}]`).join(', ')}`,
    ).toBeGreaterThanOrEqual(2);

    // Verify both child agents executed via sub-workflow completion
    const completedRefs = subWorkflows
      .filter((t) => t.status === 'COMPLETED')
      .map((t) => t.referenceTaskName);
    expect(
      completedRefs.some((r) => r.toLowerCase().includes('math')),
      `[Sequential] math_agent sub-workflow not COMPLETED. Refs: ${completedRefs}`,
    ).toBe(true);
    expect(
      completedRefs.some((r) => r.toLowerCase().includes('text')),
      `[Sequential] text_agent sub-workflow not COMPLETED. Refs: ${completedRefs}`,
    ).toBe(true);
  });

  it('parallel execution produces FORK task', async () => {
    const parent = new Agent({
      name: 'e2e_ts_parallel_run',
      model: MODEL,
      instructions:
        'You are a parallel orchestrator. Delegate to math_agent to compute 3+4 AND ' +
        'delegate to text_agent to reverse "hello" simultaneously. Report both results.',
      agents: [mathAgent, textAgent],
      strategy: 'parallel',
    });

    const result = await runtime.run(
      parent,
      'Compute 3+4 AND reverse hello',
      { timeout: TIMEOUT },
    );

    const diag = runDiagnostic(result as unknown as Record<string, unknown>);
    expect(result.executionId).toBeTruthy();
    expect(result.status, `[Parallel] ${diag}`).toBe('COMPLETED');

    // Verify FORK task exists in the workflow
    const tasks = await getWorkflowTasks(result.executionId);
    const forkTasks = findTasksByType(tasks, 'FORK');
    expect(
      forkTasks.length,
      `[Parallel] Expected FORK task. All tasks: ${tasks.map((t) => `${t.referenceTaskName}[${t.taskType}]`).join(', ')}`,
    ).toBeGreaterThanOrEqual(1);

    // Verify both child agents executed via sub-workflow completion
    const subWorkflows = findTasksByType(tasks, 'SUB_WORKFLOW');
    const completedRefs = subWorkflows
      .filter((t) => t.status === 'COMPLETED')
      .map((t) => t.referenceTaskName);
    expect(
      completedRefs.some((r) => r.toLowerCase().includes('math')),
      `[Parallel] math_agent sub-workflow not COMPLETED. Refs: ${completedRefs}`,
    ).toBe(true);
    expect(
      completedRefs.some((r) => r.toLowerCase().includes('text')),
      `[Parallel] text_agent sub-workflow not COMPLETED. Refs: ${completedRefs}`,
    ).toBe(true);
  });

  it('handoff execution delegates to sub-agent', async () => {
    const parent = new Agent({
      name: 'e2e_ts_handoff_run',
      model: MODEL,
      instructions:
        'You route requests. If the user needs math, delegate to math_agent. ' +
        'If the user needs text manipulation, delegate to text_agent.',
      agents: [mathAgent, textAgent],
      strategy: 'handoff',
    });

    const result = await runtime.run(
      parent,
      'I need to reverse the word hello',
      { timeout: TIMEOUT },
    );

    const diag = runDiagnostic(result as unknown as Record<string, unknown>);
    expect(result.executionId).toBeTruthy();
    expect(
      ['COMPLETED', 'FAILED', 'TERMINATED'],
      `[Handoff] Unexpected status. ${diag}`,
    ).toContain(result.status);

    // Verify SUB_WORKFLOW tasks exist (handoff creates sub-workflows)
    const tasks = await getWorkflowTasks(result.executionId);
    const subWorkflows = findTasksByType(tasks, 'SUB_WORKFLOW');
    const completedSubs = subWorkflows.filter((t) => t.status === 'COMPLETED');
    expect(
      completedSubs.length,
      `[Handoff] Expected at least one COMPLETED SUB_WORKFLOW. All tasks: ${tasks.map((t) => `${t.referenceTaskName}[${t.taskType},${t.status}]`).join(', ')}`,
    ).toBeGreaterThanOrEqual(1);
  });

  it('router selects correct agent', async () => {
    const routerAgent = new Agent({
      name: 'router_lead',
      model: MODEL,
      instructions:
        'You are a routing agent. Analyze the user request and route to the correct specialist. ' +
        'For math or computation tasks, route to math_agent. ' +
        'For text manipulation tasks, route to text_agent.',
    });

    const parent = new Agent({
      name: 'e2e_ts_router_run',
      model: MODEL,
      instructions: 'Route to the correct specialist agent.',
      agents: [mathAgent, textAgent],
      strategy: 'router',
      router: routerAgent,
    });

    const result = await runtime.run(
      parent,
      'Compute 7 times 8',
      { timeout: TIMEOUT },
    );

    const diag = runDiagnostic(result as unknown as Record<string, unknown>);
    expect(result.executionId).toBeTruthy();
    expect(result.status, `[Router] ${diag}`).toBe('COMPLETED');

    // Verify math sub-workflow was executed
    const tasks = await getWorkflowTasks(result.executionId);
    const subWorkflows = findTasksByType(tasks, 'SUB_WORKFLOW');
    const mathSubs = subWorkflows.filter(
      (t) => String(t.referenceTaskName ?? '').toLowerCase().includes('math'),
    );
    expect(
      mathSubs.length,
      `[Router] Expected math-related SUB_WORKFLOW. Sub-workflows: ${subWorkflows.map((t) => `${t.referenceTaskName}[${t.status}]`).join(', ')}`,
    ).toBeGreaterThanOrEqual(1);
  });

  it('swarm with OnTextMention handoff', async () => {
    const parent = new Agent({
      name: 'e2e_ts_swarm_run',
      model: MODEL,
      instructions:
        'You are a swarm coordinator. Handle requests by delegating to the appropriate agent.',
      agents: [textAgent, mathAgent],
      strategy: 'swarm',
      maxTurns: 5,
      handoffs: [
        new OnTextMention({ target: 'text_agent', text: 'reverse' }),
        new OnTextMention({ target: 'math_agent', text: 'compute' }),
      ],
    });

    const result = await runtime.run(
      parent,
      'Please reverse the word hello',
      { timeout: TIMEOUT },
    );

    const diag = runDiagnostic(result as unknown as Record<string, unknown>);
    expect(result.executionId).toBeTruthy();
    expect(
      ['COMPLETED', 'FAILED', 'TERMINATED'],
      `[Swarm] Unexpected status. ${diag}`,
    ).toContain(result.status);

    // Verify text_agent sub-workflow was executed
    const tasks = await getWorkflowTasks(result.executionId);
    const subWorkflows = findTasksByType(tasks, 'SUB_WORKFLOW');
    const textSubs = subWorkflows.filter(
      (t) => String(t.referenceTaskName ?? '').toLowerCase().includes('text'),
    );
    expect(
      textSubs.length,
      `[Swarm] Expected text_agent SUB_WORKFLOW. Sub-workflows: ${subWorkflows.map((t) => `${t.referenceTaskName}[${t.status}]`).join(', ')}. All tasks: ${tasks.map((t) => `${t.referenceTaskName}[${t.taskType}]`).join(', ')}`,
    ).toBeGreaterThanOrEqual(1);
  });

  it('pipe operator creates sequential pipeline', async () => {
    const freshMath = makeMathAgent();
    const freshText = makeTextAgent();
    const pipeline = freshMath.pipe(freshText);

    // Verify the pipeline is a sequential agent
    expect(pipeline.strategy).toBe('sequential');
    expect(pipeline.agents.length).toBe(2);
    expect(pipeline.agents[0].name).toBe('math_agent');
    expect(pipeline.agents[1].name).toBe('text_agent');

    // Verify plan compiles with sequential strategy
    const plan = (await runtime.plan(pipeline)) as Record<string, unknown>;
    const ad = getAgentDef(plan);
    expect(ad.strategy, '[Pipe] plan strategy').toBe('sequential');

    // Run
    const result = await runtime.run(
      pipeline,
      'Compute 2+3 then reverse hello',
      { timeout: TIMEOUT },
    );

    const diag = runDiagnostic(result as unknown as Record<string, unknown>);
    expect(result.executionId).toBeTruthy();
    expect(result.status, `[Pipe] ${diag}`).toBe('COMPLETED');

    // Verify at least 2 SUB_WORKFLOW tasks, both children completed
    const tasks = await getWorkflowTasks(result.executionId);
    const subWorkflows = findTasksByType(tasks, 'SUB_WORKFLOW');
    expect(
      subWorkflows.length,
      `[Pipe] Expected at least 2 SUB_WORKFLOW tasks. All tasks: ${tasks.map((t) => `${t.referenceTaskName}[${t.taskType}]`).join(', ')}`,
    ).toBeGreaterThanOrEqual(2);

    const completedRefs = subWorkflows
      .filter((t) => t.status === 'COMPLETED')
      .map((t) => t.referenceTaskName);
    expect(
      completedRefs.some((r) => r.toLowerCase().includes('math')),
      `[Pipe] math_agent sub-workflow not COMPLETED. Refs: ${completedRefs}`,
    ).toBe(true);
    expect(
      completedRefs.some((r) => r.toLowerCase().includes('text')),
      `[Pipe] text_agent sub-workflow not COMPLETED. Refs: ${completedRefs}`,
    ).toBe(true);
  });
});
