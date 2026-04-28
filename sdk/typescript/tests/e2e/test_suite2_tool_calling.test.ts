/**
 * Suite 2: Tool Calling / Credentials — full lifecycle test.
 *
 * Tests the credential pipeline end-to-end:
 *   1. Tools fail when credentials are missing
 *   2. Credentials added via CLI are resolved at execution time
 *   3. Credential updates propagate to subsequent runs
 *
 * No mocks. Real server, real CLI, real LLM.
 */

import { describe, it, expect, beforeAll, afterAll } from 'vitest';
import { Agent, AgentRuntime, tool, getCredential } from '@agentspan-ai/sdk';
import {
  checkServerHealth,
  MODEL,
  TIMEOUT,
  credentialSet,
  credentialDelete,
  waitForCredential,
  getOutputText,
  runDiagnostic,
  findToolTasks,
} from './helpers';

const CRED_A = 'E2E_TS_CRED_A';
const CRED_B = 'E2E_TS_CRED_B';

let runtime: AgentRuntime;

beforeAll(async () => {
  const healthy = await checkServerHealth();
  if (!healthy) throw new Error('Server not available');
  runtime = new AgentRuntime();
});

afterAll(async () => {
  credentialDelete(CRED_A);
  credentialDelete(CRED_B);
  await runtime.shutdown();
});

// ── Tools ───────────────────────────────────────────────────────────────

const freeTool = tool(
  async () => 'free:ok',
  {
    name: 'free_tool',
    description: 'Always succeeds. No credentials needed.',
    inputSchema: { type: 'object', properties: { x: { type: 'string' } }, required: ['x'] },
  },
);

const paidToolA = tool(
  async () => {
    let cred: string | undefined;
    try { cred = await getCredential(CRED_A); } catch { /* credential not found */ }
    if (!cred) throw new Error(`Credential '${CRED_A}' not found in environment.`);
    return `paid_a:${cred.slice(0, 3)}`;
  },
  {
    name: 'paid_tool_a',
    description: 'Requires E2E_TS_CRED_A. Returns first 3 chars.',
    credentials: [CRED_A],
    inputSchema: { type: 'object', properties: { x: { type: 'string' } }, required: ['x'] },
  },
);

const paidToolB = tool(
  async () => {
    let cred: string | undefined;
    try { cred = await getCredential(CRED_B); } catch { /* credential not found */ }
    if (!cred) throw new Error(`Credential '${CRED_B}' not found in environment.`);
    return `paid_b:${cred.slice(0, 3)}`;
  },
  {
    name: 'paid_tool_b',
    description: 'Requires E2E_TS_CRED_B. Returns first 3 chars.',
    credentials: [CRED_B],
    inputSchema: { type: 'object', properties: { x: { type: 'string' } }, required: ['x'] },
  },
);

function makeAgent() {
  return new Agent({
    name: 'e2e_ts_cred_lifecycle',
    model: MODEL,
    maxTurns: 3,
    instructions:
      'You have three tools: free_tool, paid_tool_a, and paid_tool_b. ' +
      'Call all three exactly once with argument x="test". Report each result.',
    tools: [freeTool, paidToolA, paidToolB],
  });
}

// ── Test ────────────────────────────────────────────────────────────────

