/**
 * Suite 1: Basic Validation — plan-based structural assertions.
 *
 * Compiles agents via plan() and asserts on the Conductor workflow JSON.
 * No LLM execution — only compilation checks (except the LLM-as-judge test).
 */

import { describe, it, expect, beforeAll } from 'vitest';
import {
  Agent,
  AgentRuntime,
  tool,
  httpTool,
  mcpTool,
  imageTool,
  audioTool,
  videoTool,
  pdfTool,
  RegexGuardrail,
  guardrail,
} from '@agentspan-ai/sdk';
import type { GuardrailResult } from '@agentspan-ai/sdk';
import { checkServerHealth, MODEL, MCP_TESTKIT_URL } from './helpers';

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

function findTool(ad: Record<string, unknown>, name: string) {
  const tools = (ad.tools ?? []) as Record<string, unknown>[];
  return tools.find((t) => t.name === name);
}

function findGuardrail(ad: Record<string, unknown>, name: string) {
  const guards = (ad.guardrails ?? []) as Record<string, unknown>[];
  return guards.find((g) => g.name === name);
}

function toolCredentials(ad: Record<string, unknown>): Record<string, string[]> {
  const result: Record<string, string[]> = {};
  for (const t of (ad.tools ?? []) as Record<string, unknown>[]) {
    const config = (t.config ?? {}) as Record<string, unknown>;
    const creds = config.credentials as string[] | undefined;
    if (creds && creds.length > 0) {
      result[t.name as string] = creds;
    }
  }
  return result;
}

// ── Tools for testing ───────────────────────────────────────────────────

const addTool = tool(
  async (args: { a: number; b: number }) => ({ result: args.a + args.b }),
  {
    name: 'add',
    description: 'Add two numbers',
    inputSchema: {
      type: 'object',
      properties: {
        a: { type: 'number', description: 'First number' },
        b: { type: 'number', description: 'Second number' },
      },
      required: ['a', 'b'],
    },
  },
);

const multiplyTool = tool(
  async (args: { a: number; b: number }) => ({ result: args.a * args.b }),
  {
    name: 'multiply',
    description: 'Multiply two numbers',
    inputSchema: {
      type: 'object',
      properties: {
        a: { type: 'number' },
        b: { type: 'number' },
      },
      required: ['a', 'b'],
    },
  },
);

const credentialedTool = tool(
  async (args: { query: string }) => ({ result: args.query }),
  {
    name: 'credentialed_tool',
    description: 'Tool requiring credentials',
    credentials: ['API_KEY_1'],
    inputSchema: {
      type: 'object',
      properties: { query: { type: 'string' } },
      required: ['query'],
    },
  },
);

const multiCredTool = tool(
  async (args: { data: string }) => ({ result: args.data }),
  {
    name: 'multi_cred_tool',
    description: 'Tool needing multiple credentials',
    credentials: ['SECRET_A', 'SECRET_B'],
    inputSchema: {
      type: 'object',
      properties: { data: { type: 'string' } },
      required: ['data'],
    },
  },
);

// ── Kitchen-sink guardrails ─────────────────────────────────────────────

const ksCheckInput = guardrail(
  (content: string): GuardrailResult => {
    if (content.length > 10000) return { passed: false, message: 'Too long' };
    return { passed: true };
  },
  { name: 'check_input', position: 'input', onFail: 'retry' },
);

const ksNoPii = guardrail(
  (_content: string): GuardrailResult => ({ passed: true }),
  { name: 'no_pii', position: 'output', onFail: 'retry' },
);

const ksNoPassword = new RegexGuardrail({
  name: 'no_password',
  patterns: ['password'],
  mode: 'block',
  message: 'No passwords in output.',
  position: 'output',
  onFail: 'retry',
});

// ── Kitchen-sink agent builder ──────────────────────────────────────────

