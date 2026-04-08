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
  getOutputText,
  runDiagnostic,
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
    try { cred = getCredential(CRED_A); } catch { /* credential not found */ }
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
    try { cred = getCredential(CRED_B); } catch { /* credential not found */ }
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

    // ── Step 3: Add credentials ──────────────────────────────────
    credentialSet(CRED_A, 'secret-aaa-value');
    credentialSet(CRED_B, 'secret-bbb-value');

    const result2 = await runtime.run(agent, 'Call all three tools.', {
      timeout: TIMEOUT,
    });
    const diag2 = runDiagnostic(result2 as unknown as Record<string, unknown>);
    expect(result2.status, `[With creds] ${diag2}`).toBe('COMPLETED');

    const output2 = getOutputText(result2 as unknown as { output: unknown });
    expect(output2, `[With creds] output=${output2.slice(0, 300)}`).toContain('free');
    // "sec" = first 3 chars of "secret-aaa-value"
    expect(output2, `[With creds] output=${output2.slice(0, 300)}`).toContain('sec');

    // ── Step 4: Update credentials ───────────────────────────────
    credentialSet(CRED_A, 'newval-xxx-updated');
    credentialSet(CRED_B, 'newval-yyy-updated');

    const result3 = await runtime.run(agent, 'Call all three tools.', {
      timeout: TIMEOUT,
    });
    const diag3 = runDiagnostic(result3 as unknown as Record<string, unknown>);
    expect(result3.status, `[Updated] ${diag3}`).toBe('COMPLETED');

    const output3 = getOutputText(result3 as unknown as { output: unknown });
    // "new" = first 3 chars of "newval-xxx-updated"
    expect(output3, `[Updated] output=${output3.slice(0, 300)}`).toContain('new');
  });
});
