/**
 * Credentials -- Google ADK agent with credential injection.
 *
 * Demonstrates:
 *   - Same pattern as other frameworks -- credentials resolved from server
 *     and injected into process.env before agent execution
 *
 * NOTE: This example demonstrates the credential injection pattern for
 * Google ADK agents running through Agentspan. Since Google ADK is an
 * optional dependency, the example uses native Agentspan Agent with
 * credential-aware tools that mirror what an ADK agent tool would do.
 *
 * In a full Google ADK integration, you would:
 *   const adkAgent = createADKAgent();
 *   const result = await runtime.run(adkAgent, prompt, { credentials: ["GITHUB_TOKEN"] });
 *
 * Setup (one-time):
 *   agentspan credentials set --name GITHUB_TOKEN
 *
 * Requirements:
 *   - Agentspan server running at AGENTSPAN_SERVER_URL
 *   - AGENTSPAN_LLM_MODEL set (or defaults to openai/gpt-4o-mini)
 *   - GITHUB_TOKEN stored via `agentspan credentials set`
 */

import { Agent, AgentRuntime, tool, getCredential } from '../src/index.js';
import { llmModel } from './settings.js';

// Mirrors a Google ADK FunctionTool that checks for a credential
const checkGithubAuth = tool(
  async () => {
    try {
      const token = await getCredential('GITHUB_TOKEN');
      return { message: `GitHub token is set (starts with ${token.slice(0, 4)}...)` };
    } catch {
      const envToken = process.env.GITHUB_TOKEN ?? '';
      if (envToken) {
        return { message: `GitHub token is set via env (starts with ${envToken.slice(0, 4)}...)` };
      }
      return { message: 'GitHub token is NOT set' };
    }
  },
  {
    name: 'check_github_auth',
    description: 'Check if GitHub authentication is available.',
    inputSchema: { type: 'object', properties: {} },
    isolated: false,
    credentials: ['GITHUB_TOKEN'],
  },
);

export const agent = new Agent({
  name: 'google_adk_cred_agent',
  model: llmModel,
  tools: [checkGithubAuth],
  credentials: ['GITHUB_TOKEN'],
  instructions: 'You check GitHub authentication status.',
});

// -- Run ----------------------------------------------------------------------

// Only run when executed directly (not when imported for discovery)
async function main() {
  const runtime = new AgentRuntime();
  try {
    // Deploy to server. CLI alternative (recommended for CI/CD):
    //   agentspan deploy <module>
    await runtime.deploy(adkAgent);
    await runtime.serve(adkAgent);

    // Quick test: uncomment below (and comment out serve) to run directly.
    // const runtime = new AgentRuntime();
    // try {
    // const result = await runtime.run(
    // agent,
    // 'Is GitHub authentication available?',
    // );
    // result.printResult();
  } finally {
    await runtime.shutdown();
    // }
}

if (process.argv[1]?.endsWith('16k-credentials-google-adk.ts') || process.argv[1]?.endsWith('16k-credentials-google-adk.js')) {
  main().catch(console.error);
}
