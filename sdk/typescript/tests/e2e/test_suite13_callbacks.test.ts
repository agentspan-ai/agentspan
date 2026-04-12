/**
 * Suite 13: Callbacks -- lifecycle hooks for tool and model events.
 *
 * Tests that CallbackHandler hooks compile correctly into the workflow
 * definition and execute as real worker tasks at runtime.
 *
 * All assertions are algorithmic/deterministic -- no LLM output parsing.
 * Validation uses plan inspection and workflow task status checks.
 * No mocks. Real server, real LLM.
 */

import { describe, it, expect, beforeAll, afterAll } from 'vitest';
import {
  Agent,
  AgentRuntime,
  tool,
  CallbackHandler,
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

// ── Callback handlers ────────────────────────────────────────────────────

class ToolCallbackHandler extends CallbackHandler {
  /** Overrides onToolStart and onToolEnd only. */
  async onToolStart(_agentName: string, _toolName: string, _args: unknown): Promise<void> {
    return;
  }
  async onToolEnd(_agentName: string, _toolName: string, _result: unknown): Promise<void> {
    return;
  }
}

class ModelCallbackHandler extends CallbackHandler {
  /** Overrides onModelStart and onModelEnd only. */
  async onModelStart(_agentName: string, _messages: unknown[]): Promise<void> {
    return;
  }
  async onModelEnd(_agentName: string, _response: unknown): Promise<void> {
    return;
  }
}

class BeforeToolCallbackHandler extends CallbackHandler {
  /** Overrides onToolStart only. */
  async onToolStart(_agentName: string, _toolName: string, _args: unknown): Promise<void> {
    return;
  }
}

class AfterToolCallbackHandler extends CallbackHandler {
  /** Overrides onToolEnd only. */
  async onToolEnd(_agentName: string, _toolName: string, _result: unknown): Promise<void> {
    return;
  }
}

class AllCallbackHandler extends CallbackHandler {
  /** Overrides all 6 lifecycle methods. */
  async onAgentStart(_agentName: string, _prompt: string): Promise<void> {
    return;
  }
  async onAgentEnd(_agentName: string, _result: unknown): Promise<void> {
    return;
  }
  async onModelStart(_agentName: string, _messages: unknown[]): Promise<void> {
    return;
  }
  async onModelEnd(_agentName: string, _response: unknown): Promise<void> {
    return;
  }
  async onToolStart(_agentName: string, _toolName: string, _args: unknown): Promise<void> {
    return;
  }
  async onToolEnd(_agentName: string, _toolName: string, _result: unknown): Promise<void> {
    return;
  }
}

// ── Tests ────────────────────────────────────────────────────────────────

describe('Suite 13: Callbacks', { timeout: 300_000 }, () => {
  // ── Compilation: tool callbacks ───────────────────────────────────

  it('tool callbacks compile in plan', async () => {
    const agent = new Agent({
      name: 'e2e_ts_s13_tool_cb',
      model: MODEL,
      maxTurns: 3,
      instructions: 'You are a helpful assistant. Use the echo tool.',
      tools: [echoTool],
      callbacks: [new ToolCallbackHandler()],
    });

    const plan = (await runtime.plan(agent)) as Record<string, unknown>;
    const workflowDef = plan.workflowDef as Record<string, unknown>;
    const metadata = workflowDef.metadata as Record<string, unknown>;
    const agentDef = metadata.agentDef as Record<string, unknown>;
    const callbacks = (agentDef.callbacks ?? []) as Array<Record<string, string>>;

    expect(
      callbacks.length,
      `[tool_callbacks_compile] Expected at least 2 callback entries ` +
        `(before_tool + after_tool), got ${callbacks.length}. ` +
        `Callbacks: ${JSON.stringify(callbacks)}`,
    ).toBeGreaterThanOrEqual(2);

    const positions = new Set(callbacks.map((cb) => cb.position));
    expect(
      positions.has('before_tool'),
      `[tool_callbacks_compile] 'before_tool' not found in callback ` +
        `positions: ${[...positions].join(', ')}. ` +
        `Callbacks: ${JSON.stringify(callbacks)}`,
    ).toBe(true);
    expect(
      positions.has('after_tool'),
      `[tool_callbacks_compile] 'after_tool' not found in callback ` +
        `positions: ${[...positions].join(', ')}. ` +
        `Callbacks: ${JSON.stringify(callbacks)}`,
    ).toBe(true);

    // Verify taskName format
    const beforeToolEntries = callbacks.filter((cb) => cb.position === 'before_tool');
    expect(
      beforeToolEntries.some((cb) => cb.taskName === 'e2e_ts_s13_tool_cb_before_tool'),
      `[tool_callbacks_compile] Expected taskName ` +
        `'e2e_ts_s13_tool_cb_before_tool' in before_tool entries: ` +
        `${JSON.stringify(beforeToolEntries)}`,
    ).toBe(true);

    const afterToolEntries = callbacks.filter((cb) => cb.position === 'after_tool');
    expect(
      afterToolEntries.some((cb) => cb.taskName === 'e2e_ts_s13_tool_cb_after_tool'),
      `[tool_callbacks_compile] Expected taskName ` +
        `'e2e_ts_s13_tool_cb_after_tool' in after_tool entries: ` +
        `${JSON.stringify(afterToolEntries)}`,
    ).toBe(true);
  });

  // ── Compilation: model callbacks ──────────────────────────────────

  it('model callbacks compile in plan', async () => {
    const agent = new Agent({
      name: 'e2e_ts_s13_model_cb',
      model: MODEL,
      maxTurns: 3,
      instructions: 'You are a helpful assistant.',
      callbacks: [new ModelCallbackHandler()],
    });

    const plan = (await runtime.plan(agent)) as Record<string, unknown>;
    const workflowDef = plan.workflowDef as Record<string, unknown>;
    const metadata = workflowDef.metadata as Record<string, unknown>;
    const agentDef = metadata.agentDef as Record<string, unknown>;
    const callbacks = (agentDef.callbacks ?? []) as Array<Record<string, string>>;

    expect(
      callbacks.length,
      `[model_callbacks_compile] Expected at least 2 callback entries ` +
        `(before_model + after_model), got ${callbacks.length}. ` +
        `Callbacks: ${JSON.stringify(callbacks)}`,
    ).toBeGreaterThanOrEqual(2);

    const positions = new Set(callbacks.map((cb) => cb.position));
    expect(
      positions.has('before_model'),
      `[model_callbacks_compile] 'before_model' not found in callback ` +
        `positions: ${[...positions].join(', ')}. ` +
        `Callbacks: ${JSON.stringify(callbacks)}`,
    ).toBe(true);
    expect(
      positions.has('after_model'),
      `[model_callbacks_compile] 'after_model' not found in callback ` +
        `positions: ${[...positions].join(', ')}. ` +
        `Callbacks: ${JSON.stringify(callbacks)}`,
    ).toBe(true);

    // Verify taskName format
    const beforeModelEntries = callbacks.filter((cb) => cb.position === 'before_model');
    expect(
      beforeModelEntries.some((cb) => cb.taskName === 'e2e_ts_s13_model_cb_before_model'),
      `[model_callbacks_compile] Expected taskName ` +
        `'e2e_ts_s13_model_cb_before_model' in before_model entries: ` +
        `${JSON.stringify(beforeModelEntries)}`,
    ).toBe(true);

    const afterModelEntries = callbacks.filter((cb) => cb.position === 'after_model');
    expect(
      afterModelEntries.some((cb) => cb.taskName === 'e2e_ts_s13_model_cb_after_model'),
      `[model_callbacks_compile] Expected taskName ` +
        `'e2e_ts_s13_model_cb_after_model' in after_model entries: ` +
        `${JSON.stringify(afterModelEntries)}`,
    ).toBe(true);
  });

  // ── Runtime: before_tool callback executes ────────────────────────

  it('before_tool callback executes at runtime', async () => {
    const agent = new Agent({
      name: 'e2e_ts_s13_before_tool',
      model: MODEL,
      maxTurns: 3,
      instructions:
        'You are a helpful assistant. You MUST call the echo_tool ' +
        "with text='hello' to answer the user. Always use the tool.",
      tools: [echoTool],
      callbacks: [new BeforeToolCallbackHandler()],
    });

    const result = await runtime.run(agent, 'Say hello using the echo tool.', { timeout: TIMEOUT });
    const diag = runDiagnostic(result as unknown as Record<string, unknown>);

    expect(
      result.executionId,
      `[before_tool_callback] No executionId. ${diag}`,
    ).toBeTruthy();
    expect(
      ['COMPLETED', 'TERMINATED'],
      `[before_tool_callback] Expected COMPLETED or TERMINATED, ` +
        `got '${result.status}'. ${diag}`,
    ).toContain(result.status);

    const wf = await getWorkflow(result.executionId);
    const allTasks = (wf.tasks ?? []) as Array<Record<string, unknown>>;
    const beforeToolTasks = allTasks.filter(
      (t) => ((t.referenceTaskName as string) ?? '').includes('before_tool'),
    );

    expect(
      beforeToolTasks.length,
      `[before_tool_callback] No task with 'before_tool' in ` +
        `referenceTaskName found. All task refs: ` +
        `${allTasks.map((t) => t.referenceTaskName ?? '?').join(', ')}. ${diag}`,
    ).toBeGreaterThan(0);

    const completed = beforeToolTasks.filter((t) => t.status === 'COMPLETED');
    expect(
      completed.length,
      `[before_tool_callback] before_tool task(s) exist but none ` +
        `reached COMPLETED. Statuses: ` +
        `${beforeToolTasks.map((t) => t.status).join(', ')}. ${diag}`,
    ).toBeGreaterThan(0);
  });

  // ── Runtime: after_tool callback executes ─────────────────────────

  it('after_tool callback executes at runtime', async () => {
    const agent = new Agent({
      name: 'e2e_ts_s13_after_tool',
      model: MODEL,
      maxTurns: 3,
      instructions:
        'You are a helpful assistant. You MUST call the echo_tool ' +
        "with text='world' to answer the user. Always use the tool.",
      tools: [echoTool],
      callbacks: [new AfterToolCallbackHandler()],
    });

    const result = await runtime.run(agent, 'Say world using the echo tool.', { timeout: TIMEOUT });
    const diag = runDiagnostic(result as unknown as Record<string, unknown>);

    expect(
      result.executionId,
      `[after_tool_callback] No executionId. ${diag}`,
    ).toBeTruthy();
    expect(
      ['COMPLETED', 'TERMINATED'],
      `[after_tool_callback] Expected COMPLETED or TERMINATED, ` +
        `got '${result.status}'. ${diag}`,
    ).toContain(result.status);

    const wf = await getWorkflow(result.executionId);
    const allTasks = (wf.tasks ?? []) as Array<Record<string, unknown>>;
    const afterToolTasks = allTasks.filter(
      (t) => ((t.referenceTaskName as string) ?? '').includes('after_tool'),
    );

    expect(
      afterToolTasks.length,
      `[after_tool_callback] No task with 'after_tool' in ` +
        `referenceTaskName found. All task refs: ` +
        `${allTasks.map((t) => t.referenceTaskName ?? '?').join(', ')}. ${diag}`,
    ).toBeGreaterThan(0);

    const completed = afterToolTasks.filter((t) => t.status === 'COMPLETED');
    expect(
      completed.length,
      `[after_tool_callback] after_tool task(s) exist but none ` +
        `reached COMPLETED. Statuses: ` +
        `${afterToolTasks.map((t) => t.status).join(', ')}. ${diag}`,
    ).toBeGreaterThan(0);
  });

  // ── Runtime: all callbacks don't block execution ──────────────────

  it('all callbacks do not block execution', async () => {
    const agent = new Agent({
      name: 'e2e_ts_s13_all_cb',
      model: MODEL,
      maxTurns: 3,
      instructions:
        'You are a helpful assistant. You MUST call the echo_tool ' +
        "with text='test' to answer the user. Always use the tool.",
      tools: [echoTool],
      callbacks: [new AllCallbackHandler()],
    });

    const result = await runtime.run(agent, "Use the echo tool with 'test'.", { timeout: TIMEOUT });
    const diag = runDiagnostic(result as unknown as Record<string, unknown>);

    expect(
      result.executionId,
      `[all_callbacks] No executionId. ${diag}`,
    ).toBeTruthy();
    expect(
      result.status,
      `[all_callbacks] Expected COMPLETED, got '${result.status}'. ` +
        `All 6 callbacks should not interfere with normal execution. ` +
        `${diag}`,
    ).toBe('COMPLETED');

    // Verify the echo_tool actually ran by finding its task.
    // Tool tasks use the LLM's call ID as referenceTaskName (e.g., call_XYZ),
    // but taskType or taskDefName contains the tool name.
    const wf = await getWorkflow(result.executionId);
    const allTasks = (wf.tasks ?? []) as Array<Record<string, unknown>>;
    const toolTasks = allTasks.filter(
      (t) =>
        ((t.taskType as string) ?? '').includes('echo_tool') ||
        ((t.taskDefName as string) ?? '').includes('echo_tool'),
    );

    expect(
      toolTasks.length,
      `[all_callbacks] No echo_tool task found. Callbacks may have ` +
        `blocked tool execution. All tasks: ` +
        `${allTasks.map((t) => `${t.referenceTaskName ?? '?'}[${t.taskType ?? '?'}]`).join(', ')}. ${diag}`,
    ).toBeGreaterThan(0);

    const completedTools = toolTasks.filter((t) => t.status === 'COMPLETED');
    expect(
      completedTools.length,
      `[all_callbacks] echo_tool task(s) exist but none reached ` +
        `COMPLETED. Callbacks may have interfered with tool execution. ` +
        `Statuses: ${toolTasks.map((t) => t.status).join(', ')}. ${diag}`,
    ).toBeGreaterThan(0);
  });
});
