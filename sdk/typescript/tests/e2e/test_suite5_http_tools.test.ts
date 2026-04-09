/**
 * Suite 5: HTTP Tools — API discovery, execution, and authenticated access.
 *
 * Manages its own mcp-testkit instance (REST API mode) on a dedicated port.
 * No mocks. Real server, real CLI, real LLM.
 */

import { describe, it, expect, beforeAll, afterAll } from 'vitest';
import { Agent, AgentRuntime, httpTool, apiTool } from '@agentspan-ai/sdk';
import { execSync, spawn, type ChildProcess } from 'node:child_process';
import {
  checkServerHealth,
  MODEL,
  TIMEOUT,
  credentialSet,
  credentialDelete,
  findToolTasks,
  runDiagnostic,
} from './helpers';

const HTTP_PORT = 3003;
const HTTP_BASE_URL = `http://localhost:${HTTP_PORT}`;
const HTTP_SPEC_URL = `${HTTP_BASE_URL}/api-docs`;
const HTTP_AUTH_KEY = 'e2e-ts-http-secret';
const CRED_NAME = 'HTTP_AUTH_KEY_TS';

const TEST_TOOL_NAMES = ['math_add', 'string_reverse', 'encoding_base64_encode'];
const TEST_TOOL_EXPECTED: Record<string, string> = {
  math_add: '7',
  string_reverse: 'olleh',
  encoding_base64_encode: 'dGVzdA==',
};

const PROMPT = `Call exactly these three tools:
1. math_add with a=3 and b=4
2. string_reverse with text="hello"
3. encoding_base64_encode with text="test"
Report each result.`;

let runtime: AgentRuntime;

beforeAll(async () => {
  const healthy = await checkServerHealth();
  if (!healthy) throw new Error('Server not available');
  runtime = new AgentRuntime();
});

afterAll(async () => {
  credentialDelete(CRED_NAME);
  await runtime.shutdown();
});

// ── HTTP server management ──────────────────────────────────────────────

async function startHttpServer(port: number, authKey?: string): Promise<ChildProcess> {
  const args = ['--transport', 'http', '--port', String(port)];
  if (authKey) args.push('--auth', authKey);
  const proc = spawn('mcp-testkit', args, { stdio: 'pipe' });

  const deadline = Date.now() + 15_000;
  while (Date.now() < deadline) {
    try {
      const resp = await fetch(`http://localhost:${port}/api-docs`, {
        signal: AbortSignal.timeout(2_000),
      });
      if (resp.ok || resp.status === 401) return proc;
    } catch { /* not ready */ }
    await new Promise((r) => setTimeout(r, 500));
  }
  proc.kill();
  throw new Error(`mcp-testkit not ready on port ${port}`);
}

function stopHttpServer(proc: ChildProcess | null): void {
  if (proc && !proc.killed) {
    proc.kill('SIGTERM');
    try { execSync('sleep 1'); } catch { /* ignore */ }
  }
}

// ── OpenAPI discovery ───────────────────────────────────────────────────

async function discoverViaOpenApi(specUrl: string, authKey?: string): Promise<string[]> {
  const headers: Record<string, string> = {};
  if (authKey) headers.Authorization = `Bearer ${authKey}`;
  const resp = await fetch(specUrl, { headers, signal: AbortSignal.timeout(10_000) });
  if (!resp.ok) throw new Error(`OpenAPI fetch ${resp.status}`);
  const spec = (await resp.json()) as Record<string, unknown>;
  const paths = (spec.paths ?? {}) as Record<string, Record<string, Record<string, unknown>>>;
  const ops: string[] = [];
  for (const methods of Object.values(paths)) {
    for (const op of Object.values(methods)) {
      if (typeof op === 'object' && op && 'operationId' in op) ops.push(op.operationId as string);
    }
  }
  return ops.sort();
}

// ── Tool factories ──────────────────────────────────────────────────────

function makeHttpTools(baseUrl: string, headers?: Record<string, string>, credentials?: string[]) {
  return [
    httpTool({
      name: 'math_add',
      description: 'Add two numbers',
      url: `${baseUrl}/api/math/add`,
      method: 'GET',
      headers,
      credentials,
      inputSchema: {
        type: 'object',
        properties: {
          a: { type: 'number', description: 'First number' },
          b: { type: 'number', description: 'Second number' },
        },
        required: ['a', 'b'],
      },
    }),
    httpTool({
      name: 'string_reverse',
      description: 'Reverse a string',
      url: `${baseUrl}/api/string/reverse`,
      method: 'POST',
      headers,
      credentials,
      inputSchema: {
        type: 'object',
        properties: { text: { type: 'string' } },
        required: ['text'],
      },
    }),
    httpTool({
      name: 'encoding_base64_encode',
      description: 'Base64-encode a string',
      url: `${baseUrl}/api/encoding/base64-encode`,
      method: 'POST',
      headers,
      credentials,
      inputSchema: {
        type: 'object',
        properties: { text: { type: 'string' } },
        required: ['text'],
      },
    }),
  ];
}

// ── Tests ───────────────────────────────────────────────────────────────