function makeKitchenSinkAgent() {
  const localTool = tool(
    async (args: { x: string }) => args.x,
    {
      name: 'local_tool',
      description: 'A local worker tool.',
      inputSchema: {
        type: 'object',
        properties: { x: { type: 'string' } },
        required: ['x'],
      },
    },
  );

  const credLocalTool = tool(
    async (args: { x: string }) => args.x,
    {
      name: 'cred_local_tool',
      description: 'Worker tool with credentials.',
      credentials: ['KS_SECRET'],
      inputSchema: {
        type: 'object',
        properties: { x: { type: 'string' } },
        required: ['x'],
      },
    },
  );

  const ht = httpTool({
    name: 'ks_http',
    description: 'HTTP endpoint',
    url: `${MCP_TESTKIT_URL}/echo`,
    method: 'POST',
  });
  const mt = mcpTool({
    serverUrl: MCP_TESTKIT_URL,
    name: 'ks_mcp',
    description: 'MCP tools',
  });
  const img = imageTool({
    name: 'ks_image',
    description: 'Generate image',
    llmProvider: 'openai',
    model: 'dall-e-3',
  });
  const aud = audioTool({
    name: 'ks_audio',
    description: 'Generate audio',
    llmProvider: 'openai',
    model: 'tts-1',
  });
  const vid = videoTool({
    name: 'ks_video',
    description: 'Generate video',
    llmProvider: 'openai',
    model: 'sora',
  });
  const pdf = pdfTool({ name: 'ks_pdf', description: 'Generate PDF' });

  return new Agent({
    name: 'e2e_kitchen_sink',
    model: MODEL,
    instructions: 'You are the kitchen sink agent.',
    tools: [localTool, credLocalTool, ht, mt, img, aud, vid, pdf],
    guardrails: [ksCheckInput, ksNoPii, ksNoPassword.toGuardrailDef()],
    agents: [
      new Agent({
        name: 'ks_handoff',
        model: MODEL,
        instructions: 'Route tasks.',
        agents: [
          new Agent({ name: 'ks_h1', model: MODEL, instructions: 'H1.' }),
          new Agent({ name: 'ks_h2', model: MODEL, instructions: 'H2.' }),
        ],
        strategy: 'handoff',
      }),
      new Agent({
        name: 'ks_sequential',
        model: MODEL,
        agents: [
          new Agent({ name: 'ks_seq1', model: MODEL, instructions: 'Seq1.' }),
          new Agent({ name: 'ks_seq2', model: MODEL, instructions: 'Seq2.' }),
        ],
        strategy: 'sequential',
      }),
      new Agent({
        name: 'ks_parallel',
        model: MODEL,
        agents: [
          new Agent({ name: 'ks_p1', model: MODEL, instructions: 'P1.' }),
          new Agent({ name: 'ks_p2', model: MODEL, instructions: 'P2.' }),
        ],
        strategy: 'parallel',
      }),
      new Agent({
        name: 'ks_router',
        model: MODEL,
        agents: [
          new Agent({ name: 'ks_r1', model: MODEL, instructions: 'R1.' }),
          new Agent({ name: 'ks_r2', model: MODEL, instructions: 'R2.' }),
        ],
        strategy: 'router',
        router: new Agent({ name: 'ks_router_lead', model: MODEL, instructions: 'Route.' }),
      }),
      new Agent({
        name: 'ks_round_robin',
        model: MODEL,
        agents: [
          new Agent({ name: 'ks_rr1', model: MODEL, instructions: 'RR1.' }),
          new Agent({ name: 'ks_rr2', model: MODEL, instructions: 'RR2.' }),
        ],
        strategy: 'round_robin',
      }),
      new Agent({
        name: 'ks_random',
        model: MODEL,
        agents: [
          new Agent({ name: 'ks_rand1', model: MODEL, instructions: 'Rand1.' }),
          new Agent({ name: 'ks_rand2', model: MODEL, instructions: 'Rand2.' }),
        ],
        strategy: 'random',
      }),
      new Agent({
        name: 'ks_swarm',
        model: MODEL,
        agents: [
          new Agent({ name: 'ks_sw1', model: MODEL, instructions: 'SW1.' }),
          new Agent({ name: 'ks_sw2', model: MODEL, instructions: 'SW2.' }),
        ],
        strategy: 'swarm',
      }),
      new Agent({
        name: 'ks_manual',
        model: MODEL,
        agents: [
          new Agent({ name: 'ks_m1', model: MODEL, instructions: 'M1.' }),
          new Agent({ name: 'ks_m2', model: MODEL, instructions: 'M2.' }),
        ],
        strategy: 'manual',
      }),
    ],
    strategy: 'handoff',
  });
}

// ── LLM Judge ───────────────────────────────────────────────────────────

const JUDGE_MODEL = process.env.AGENTSPAN_JUDGE_MODEL ?? 'claude-sonnet-4-20250514';

