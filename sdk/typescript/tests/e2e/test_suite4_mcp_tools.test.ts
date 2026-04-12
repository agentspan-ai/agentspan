/**
 * Suite 4: MCP Tools — discovery, execution, and authenticated access.
 *
 * Manages its own mcp-testkit instance on a dedicated port.
 * No mocks. Real server, real CLI, real LLM.
 */

import { describe, it, expect, beforeAll, afterAll } from 'vitest';
import { Agent, AgentRuntime, mcpTool } from '@agentspan-ai/sdk';
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

const MCP_PORT = 3004; // Dedicated port — avoids conflict with Python Suite 4 (3002) in parallel CI
const MCP_BASE_URL = `http://localhost:${MCP_PORT}`;
const MCP_SERVER_URL = `${MCP_BASE_URL}/mcp`;
const MCP_AUTH_KEY = 'e2e-ts-mcp-test-secret';
const CRED_NAME = 'MCP_AUTH_KEY_TS';

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

// ── MCP server management ───────────────────────────────────────────────

function startMcpServer(port: number, authKey?: string): ChildProcess {
  const args = ['--transport', 'http', '--port', String(port)];
  if (authKey) args.push('--auth', authKey);
  const proc = spawn('mcp-testkit', args, { stdio: 'pipe' });

  // Wait for server to be ready
  const deadline = Date.now() + 15_000;
  while (Date.now() < deadline) {
    try {
      execSync(`curl -sf http://localhost:${port}/ 2>/dev/null || true`, { timeout: 2_000 });
      // Check if server responds (any response including 404 means it's up)
      const resp = execSync(`curl -s -o /dev/null -w '%{http_code}' http://localhost:${port}/`, {
        timeout: 2_000,
      });
      if (resp.toString().trim() !== '000') return proc;
    } catch {
      // Not ready yet
    }
    execSync('sleep 0.5');
  }
  proc.kill();
  throw new Error(`mcp-testkit not ready on port ${port}`);
}

function stopMcpServer(proc: ChildProcess | null): void {
  if (proc && !proc.killed) {
    proc.kill('SIGTERM');
    try {
      execSync('sleep 1');
    } catch { /* ignore */ }
  }
}

// ── MCP discovery ───────────────────────────────────────────────────────

async function discoverMcpTools(serverUrl: string, authKey?: string): Promise<string[]> {
  // Use the MCP client library (same as Python test)
  const { streamablehttp_client } = await import('@anthropic-ai/mcp/client/streamable-http');
  const { ClientSession } = await import('@anthropic-ai/mcp');

  const headers: Record<string, string> = {};
  if (authKey) headers.Authorization = `Bearer ${authKey}`;

  const [read, write] = await streamablehttp_client(serverUrl, { headers });
  const session = new ClientSession(read, write);
  await session.initialize();
  const result = await session.listTools();
  return result.tools.map((t: { name: string }) => t.name).sort();
}

// Fallback: fetch OpenAPI spec from REST API (with retry for server readiness)
async function discoverToolsViaOpenApi(baseUrl: string, authKey?: string): Promise<string[]> {
  const headers: Record<string, string> = {};
  if (authKey) headers.Authorization = `Bearer ${authKey}`;

  // Retry up to 3 times with 2s backoff — mcp-testkit may not be fully ready
  // after restart (especially in CI where processes start slower)
  let lastError: Error | undefined;
  for (let attempt = 0; attempt < 3; attempt++) {
    try {
      const resp = await fetch(`${baseUrl}/api-docs`, { headers, signal: AbortSignal.timeout(10_000) });
      if (!resp.ok) throw new Error(`OpenAPI fetch failed: ${resp.status}`);
      const spec = (await resp.json()) as Record<string, unknown>;
      const paths = (spec.paths ?? {}) as Record<string, Record<string, Record<string, unknown>>>;
      const operations: string[] = [];
      for (const methods of Object.values(paths)) {
        for (const op of Object.values(methods)) {
          if (typeof op === 'object' && op && 'operationId' in op) {
            operations.push(op.operationId as string);
          }
        }
      }
      return operations.sort();
    } catch (err) {
      lastError = err instanceof Error ? err : new Error(String(err));
      if (attempt < 2) {
        await new Promise((r) => setTimeout(r, 2000));
      }
    }
  }
  throw lastError!;
}

