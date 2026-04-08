/**
 * Suite 1: Basic Validation — plan-based structural assertions.
 *
 * Compiles agents via plan() and asserts on the Conductor workflow JSON.
 * No LLM execution — only compilation checks.
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
    expect(tools.length).toBeGreaterThanOrEqual(2);

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

    expect(guardrails.length).toBeGreaterThanOrEqual(2);

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

  it('plan reflects sub-agents', async () => {
    const child = new Agent({ name: 'child_agent', model: MODEL });
    const parent = new Agent({
      name: 'parent_agent',
      model: MODEL,
      agents: [child],
      strategy: 'handoff',
    });

    const plan = await runtime.plan(parent);
    const ad = getAgentDef(plan);

    const agents = (ad.agents ?? []) as Record<string, unknown>[];
    expect(agents.length).toBeGreaterThanOrEqual(1);
    expect(agents.some((a) => a.name === 'child_agent')).toBe(true);
  });
});