describe('Suite 5: HTTP Tools', { timeout: 600_000 }, () => {
  let serverProc: ChildProcess | null = null;

  afterAll(() => stopHttpServer(serverProc));

  it('HTTP lifecycle — unauthenticated → authenticated', async () => {
    try {
      // ── Phase 1: Unauthenticated ────────────────────────────────
      serverProc = await startHttpServer(HTTP_PORT);

      // Discovery — dynamically determine exact count from spec
      const discovered = await discoverViaOpenApi(HTTP_SPEC_URL);
      const expectedCount = discovered.length;
      expect(expectedCount).toBeGreaterThanOrEqual(64);
      expect(discovered.length).toBe(expectedCount);

      // Execute
      const agent = new Agent({
        name: 'e2e_ts_http_unauth',
        model: MODEL,
        instructions: 'Call the tools as directed. Report results.',
        tools: makeHttpTools(HTTP_BASE_URL),
      });

      const result = await runtime.run(agent, PROMPT, { timeout: TIMEOUT });
      const diag = runDiagnostic(result as unknown as Record<string, unknown>);
      expect(result.status, `[Phase 1] ${diag}`).toBe('COMPLETED');

      const { results: tasks } = await findToolTasks(result.executionId, TEST_TOOL_NAMES);
      for (const name of TEST_TOOL_NAMES) {
        expect(tasks[name], `Tool '${name}' not found`).toBeDefined();
        expect(tasks[name].status).toBe('COMPLETED');
        expect(JSON.stringify(tasks[name].output)).toContain(TEST_TOOL_EXPECTED[name]);
      }

      // ── Phase 2: Authenticated ──────────────────────────────────
      stopHttpServer(serverProc);
      serverProc = null;
      execSync('sleep 1');
      serverProc = await startHttpServer(HTTP_PORT, HTTP_AUTH_KEY);

      // Auth enforcement
      const unauthResp = await fetch(HTTP_SPEC_URL, { signal: AbortSignal.timeout(5_000) });
      expect([401, 403]).toContain(unauthResp.status);

      credentialSet(CRED_NAME, HTTP_AUTH_KEY);

      const authAgent = new Agent({
        name: 'e2e_ts_http_auth',
        model: MODEL,
        instructions: 'Call the tools as directed. Report results.',
        tools: makeHttpTools(HTTP_BASE_URL, {
          Authorization: `Bearer \${${CRED_NAME}}`,
        }, [CRED_NAME]),
      });

      // Discovery with auth — must match unauthenticated count
      const discoveredAuth = await discoverViaOpenApi(HTTP_SPEC_URL, HTTP_AUTH_KEY);
      expect(discoveredAuth.length).toBe(expectedCount);

      // Execute with auth
      const resultAuth = await runtime.run(authAgent, PROMPT, { timeout: TIMEOUT });
      expect(resultAuth.status).toBe('COMPLETED');

      const { results: authTasks } = await findToolTasks(resultAuth.executionId, TEST_TOOL_NAMES);
      for (const name of TEST_TOOL_NAMES) {
        expect(authTasks[name], `Auth tool '${name}' not found`).toBeDefined();
        expect(authTasks[name].status).toBe('COMPLETED');
        expect(
          JSON.stringify(authTasks[name].output),
          `Auth tool '${name}' output missing expected value`,
        ).toContain(TEST_TOOL_EXPECTED[name]);
      }
    } finally {
      stopHttpServer(serverProc);
      serverProc = null;
    }
  });

  it('external OpenAPI spec — Orkes startWorkflow', async () => {
    const ORKES_URL = 'https://developer.orkescloud.com/api-docs';

    // Algorithmic: fetch spec and verify startWorkflow exists
    let spec: Record<string, unknown>;
    try {
      const resp = await fetch(ORKES_URL, { signal: AbortSignal.timeout(10_000) });
      spec = (await resp.json()) as Record<string, unknown>;
    } catch {
      console.log('Orkes API spec unreachable — skipping');
      return;
    }

    const paths = (spec.paths ?? {}) as Record<string, Record<string, Record<string, unknown>>>;
    let found = false;
    for (const [path, methods] of Object.entries(paths)) {
      for (const op of Object.values(methods)) {
        if (typeof op === 'object' && op && (op as Record<string, unknown>).operationId === 'startWorkflow') {
          expect(path).toContain('/workflow');
          found = true;
        }
      }
    }
    expect(found, 'startWorkflow not found in Orkes spec').toBe(true);

    // Compile agent with API tool
    const agent = new Agent({
      name: 'e2e_ts_orkes',
      model: MODEL,
      instructions: 'Answer questions about Orkes Conductor API.',
      tools: [apiTool({ url: ORKES_URL, name: 'orkes_api', toolNames: ['startWorkflow'] })],
    });

    const plan = (await runtime.plan(agent)) as Record<string, unknown>;
    const wf = plan.workflowDef as Record<string, unknown>;
    const meta = wf.metadata as Record<string, unknown>;
    const ad = meta.agentDef as Record<string, unknown>;
    const tools = (ad.tools ?? []) as Record<string, unknown>[];
    const apiTools = tools.filter((t) => t.toolType === 'api');
    expect(apiTools.length).toBeGreaterThanOrEqual(1);
  });
});
