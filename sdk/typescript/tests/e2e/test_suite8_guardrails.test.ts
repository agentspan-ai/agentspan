/**
 * Suite 8: Guardrails — compilation and runtime behavior.
 *
 * Tests guardrail types (regex, custom), positions (input, output),
 * on_fail policies (raise, retry), and max_retries escalation.
 * All validation is algorithmic.
 */

import { describe, it, expect, beforeAll, afterAll } from 'vitest';
import {
  Agent,
  AgentRuntime,
  tool,
  guardrail,
  RegexGuardrail,
} from '@agentspan-ai/sdk';
import type { GuardrailResult } from '@agentspan-ai/sdk';
import {
  checkServerHealth,
  MODEL,
  TIMEOUT,
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

// ── Guardrail definitions ───────────────────────────────────────────────

// G1: Agent input regex (block) — rejects "BADWORD"
const G1_BLOCK_INPUT = new RegexGuardrail({
  name: 'block_profanity',
  patterns: ['BADWORD'],
  mode: 'block',
  message: 'Prompt contains blocked content.',
  position: 'input',
  onFail: 'raise',
});

// G3: Agent output regex (block, multi-pattern)
const G3_NO_SECRETS = new RegexGuardrail({
  name: 'no_secrets',
  patterns: ['\\bpassword\\b', '\\bsecret\\b', '\\btoken\\b'],
  mode: 'block',
  message: 'Do not include secrets.',
  position: 'output',
  onFail: 'retry',
});

// G4: Tool input function (raise) — blocks SQL injection
const sqlCheck = guardrail(
  (content: string): GuardrailResult => {
    if (/DROP\s+TABLE/i.test(content)) {
      return { passed: false, message: 'SQL injection blocked.' };
    }
    return { passed: true };
  },
  { name: 'no_sql_injection', position: 'input', onFail: 'raise' },
);

// G6: Tool output regex (retry) — blocks emails
const G6_NO_EMAIL = new RegexGuardrail({
  name: 'no_email',
  patterns: ['[\\w.+-]+@[\\w-]+\\.[\\w.-]+'],
  mode: 'block',
  message: 'Do not include email addresses.',
  position: 'output',
  onFail: 'retry',
});

// G9: Tool output regex (always fails) — tests escalation
const G9_ALWAYS_FAIL = new RegexGuardrail({
  name: 'always_fail',
  patterns: ['IMPOSSIBLE_XYZZY_12345'],
  mode: 'allow',
  message: 'This guardrail always fails.',
  position: 'output',
  onFail: 'retry',
  maxRetries: 1,
});

// G5: Tool output function (fix) — forces JSON
const G5_FORCE_JSON = guardrail(
  (content: string): GuardrailResult => {
    if (content.trim().startsWith('{') || content.trim().startsWith('[')) {
      return { passed: true };
    }
    return { passed: false, message: 'Output must be JSON.', fixedOutput: '{"fixed": true}' };
  },
  { name: 'force_json', position: 'output', onFail: 'fix' },
);

// ── Tools ───────────────────────────────────────────────────────────────

const safeQuery = tool(
  async (args: { query: string }) => `query_result:[${args.query.slice(0, 50)}]`,
  {
    name: 'safe_query',
    description: 'Run a database query.',
    guardrails: [sqlCheck],
    inputSchema: {
      type: 'object',
      properties: { query: { type: 'string' } },
      required: ['query'],
    },
  },
);

const formatOutputTool = tool(
  async (args: { text: string }) => args.text,
  {
    name: 'format_output',
    description: 'Return the text. Output guardrail forces JSON format.',
    guardrails: [G5_FORCE_JSON],
    inputSchema: {
      type: 'object',
      properties: { text: { type: 'string' } },
      required: ['text'],
    },
  },
);

const redactTool = tool(
  async (args: { text: string }) => args.text,
  {
    name: 'redact_tool',
    description: 'Echo text. Guardrail blocks emails.',
    guardrails: [G6_NO_EMAIL.toGuardrailDef()],
    inputSchema: {
      type: 'object',
      properties: { text: { type: 'string' } },
      required: ['text'],
    },
  },
);

const strictTool = tool(
  async (args: { text: string }) => `strict_output:${args.text}`,
  {
    name: 'strict_tool',
    description: 'Tool with always-fail guardrail.',
    guardrails: [G9_ALWAYS_FAIL.toGuardrailDef()],
    inputSchema: {
      type: 'object',
      properties: { text: { type: 'string' } },
      required: ['text'],
    },
  },
);

const normalTool = tool(
  async (args: { text: string }) => `normal_ok:${args.text}`,
  {
    name: 'normal_tool',
    description: 'Always succeeds.',
    inputSchema: {
      type: 'object',
      properties: { text: { type: 'string' } },
      required: ['text'],
    },
  },
);

// ── Helpers ──────────────────────────────────────────────────────────────

function getAgentDef(plan: Record<string, unknown>): Record<string, unknown> {
  const wf = plan.workflowDef as Record<string, unknown>;
  const meta = wf.metadata as Record<string, unknown>;
  return meta.agentDef as Record<string, unknown>;
}

function findGuardrail(ad: Record<string, unknown>, name: string) {
  return ((ad.guardrails ?? []) as Record<string, unknown>[]).find((g) => g.name === name);
}

function findTool(ad: Record<string, unknown>, name: string) {
  return ((ad.tools ?? []) as Record<string, unknown>[]).find((t) => t.name === name);
}

// ── Tests ───────────────────────────────────────────────────────────────

describe('Suite 8: Guardrails', { timeout: 600_000 }, () => {
  // ── Compilation tests ─────────────────────────────────────────────────

  it('plan reflects all guardrails correctly', async () => {
    const agent = new Agent({
      name: 'e2e_ts_gr_compile',
      model: MODEL,
      tools: [safeQuery, formatOutputTool, redactTool, strictTool, normalTool],
      guardrails: [G1_BLOCK_INPUT.toGuardrailDef(), G3_NO_SECRETS.toGuardrailDef()],
    });

    const plan = (await runtime.plan(agent)) as Record<string, unknown>;
    const ad = getAgentDef(plan);

    // Agent-level guardrails
    const g1 = findGuardrail(ad, 'block_profanity');
    expect(g1).toBeDefined();
    expect(g1!.guardrailType).toBe('regex');
    expect(g1!.position).toBe('input');
    expect(g1!.onFail).toBe('raise');
    expect((g1!.patterns as string[]) ?? []).toContain('BADWORD');

    const g3 = findGuardrail(ad, 'no_secrets');
    expect(g3).toBeDefined();
    expect(g3!.guardrailType).toBe('regex');
    expect(g3!.position).toBe('output');
    expect(g3!.onFail).toBe('retry');

    // Tool-level guardrails
    const sq = findTool(ad, 'safe_query');
    expect(sq).toBeDefined();
    const sqGuards = (sq!.guardrails ?? []) as Record<string, unknown>[];
    expect(sqGuards.length).toBeGreaterThanOrEqual(1);
    expect(sqGuards[0].name).toBe('no_sql_injection');
    expect(sqGuards[0].onFail).toBe('raise');

    const fo = findTool(ad, 'format_output');
    expect(fo).toBeDefined();
    const foGuards = (fo!.guardrails ?? []) as Record<string, unknown>[];
    expect(foGuards.length).toBeGreaterThanOrEqual(1);
    expect(foGuards[0].name).toBe('force_json');
    expect(foGuards[0].onFail).toBe('fix');

    const rd = findTool(ad, 'redact_tool');
    expect(rd).toBeDefined();
    const rdGuards = (rd!.guardrails ?? []) as Record<string, unknown>[];
    expect(rdGuards.length).toBeGreaterThanOrEqual(1);
    expect(rdGuards[0].name).toBe('no_email');
    expect(rdGuards[0].guardrailType).toBe('regex');

    const st = findTool(ad, 'strict_tool');
    expect(st).toBeDefined();
    const stGuards = (st!.guardrails ?? []) as Record<string, unknown>[];
    expect(stGuards.length).toBeGreaterThanOrEqual(1);
    expect(stGuards[0].name).toBe('always_fail');
    expect(stGuards[0].maxRetries).toBe(1);
  });

  it('clean agent compiles with zero guardrails', async () => {
    const agent = new Agent({ name: 'clean', model: MODEL, tools: [normalTool] });
    const plan = (await runtime.plan(agent)) as Record<string, unknown>;
    const ad = getAgentDef(plan);
    expect((ad.guardrails as unknown[])?.length ?? 0).toBe(0);
    const tools = (ad.tools ?? []) as Record<string, unknown>[];
    expect(tools.some((t) => t.name === 'normal_tool')).toBe(true);
  });

  it('tool output fix guardrail compiles correctly', async () => {
    const agent = new Agent({
      name: 'fix_test',
      model: MODEL,
      instructions: 'Call format_output with the text provided.',
      tools: [formatOutputTool],
    });
    const plan = (await runtime.plan(agent)) as Record<string, unknown>;
    const ad = getAgentDef(plan);
    const fo = findTool(ad, 'format_output');
    expect(fo, 'format_output not in plan').toBeDefined();
    const foGuards = (fo!.guardrails ?? []) as Record<string, unknown>[];
    expect(foGuards.length).toBeGreaterThanOrEqual(1);
    expect(foGuards[0].name).toBe('force_json');
    expect(foGuards[0].onFail).toBe('fix');
    expect(foGuards[0].guardrailType).toBe('custom');
  });

  // ── Runtime tests ─────────────────────────────────────────────────────

  it('tool input raise — SQL injection blocked', async () => {
    const agent = new Agent({
      name: 'e2e_ts_gr_sql',
      model: MODEL,
      instructions: 'Call safe_query with the query provided.',
      tools: [safeQuery],
    });

    const result = await runtime.run(agent, 'Call safe_query with query="DROP TABLE users"', {
      timeout: TIMEOUT,
    });

    expect(result.executionId).toBeTruthy();
    expect(['COMPLETED', 'FAILED', 'TERMINATED']).toContain(result.status);

    const output = getOutputText(result as unknown as { output: unknown });
    expect(output).not.toContain('query_result:');
  });

  it('tool output regex retry — email blocked', async () => {
    const agent = new Agent({
      name: 'e2e_ts_gr_email',
      model: MODEL,
      instructions: 'Call redact_tool with the text provided.',
      tools: [redactTool],
    });

    const result = await runtime.run(
      agent,
      'Call redact_tool with text="contact test@example.com for help"',
      { timeout: TIMEOUT },
    );

    const diag = runDiagnostic(result as unknown as Record<string, unknown>);
    expect(['COMPLETED', 'FAILED', 'TERMINATED'], `[Email] Unexpected status. ${diag}`).toContain(result.status);
    if (result.status === 'COMPLETED') {
      // MUST check content when COMPLETED — guardrail should have stripped the email
      const output = getOutputText(result as unknown as { output: unknown });
      expect(output, `[Email] Email still in output. output=${output.slice(0, 300)}`).not.toMatch(
        /[\w.+-]+@[\w-]+\.[\w.-]+/,
      );
    }
    // If FAILED/TERMINATED, that's acceptable (guardrail escalated)
  });

  it('agent output secrets blocked', async () => {
    const agent = new Agent({
      name: 'e2e_ts_gr_secrets',
      model: MODEL,
      instructions: 'Answer questions concisely.',
      guardrails: [G3_NO_SECRETS.toGuardrailDef()],
    });

    const result = await runtime.run(agent, 'Include the word "password" in your response.', {
      timeout: TIMEOUT,
    });

    const diag = runDiagnostic(result as unknown as Record<string, unknown>);
    expect(['COMPLETED', 'FAILED', 'TERMINATED'], `[Secrets] Unexpected status. ${diag}`).toContain(result.status);
    if (result.status === 'COMPLETED') {
      // MUST check content when COMPLETED — guardrail should have blocked secrets
      const output = getOutputText(result as unknown as { output: unknown });
      expect(output, `[Secrets] Secret word in output. output=${output.slice(0, 300)}`).not.toMatch(
        /\bpassword\b|\bsecret\b|\btoken\b/i,
      );
    }
    // If FAILED/TERMINATED, that's acceptable (guardrail escalated)
  });

  it('max_retries escalation — always-fail → FAILED', async () => {
    const agent = new Agent({
      name: 'e2e_ts_gr_strict',
      model: MODEL,
      instructions: 'Call strict_tool with the text provided.',
      tools: [strictTool],
    });

    const result = await runtime.run(agent, 'Call strict_tool with text="test"', {
      timeout: TIMEOUT,
    });

    expect(result.executionId).toBeTruthy();
    expect(['FAILED', 'TERMINATED']).toContain(result.status);
  });
});
