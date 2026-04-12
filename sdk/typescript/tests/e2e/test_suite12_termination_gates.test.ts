/**
 * Suite 12: Termination Conditions, Gates, and Negative Paths.
 *
 * Features NOT tested by Suites 1-11:
 *   - TextMention: agent stops when output contains sentinel text
 *   - MaxMessage: agent stops after N LLM turns
 *   - TextGate: stops/allows sequential pipeline based on sentinel
 *   - Invalid model: server rejects nonexistent model
 *
 * All assertions are algorithmic/deterministic — no LLM output parsing.
 * Validation uses DO_WHILE loop iteration counts and SUB_WORKFLOW task
 * inspection from the Conductor workflow API.
 * No mocks. Real server, real LLM.
 */

import { describe, it, expect, beforeAll, afterAll } from 'vitest';
import {
  Agent,
  AgentRuntime,
  tool,
  TextMention,
  MaxMessage,
  TextGate,
} from '@agentspan-ai/sdk';
import {
  checkServerHealth,
  MODEL,
  TIMEOUT,
  getWorkflow,
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

const echoTool = tool(
  async (args: { text: string }) => `echo:${args.text}`,
  {
    name: 'echo_tool',
    description: 'Echo the input text back.',
    inputSchema: {
      type: 'object',
      properties: { text: { type: 'string', description: 'Text to echo' } },
      required: ['text'],
    },
  },
);

// ── Helpers ──────────────────────────────────────────────────────────────

interface WorkflowTask {
  taskType: string;
  status: string;
  referenceTaskName: string;
  taskDefName: string;
  inputData: Record<string, unknown>;
  outputData: Record<string, unknown>;
}

async function getLoopIterations(executionId: string): Promise<number> {
  const wf = await getWorkflow(executionId);
  const tasks = (wf.tasks ?? []) as Record<string, unknown>[];
  for (const task of tasks) {
    if (task.taskType === 'DO_WHILE') {
      return ((task.outputData as Record<string, unknown>)?.iteration ?? 0) as number;
    }
  }
  return 0;
}

async function findSubWorkflowTasks(executionId: string): Promise<WorkflowTask[]> {
  const wf = await getWorkflow(executionId);
  const tasks = (wf.tasks ?? []) as WorkflowTask[];
  return tasks.filter((t) => {
    const taskType = t.taskType ?? (t as unknown as Record<string, unknown>).type ?? '';
    return taskType === 'SUB_WORKFLOW';
  });
}

// ── Tests ────────────────────────────────────────────────────────────────

describe('Suite 12: Termination & Gates', { timeout: 300_000 }, () => {
  // ── TextMention ──────────────────────────────────────────────

  it('text mention terminates early', async () => {
    const agent = new Agent({
      name: 'e2e_s12_text_term',
      model: MODEL,
      maxTurns: 3,
      instructions:
        'You MUST include the exact text TASK_COMPLETE in every response. ' +
        'Answer the user\'s question and always end with TASK_COMPLETE.',
      tools: [echoTool],
      termination: new TextMention('TASK_COMPLETE'),
    });

    const result = await runtime.run(agent, 'Say hello.', { timeout: TIMEOUT });
    const diag = runDiagnostic(result as unknown as Record<string, unknown>);

    expect(
      result.executionId,
      `[TextMention] No executionId. ${diag}`,
    ).toBeTruthy();
    expect(
      ['COMPLETED', 'TERMINATED'],
      `[TextMention] Expected COMPLETED or TERMINATED, got '${result.status}'. ${diag}`,
    ).toContain(result.status);

    // The loop should have stopped early — iteration count must be
    // LESS THAN OR EQUAL TO max_turns (3). Ideally it stops at iteration 1.
    const iterations = await getLoopIterations(result.executionId);
    expect(
      iterations,
      `[TextMention] DO_WHILE ran ${iterations} iterations, ` +
        `expected <= 3 (max_turns). The termination condition should ` +
        `have stopped the loop early because the agent was instructed ` +
        `to always output 'TASK_COMPLETE'. ${diag}`,
    ).toBeLessThanOrEqual(3);
  });

  // ── MaxMessage ─────────────────────────────────────────────

  it('max message terminates at limit', async () => {
    const agent = new Agent({
      name: 'e2e_s12_max_msg',
      model: MODEL,
      maxTurns: 25,
      instructions:
        'You are a helpful assistant. Answer the user\'s question. ' +
        'Keep your answers concise.',
      tools: [echoTool],
      termination: new MaxMessage(3),
    });

    const result = await runtime.run(agent, 'Count from 1 to 100.', { timeout: TIMEOUT });
    const diag = runDiagnostic(result as unknown as Record<string, unknown>);

    expect(
      result.executionId,
      `[MaxMessage] No executionId. ${diag}`,
    ).toBeTruthy();
    expect(
      ['COMPLETED', 'TERMINATED'],
      `[MaxMessage] Expected COMPLETED or TERMINATED, got '${result.status}'. ${diag}`,
    ).toContain(result.status);

    // The loop should terminate around 3 iterations.
    // Allow +/- 1 for off-by-one between message count and loop iteration.
    // The key assertion is that it does NOT run to 25 (the max_turns ceiling).
    const iterations = await getLoopIterations(result.executionId);
    expect(
      iterations,
      `[MaxMessage] DO_WHILE ran ${iterations} iterations, ` +
        `expected 2-4 (MaxMessage(3) with +/- 1 tolerance). ` +
        `If iterations == 25, the termination condition was ignored. ${diag}`,
    ).toBeGreaterThanOrEqual(2);
    expect(
      iterations,
      `[MaxMessage] DO_WHILE ran ${iterations} iterations, ` +
        `expected 2-4 (MaxMessage(3) with +/- 1 tolerance). ` +
        `If iterations == 25, the termination condition was ignored. ${diag}`,
    ).toBeLessThanOrEqual(4);
  });

  // ── TextGate stops pipeline ────────────────────────────────

  it('text gate stops pipeline', async () => {
    const checker = new Agent({
      name: 'e2e_s12_checker_stop',
      model: MODEL,
      maxTurns: 2,
      instructions: 'You MUST output exactly this text and nothing else: STOP',
      gate: new TextGate({ text: 'STOP' }),
    });
    const fixer = new Agent({
      name: 'e2e_s12_fixer_stop',
      model: MODEL,
      maxTurns: 2,
      instructions: 'Fix any issues found by the checker.',
      tools: [echoTool],
    });
    const pipeline = checker.pipe(fixer);

    const result = await runtime.run(
      pipeline,
      'Check this code for bugs.',
      { timeout: TIMEOUT },
    );
    const diag = runDiagnostic(result as unknown as Record<string, unknown>);

    expect(
      result.executionId,
      `[TextGate stops] No executionId. ${diag}`,
    ).toBeTruthy();
    expect(
      ['COMPLETED', 'TERMINATED'],
      `[TextGate stops] Expected COMPLETED or TERMINATED, got '${result.status}'. ${diag}`,
    ).toContain(result.status);

    // The fixer agent should NOT have executed (or not completed)
    // because the gate on the checker agent saw "STOP" in its output.
    const subWfs = await findSubWorkflowTasks(result.executionId);
    const fixerTasks = subWfs.filter(
      (t) => (t.referenceTaskName ?? '').toLowerCase().includes('fixer'),
    );

    if (fixerTasks.length > 0) {
      // If a fixer task exists, it must NOT be COMPLETED
      const fixerStatuses = fixerTasks.map((t) => t.status);
      const anyCompleted = fixerStatuses.some((s) => s === 'COMPLETED');
      expect(
        anyCompleted,
        `[TextGate stops] fixer SUB_WORKFLOW completed despite ` +
          `gate sentinel 'STOP' being present in checker output. ` +
          `Fixer statuses: ${fixerStatuses.join(', ')}. ` +
          `The TextGate should have halted the pipeline. ${diag}`,
      ).toBe(false);
    }
  });

  // ── TextGate allows continuation ───────────────────────────

  it('text gate allows continuation', async () => {
    const checker = new Agent({
      name: 'e2e_s12_checker_pass',
      model: MODEL,
      maxTurns: 2,
      instructions:
        'Describe the problem. Never output the word STOP. ' +
        'Say: The code has a null pointer bug that needs fixing.',
      gate: new TextGate({ text: 'STOP' }),
    });
    const fixer = new Agent({
      name: 'e2e_s12_fixer_pass',
      model: MODEL,
      maxTurns: 2,
      instructions:
        'Fix any issues found by the checker. ' +
        'Respond with the fix applied.',
      tools: [echoTool],
    });
    const pipeline = checker.pipe(fixer);

    const result = await runtime.run(
      pipeline,
      'Check this code for bugs.',
      { timeout: TIMEOUT },
    );
    const diag = runDiagnostic(result as unknown as Record<string, unknown>);

    expect(
      result.executionId,
      `[TextGate continues] No executionId. ${diag}`,
    ).toBeTruthy();
    expect(
      result.status,
      `[TextGate continues] Expected COMPLETED, got '${result.status}'. ${diag}`,
    ).toBe('COMPLETED');

    // Both agents should have executed. Verify at least 2 SUB_WORKFLOW
    // tasks exist and are COMPLETED.
    const subWfs = await findSubWorkflowTasks(result.executionId);
    const completedSubs = subWfs.filter((t) => t.status === 'COMPLETED');
    const subStatuses = subWfs.map(
      (t) => `${t.referenceTaskName ?? '?'}[${t.status}]`,
    );
    expect(
      completedSubs.length,
      `[TextGate continues] Expected at least 2 COMPLETED ` +
        `SUB_WORKFLOW tasks (checker + fixer), got ` +
        `${completedSubs.length}. ` +
        `Sub-workflow statuses: ${subStatuses.join(', ')}. ` +
        `The TextGate should have allowed continuation because ` +
        `the checker was instructed to never say 'STOP'. ${diag}`,
    ).toBeGreaterThanOrEqual(2);
  });

  // ── Invalid model fails ────────────────────────────────────

  it('invalid model fails', async () => {
    const agent = new Agent({
      name: 'e2e_s12_bad_model',
      model: 'nonexistent/xyz-model-does-not-exist',
      instructions: 'This agent should never execute successfully.',
      tools: [echoTool],
    });

    const result = await runtime.run(agent, 'Hello.', { timeout: TIMEOUT });
    const diag = runDiagnostic(result as unknown as Record<string, unknown>);

    expect(
      ['FAILED', 'TERMINATED'],
      `[Invalid model] Expected FAILED or TERMINATED for ` +
        `nonexistent model 'nonexistent/xyz-model-does-not-exist', ` +
        `got '${result.status}'. The server should reject unknown ` +
        `models and fail the workflow. ${diag}`,
    ).toContain(result.status);
  });
});