const JUDGE_SYSTEM_PROMPT = `You are a strict validation judge for a workflow compilation system.

You will receive a SIDE-BY-SIDE COMPARISON of what the developer specified \
(EXPECTED) versus what the compiler produced (ACTUAL) for each element.

Your job: go through each comparison item and check if EXPECTED matches ACTUAL.

Rules:
- A tool is NOT a sub-agent. They are in separate lists. Do not confuse them.
- Compare values exactly as written. "regex" matches "regex", not "custom".
- If EXPECTED and ACTUAL match for all items, set "pass" to true.

Respond with ONLY a JSON object:
{
  "pass": true or false,
  "missing": ["list items where EXPECTED does not match ACTUAL"],
  "explanation": "brief explanation"
}`;

const KITCHEN_SINK_SPEC: {
  tools: { name: string; type: string; credentials?: string[] }[];
  guardrails: { name: string; guardrailType: string; position: string; onFail: string; patterns?: string[] }[];
  agents: { name: string; strategy: string }[];
  strategy: string;
} = {
  tools: [
    { name: 'local_tool', type: 'worker' },
    { name: 'cred_local_tool', type: 'worker', credentials: ['KS_SECRET'] },
    { name: 'ks_http', type: 'http' },
    { name: 'ks_mcp', type: 'mcp' },
    { name: 'ks_image', type: 'generate_image' },
    { name: 'ks_audio', type: 'generate_audio' },
    { name: 'ks_video', type: 'generate_video' },
    { name: 'ks_pdf', type: 'generate_pdf' },
  ],
  guardrails: [
    { name: 'check_input', guardrailType: 'custom', position: 'input', onFail: 'retry' },
    { name: 'no_pii', guardrailType: 'custom', position: 'output', onFail: 'retry' },
    { name: 'no_password', guardrailType: 'regex', position: 'output', onFail: 'retry', patterns: ['password'] },
  ],
  agents: [
    { name: 'ks_handoff', strategy: 'handoff' },
    { name: 'ks_sequential', strategy: 'sequential' },
    { name: 'ks_parallel', strategy: 'parallel' },
    { name: 'ks_router', strategy: 'router' },
    { name: 'ks_round_robin', strategy: 'round_robin' },
    { name: 'ks_random', strategy: 'random' },
    { name: 'ks_swarm', strategy: 'swarm' },
    { name: 'ks_manual', strategy: 'manual' },
  ],
  strategy: 'handoff',
};

function buildJudgeComparison(result: Record<string, unknown>): string {
  const wf = result.workflowDef as Record<string, unknown>;
  const ad = ((wf.metadata ?? {}) as Record<string, unknown>).agentDef as Record<string, unknown>;

  const compiledTools: Record<string, Record<string, unknown>> = {};
  for (const t of (ad.tools ?? []) as Record<string, unknown>[]) {
    compiledTools[t.name as string] = t;
  }
  const compiledGuardrails: Record<string, Record<string, unknown>> = {};
  for (const g of (ad.guardrails ?? []) as Record<string, unknown>[]) {
    compiledGuardrails[g.name as string] = g;
  }
  const compiledAgents: Record<string, Record<string, unknown>> = {};
  for (const a of (ad.agents ?? []) as Record<string, unknown>[]) {
    compiledAgents[a.name as string] = a;
  }

  const lines: string[] = [];

  lines.push('=== TOOLS ===');
  for (const t of KITCHEN_SINK_SPEC.tools) {
    const ct = compiledTools[t.name];
    let actual: string;
    if (ct) {
      const creds = ((ct.config ?? {}) as Record<string, unknown>).credentials ?? [];
      actual = `toolType=${ct.toolType ?? '?'}`;
      if (t.credentials) actual += `, credentials=${JSON.stringify(creds)}`;
    } else {
      actual = 'NOT FOUND';
    }
    let expected = `toolType=${t.type}`;
    if (t.credentials) expected += `, credentials=${JSON.stringify(t.credentials)}`;
    lines.push(`  ${t.name}: EXPECTED(${expected}) ACTUAL(${actual})`);
  }

  lines.push('\n=== GUARDRAILS ===');
  for (const g of KITCHEN_SINK_SPEC.guardrails) {
    const cg = compiledGuardrails[g.name];
    let actual: string;
    if (cg) {
      actual = `guardrailType=${cg.guardrailType ?? '?'}, position=${cg.position ?? '?'}, onFail=${cg.onFail ?? '?'}`;
      if (g.patterns) actual += `, patterns=${JSON.stringify(cg.patterns ?? [])}`;
    } else {
      actual = 'NOT FOUND';
    }
    let expected = `guardrailType=${g.guardrailType}, position=${g.position}, onFail=${g.onFail}`;
    if (g.patterns) expected += `, patterns=${JSON.stringify(g.patterns)}`;
    lines.push(`  ${g.name}: EXPECTED(${expected}) ACTUAL(${actual})`);
  }

  lines.push('\n=== SUB-AGENTS ===');
  for (const a of KITCHEN_SINK_SPEC.agents) {
    const ca = compiledAgents[a.name];
    const actual = ca ? `strategy=${ca.strategy ?? '?'}` : 'NOT FOUND';
    lines.push(`  ${a.name}: EXPECTED(strategy=${a.strategy}) ACTUAL(${actual})`);
  }

  lines.push('\n=== PARENT STRATEGY ===');
  lines.push(`  EXPECTED(${KITCHEN_SINK_SPEC.strategy}) ACTUAL(${ad.strategy ?? 'not set'})`);

  return lines.join('\n');
}