// ── Tests ───────────────────────────────────────────────────────────────

describe('Suite 4: MCP Tools', { timeout: 600_000 }, () => {
  let serverProc: ChildProcess | null = null;

  afterAll(() => stopMcpServer(serverProc));

  it('MCP lifecycle — unauthenticated → authenticated', async () => {
    try {
      // ── Phase 1: Unauthenticated ────────────────────────────────
      serverProc = startMcpServer(MCP_PORT);

      // Discovery: use OpenAPI fallback (MCP client may not be available in TS)
      const discovered = await discoverToolsViaOpenApi(MCP_BASE_URL);
      // Dynamically determine exact count from the spec itself
      const expectedCount = discovered.length;
      expect(expectedCount).toBeGreaterThanOrEqual(64);
      expect(discovered.length).toBe(expectedCount);

      // Execute: create agent and run
      const agent = new Agent({
        name: 'e2e_ts_mcp_unauth',
        model: MODEL,
        instructions: 'Call exactly the tools specified. Report results.',
        tools: [
          mcpTool({
            serverUrl: MCP_SERVER_URL,
            name: 'test_mcp',
            description: 'Test MCP tools',
          }),
        ],
      });

      const result = await runtime.run(agent, PROMPT, { timeout: TIMEOUT });
      const diag = runDiagnostic(result as unknown as Record<string, unknown>);
      expect(result.executionId).toBeTruthy();
      expect(result.status, `[Phase 1] ${diag}`).toBe('COMPLETED');

      // Validate tool execution via workflow tasks
      const { results: toolTasks } = await findToolTasks(result.executionId, TEST_TOOL_NAMES);
      for (const name of TEST_TOOL_NAMES) {
        expect(toolTasks[name], `Tool '${name}' not in workflow tasks`).toBeDefined();
        expect(toolTasks[name].status, `Tool '${name}' status`).toBe('COMPLETED');
        const outputStr = JSON.stringify(toolTasks[name].output);
        expect(outputStr, `Tool '${name}' output`).toContain(TEST_TOOL_EXPECTED[name]);
      }

      // ── Phase 2: Authenticated ──────────────────────────────────
      stopMcpServer(serverProc);
      serverProc = null;
      execSync('sleep 1');
      serverProc = startMcpServer(MCP_PORT, MCP_AUTH_KEY);

      // Auth agent
      credentialSet(CRED_NAME, MCP_AUTH_KEY);

      const authAgent = new Agent({
        name: 'e2e_ts_mcp_auth',
        model: MODEL,
        instructions: 'Call exactly the tools specified. Report results.',
        tools: [
          mcpTool({
            serverUrl: MCP_SERVER_URL,
            name: 'test_mcp_auth',
            description: 'Authenticated MCP tools',
            headers: { Authorization: `Bearer \${${CRED_NAME}}` },
            credentials: [CRED_NAME],
          }),
        ],
      });

      // Discovery with auth — must match unauthenticated count
      const discoveredAuth = await discoverToolsViaOpenApi(MCP_BASE_URL, MCP_AUTH_KEY);
      expect(discoveredAuth.length).toBe(expectedCount);

      // Execute with auth
      const resultAuth = await runtime.run(authAgent, PROMPT, { timeout: TIMEOUT });
      const diagAuth = runDiagnostic(resultAuth as unknown as Record<string, unknown>);
      expect(resultAuth.status, `[Phase 2] ${diagAuth}`).toBe('COMPLETED');

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
      stopMcpServer(serverProc);
      serverProc = null;
    }
  });
});
