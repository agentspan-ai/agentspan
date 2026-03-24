/**
 * Vercel AI SDK Tools + Native Agent -- Credentials
 *
 * Demonstrates agentspan's credential system with AI SDK tools on a native Agent.
 * Credentials are declared on the Agent and resolved by the agentspan server
 * before tool execution -- the tool receives credentials via environment injection.
 */

import { tool as aiTool } from 'ai';
import { z } from 'zod';
import { Agent, AgentRuntime } from '../../src/index.js';

// ── Vercel AI SDK tool that uses a credential ────────────
const fetchReport = aiTool({
  description: 'Fetch a report from the analytics API.',
  parameters: z.object({
    reportId: z.string().describe('Report ID to fetch'),
  }),
  execute: async ({ reportId }) => {
    // In production, the agentspan server injects ANALYTICS_API_KEY
    // into the environment before this tool executes.
    const apiKey = process.env.ANALYTICS_API_KEY ?? 'demo-key';
    return {
      reportId,
      data: `Report ${reportId} fetched successfully (key: ${apiKey.slice(0, 4)}...)`,
      rows: 42,
    };
  },
});

// ── Native Agent with credentials ────────────────────────
const agent = new Agent({
  name: 'credentialed_agent',
  model: 'openai/gpt-4o-mini',
  instructions:
    'You are a helpful assistant with access to analytics reports. ' +
    'Use the fetchReport tool to retrieve data when asked.',
  tools: [fetchReport],
  credentials: [
    // Credential references resolved by the agentspan server.
    // In production, these are stored in the credential vault.
    'ANALYTICS_API_KEY',
  ],
});

const prompt = 'Fetch the analytics report with ID RPT-2024-Q4.';

// ── Run on agentspan ─────────────────────────────────────
async function main() {
  const runtime = new AgentRuntime();
  try {
    const result = await runtime.run(agent, prompt);
    console.log('Status:', result.status);
    result.printResult();
  } finally {
    await runtime.shutdown();
  }
}

main().catch(console.error);