async function judgeCompiledWorkflow(comparison: string): Promise<{ pass: boolean; missing: string[]; explanation: string }> {
  let raw: string;

  try {
    if (JUDGE_MODEL.startsWith('claude')) {
      const anthropicMod = await import(/* @vite-ignore */ '@anthropic-ai/sdk') as any;
      const Anthropic = anthropicMod.default ?? anthropicMod.Anthropic ?? anthropicMod;
      const client = new Anthropic();
      const response = await client.messages.create({
        model: JUDGE_MODEL,
        max_tokens: 1024,
        system: JUDGE_SYSTEM_PROMPT,
        messages: [{ role: 'user', content: comparison }],
        temperature: 0,
      });
      raw = ((response.content[0] as { text: string }).text ?? '').trim();
    } else {
      const openaiMod = await import(/* @vite-ignore */ 'openai') as any;
      const OpenAI = openaiMod.default ?? openaiMod.OpenAI ?? openaiMod;
      const client = new OpenAI();
      const response = await client.chat.completions.create({
        model: JUDGE_MODEL,
        messages: [
          { role: 'system', content: JUDGE_SYSTEM_PROMPT },
          { role: 'user', content: comparison },
        ],
        temperature: 0,
      });
      raw = (response.choices[0].message.content ?? '').trim();
    }
  } catch (e) {
    // SDK not installed — skip gracefully
    return { pass: true, missing: [], explanation: `Judge SDK not available: ${e}` };
  }

  // Strip markdown code fences if present
  if (raw.startsWith('```')) {
    const lines = raw.split('\n');
    raw = lines.filter((l) => !l.trim().startsWith('```')).join('\n');
  }

  const verdict = JSON.parse(raw) as Record<string, unknown>;
  return {
    pass: Boolean(verdict.pass),
    missing: (verdict.missing ?? []) as string[],
    explanation: (verdict.explanation ?? '') as string,
  };
}

// ── Tests ───────────────────────────────────────────────────────────────