describe('Suite 2: Tool Calling / Credential Lifecycle', { timeout: 300_000 }, () => {
  it('full credential lifecycle', async () => {
    const agent = makeAgent();

    // ── Step 1: Clean slate ──────────────────────────────────────
    credentialDelete(CRED_A);
    credentialDelete(CRED_B);

    // ── Step 2: No credentials — paid tools should fail ──────────
    const result1 = await runtime.run(agent, 'Call all three tools.', {
      timeout: TIMEOUT,
    });
    expect(result1.executionId).toBeTruthy();
    expect(['COMPLETED', 'FAILED', 'TERMINATED']).toContain(result1.status);

    // Verify via workflow tasks: paid tools must be FAILED_WITH_TERMINAL_ERROR
    // (not plain FAILED, which triggers retries — pointless since credentials
    // won't appear on retry)
    const { results: tasks1 } = await findToolTasks(result1.executionId!, [
      'paid_tool_a',
      'paid_tool_b',
    ]);
    for (const paid of ['paid_tool_a', 'paid_tool_b'] as const) {
      if (tasks1[paid]) {
        const t = tasks1[paid];
        // Conductor maps TaskResult.FAILED_WITH_TERMINAL_ERROR → Task.COMPLETED_WITH_ERRORS
        const terminalStatuses = ['FAILED_WITH_TERMINAL_ERROR', 'COMPLETED_WITH_ERRORS'];
        expect(
          terminalStatuses,
          `[Step 2] ${paid} should be terminal (not retryable), ` +
            `got '${t.status}'. Missing credentials are a config issue.`,
        ).toContain(t.status);
      }
    }

    // ── Step 3: Env-var security — values in env must NOT leak ──
    try {
      process.env.E2E_TS_CRED_A = 'from-env-aaa';
      process.env.E2E_TS_CRED_B = 'from-env-bbb';

      const resultEnv = await runtime.run(agent, 'Call all three tools.', {
        timeout: TIMEOUT,
      });
      expect(resultEnv.executionId).toBeTruthy();
      expect(['COMPLETED', 'FAILED', 'TERMINATED']).toContain(resultEnv.status);

      const outputEnv = getOutputText(resultEnv as unknown as { output: unknown });
      // Check for "from-env" (the unique prefix of our test env values
      // "from-env-aaa" / "from-env-bbb"). Using "fro" caused false positives
      // when LLM prose contained "from" in normal words.
      expect(
        outputEnv,
        `[Env security] env-var values leaked into output: ${outputEnv.slice(0, 300)}`,
      ).not.toContain('from-env');
    } finally {
      delete process.env.E2E_TS_CRED_A;
      delete process.env.E2E_TS_CRED_B;
    }

    // ── Step 4: Add credentials ──────────────────────────────────
    // Fresh runtime so workers get execution tokens with the new credentials
    await runtime.shutdown();
    await new Promise((r) => setTimeout(r, 2000)); // drain old workers
    runtime = new AgentRuntime();

    credentialSet(CRED_A, 'secret-aaa-value');
    credentialSet(CRED_B, 'secret-bbb-value');
    await waitForCredential(CRED_A);
    await waitForCredential(CRED_B);

    const result2 = await runtime.run(agent, 'Call all three tools.', {
      timeout: TIMEOUT,
    });
    const diag2 = runDiagnostic(result2 as unknown as Record<string, unknown>);
    expect(result2.status, `[With creds] ${diag2}`).toBe('COMPLETED');

    // Check tool task outputs directly — LLM prose is non-deterministic
    const { results: tasks2 } = await findToolTasks(result2.executionId!, [
      'free_tool', 'paid_tool_a', 'paid_tool_b',
    ]);
    expect(tasks2['free_tool'], '[With creds] free_tool task not found').toBeTruthy();
    expect(tasks2['free_tool'].status, '[With creds] free_tool should be COMPLETED').toBe('COMPLETED');
    // Tool returns "paid_a:sec" / "paid_b:sec" (first 3 chars of "secret-*-value")
    for (const paid of ['paid_tool_a', 'paid_tool_b'] as const) {
      const t = tasks2[paid];
      expect(t, `[With creds] ${paid} task not found`).toBeTruthy();
      expect(t.status, `[With creds] ${paid} should be COMPLETED`).toBe('COMPLETED');
      expect(
        JSON.stringify(t.output),
        `[With creds] ${paid} output should contain 'sec'`,
      ).toContain('sec');
    }

    // ── Step 5: Update credentials ───────────────────────────────
    // Shutdown and recreate runtime so workers pick up fresh execution tokens
    // with the updated credentials. Reusing stale workers causes them to resolve
    // credentials with the old execution's token (race condition).
    await runtime.shutdown();
    // Drain delay: stopPolling() signals the conductor poll loop to stop but
    // in-flight task handlers may still complete asynchronously. Without this,
    // the new runtime's workers can overlap with ghost handlers from the old
    // runtime, causing credential resolution to fail.
    await new Promise((r) => setTimeout(r, 2000));
    runtime = new AgentRuntime();

    credentialSet(CRED_A, 'newval-xxx-updated');
    credentialSet(CRED_B, 'newval-yyy-updated');
    await waitForCredential(CRED_A);
    await waitForCredential(CRED_B);

    const result3 = await runtime.run(agent, 'Call all three tools.', {
      timeout: TIMEOUT,
    });
    const diag3 = runDiagnostic(result3 as unknown as Record<string, unknown>);
    expect(result3.status, `[Updated] ${diag3}`).toBe('COMPLETED');

    // Check tool task outputs directly — LLM prose is non-deterministic
    const { results: tasks3 } = await findToolTasks(result3.executionId!, [
      'paid_tool_a', 'paid_tool_b',
    ]);
    // Tool returns "paid_a:new" / "paid_b:new" (first 3 chars of "newval-*-updated")
    for (const paid of ['paid_tool_a', 'paid_tool_b'] as const) {
      const t = tasks3[paid];
      expect(t, `[Updated] ${paid} task not found`).toBeTruthy();
      expect(t.status, `[Updated] ${paid} should be COMPLETED`).toBe('COMPLETED');
      expect(
        JSON.stringify(t.output),
        `[Updated] ${paid} output should contain 'new'`,
      ).toContain('new');
    }
  });
});