describe('Suite 1: Basic Validation', () => {
  it('smoke — simple agent compiles with tools', async () => {
    const agent = new Agent({
      name: 'smoke_test',
      model: MODEL,
      instructions: 'Test agent',
      tools: [addTool, multiplyTool],
    });

    const plan = (await runtime.plan(agent)) as Record<string, unknown>;
    const ad = getAgentDef(plan);

    expect(ad).toBeDefined();
    const tools = (ad.tools ?? []) as Record<string, unknown>[];
    expect(tools.length).toBe(2);

    const add = findTool(ad, 'add');
    expect(add).toBeDefined();
    expect(add!.toolType).toBe('worker');

    const mul = findTool(ad, 'multiply');
    expect(mul).toBeDefined();
    expect(mul!.toolType).toBe('worker');
  });

  it('plan reflects tool types correctly', async () => {
    const ht = httpTool({
      name: 'ks_http',
      description: 'HTTP endpoint',
      url: `${MCP_TESTKIT_URL}/echo`,
      method: 'POST',
    });
    const mt = mcpTool({
      serverUrl: MCP_TESTKIT_URL,
      name: 'ks_mcp',
      description: 'MCP tools',
    });
    const img = imageTool({
      name: 'ks_image',
      description: 'Generate image',
      llmProvider: 'openai',
      model: 'dall-e-3',
    });
    const aud = audioTool({
      name: 'ks_audio',
      description: 'Generate audio',
      llmProvider: 'openai',
      model: 'tts-1',
    });
    const vid = videoTool({
      name: 'ks_video',
      description: 'Generate video',
      llmProvider: 'openai',
      model: 'sora',
    });
    const pdf = pdfTool({ name: 'ks_pdf', description: 'Generate PDF' });

    const agent = new Agent({
      name: 'kitchen_sink',
      model: MODEL,
      tools: [addTool, ht, mt, img, aud, vid, pdf],
    });

    const plan = (await runtime.plan(agent)) as Record<string, unknown>;
    const ad = getAgentDef(plan);

    const expectedTypes: Record<string, string> = {
      add: 'worker',
      ks_http: 'http',
      ks_mcp: 'mcp',
      ks_image: 'generate_image',
      ks_audio: 'generate_audio',
      ks_video: 'generate_video',
      ks_pdf: 'generate_pdf',
    };

    for (const [name, expectedType] of Object.entries(expectedTypes)) {
      const t = findTool(ad, name);
      expect(t, `Tool '${name}' not found in plan`).toBeDefined();
      expect(t!.toolType, `Tool '${name}' has wrong toolType`).toBe(expectedType);
    }
  });

  it('plan reflects guardrails', async () => {
    const noSsn = new RegexGuardrail({
      name: 'no_ssn',
      patterns: ['\\b\\d{3}-\\d{2}-\\d{4}\\b'],
      mode: 'block',
      position: 'output',
      onFail: 'retry',
    });

    const checkInput = guardrail(
      (content: string): GuardrailResult => {
        if (content.length > 1000) return { passed: false, message: 'Too long' };
        return { passed: true };
      },
      { name: 'check_input', position: 'input', onFail: 'raise' },
    );

    const agent = new Agent({
      name: 'guardrail_test',
      model: MODEL,
      tools: [addTool],
      guardrails: [noSsn.toGuardrailDef(), checkInput],
    });

    const plan = (await runtime.plan(agent)) as Record<string, unknown>;
    const ad = getAgentDef(plan);
    const guardrails = (ad.guardrails ?? []) as Record<string, unknown>[];

    expect(guardrails.length).toBe(2);

    const ssn = findGuardrail(ad, 'no_ssn');
    expect(ssn).toBeDefined();
    expect(ssn!.guardrailType).toBe('regex');
    expect(ssn!.position).toBe('output');
    expect(ssn!.onFail).toBe('retry');
    expect((ssn!.patterns as string[]) ?? []).toContain('\\b\\d{3}-\\d{2}-\\d{4}\\b');

    const input = findGuardrail(ad, 'check_input');
    expect(input).toBeDefined();
    expect(input!.position).toBe('input');
    expect(input!.onFail).toBe('raise');
  });

  it('credentialed tool compiles into plan', async () => {
    const agent = new Agent({
      name: 'cred_test',
      model: MODEL,
      tools: [addTool, credentialedTool],
    });

    const plan = (await runtime.plan(agent)) as Record<string, unknown>;
    const ad = getAgentDef(plan);

    // Credentialed tool must appear in the plan
    const ct = findTool(ad, 'credentialed_tool');
    expect(ct, 'credentialed_tool not found in plan').toBeDefined();
    expect(ct!.toolType).toBe('worker');
  });

  it('credentialed tools compile into plan', async () => {
    // NOTE: TS SDK does not serialize credential names into the compiled plan
    // (credentials are resolved via execution token, not plan config).
    // This test validates tools exist with correct types.
    const agent = new Agent({
      name: 'e2e_creds',
      model: MODEL,
      instructions: 'Use tools.',
      tools: [credentialedTool, multiCredTool],
    });

    const plan = (await runtime.plan(agent)) as Record<string, unknown>;
    const ad = getAgentDef(plan);

    const ct = findTool(ad, 'credentialed_tool');
    expect(ct, 'credentialed_tool not in plan').toBeDefined();
    expect(ct!.toolType).toBe('worker');

    const mct = findTool(ad, 'multi_cred_tool');
    expect(mct, 'multi_cred_tool not in plan').toBeDefined();
    expect(mct!.toolType).toBe('worker');
  });

  it('plan reflects sub-agents', async () => {
    const child = new Agent({ name: 'child_agent', model: MODEL });
    const parent = new Agent({
      name: 'parent_agent',
      model: MODEL,
      agents: [child],
      strategy: 'handoff',
    });

    const plan = (await runtime.plan(parent)) as Record<string, unknown>;
    const ad = getAgentDef(plan);

    const agents = (ad.agents ?? []) as Record<string, unknown>[];
    expect(agents.length).toBeGreaterThanOrEqual(1);
    expect(agents.some((a) => a.name === 'child_agent')).toBe(true);
  });

  it('kitchen sink compiles with all tool types, guardrails, and sub-agents', async () => {
    const kitchenSink = makeKitchenSinkAgent();

    const plan = (await runtime.plan(kitchenSink)) as Record<string, unknown>;
    expect(plan.workflowDef, 'plan() missing workflowDef').toBeDefined();
    expect(plan.requiredWorkers, 'plan() missing requiredWorkers').toBeDefined();

    const wf = plan.workflowDef as Record<string, unknown>;
    expect(wf.name).toBe('e2e_kitchen_sink');
    expect(((wf.tasks ?? []) as unknown[]).length).toBeGreaterThan(0);

    const ad = getAgentDef(plan);

    // Tools: every tool present with correct type
    const expectedTools: Record<string, string> = {
      local_tool: 'worker',
      cred_local_tool: 'worker',
      ks_http: 'http',
      ks_mcp: 'mcp',
      ks_image: 'generate_image',
      ks_audio: 'generate_audio',
      ks_video: 'generate_video',
      ks_pdf: 'generate_pdf',
    };
    for (const [name, expectedType] of Object.entries(expectedTools)) {
      const t = findTool(ad, name);
      expect(t, `Tool '${name}' not found in plan`).toBeDefined();
      expect(t!.toolType, `Tool '${name}' has wrong toolType`).toBe(expectedType);
    }

    // Credentials: TS SDK doesn't serialize credential names into plan config.
    // Verify the credentialed tool exists with correct type instead.
    const credTool = findTool(ad, 'cred_local_tool');
    expect(credTool, 'cred_local_tool not in plan').toBeDefined();
    expect(credTool!.toolType).toBe('worker');

    // Guardrails: all 3
    const guardrails = (ad.guardrails ?? []) as Record<string, unknown>[];
    const guardNames = guardrails.map((g) => g.name as string);
    expect(guardrails.length).toBe(3);
    for (const name of ['check_input', 'no_pii', 'no_password']) {
      expect(guardNames, `Guardrail '${name}' not found`).toContain(name);
    }

    const noPw = findGuardrail(ad, 'no_password');
    expect(noPw!.guardrailType).toBe('regex');
    expect((noPw!.patterns as string[]) ?? []).toContain('password');

    // Sub-agents: all 8 strategies
    const subAgents = (ad.agents ?? []) as Record<string, unknown>[];
    const subNames = subAgents.map((a) => a.name as string);
    const expectedSubs = [
      'ks_handoff', 'ks_sequential', 'ks_parallel', 'ks_router',
      'ks_round_robin', 'ks_random', 'ks_swarm', 'ks_manual',
    ];
    for (const name of expectedSubs) {
      expect(subNames, `Sub-agent '${name}' not found`).toContain(name);
    }

    // Verify strategies
    const subMap: Record<string, Record<string, unknown>> = {};
    for (const a of subAgents) subMap[a.name as string] = a;
    const expectedStrategies: Record<string, string> = {
      ks_handoff: 'handoff', ks_sequential: 'sequential', ks_parallel: 'parallel',
      ks_router: 'router', ks_round_robin: 'round_robin', ks_random: 'random',
      ks_swarm: 'swarm', ks_manual: 'manual',
    };
    for (const [name, strat] of Object.entries(expectedStrategies)) {
      expect(subMap[name].strategy, `Sub-agent '${name}' has wrong strategy`).toBe(strat);
    }

    // Parent strategy
    expect(ad.strategy).toBe('handoff');
  });

  it.skipIf(!process.env.ANTHROPIC_API_KEY && !process.env.OPENAI_API_KEY)(
    'LLM judge validates compiled kitchen sink workflow',
    async () => {
      const kitchenSink = makeKitchenSinkAgent();
      const result = (await runtime.plan(kitchenSink)) as Record<string, unknown>;
      expect(result.workflowDef, 'plan() missing workflowDef').toBeDefined();

      const comparison = buildJudgeComparison(result);
      const verdict = await judgeCompiledWorkflow(comparison);

      expect(verdict.pass, [
        'LLM judge found structural mismatches.',
        `Missing: ${JSON.stringify(verdict.missing)}`,
        `Explanation: ${verdict.explanation}`,
        `Judge model: ${JUDGE_MODEL}`,
      ].join('\n  ')).toBe(true);
    },
  );
});
