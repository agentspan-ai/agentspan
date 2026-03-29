/**
 * Credentials -- OpenAI Agent SDK with credential injection.
 *
 * Demonstrates:
 *   - Credentials resolved from server and injected into process.env
 *   - Agent tools can read credentials from process.env
 *
 * NOTE: This example demonstrates the credential injection pattern for
 * OpenAI Agent SDK agents running through Agentspan. Since the OpenAI
 * Agent SDK is an optional dependency, the example uses native Agentspan
 * Agent with credential-aware tools that mirror what an OpenAI agent tool
 * would do.
 *
 * In a full OpenAI Agent SDK integration, you would:
 *   const openaiAgent = createOpenAIAgent();
 *   const result = await runtime.run(openaiAgent, prompt, { credentials: ["GITHUB_TOKEN"] });
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

// Mirrors an OpenAI @function_tool that checks for a credential
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
  name: 'openai_sdk_cred_agent',
  model: llmModel,
  tools: [checkGithubAuth],
  credentials: ['GITHUB_TOKEN'],
  instructions: 'You check GitHub authentication status. Use the tool when asked.',
});

// -- Run ----------------------------------------------------------------------

// Only run when executed directly (not when imported for discovery)
async function main() {
  const runtime = new AgentRuntime();
  try {
    // Deploy to server. CLI alternative (recommended for CI/CD):
    //   agentspan deploy <module>
    await runtime.deploy(openaiAgent);
    await runtime.serve(openaiAgent);

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

if (process.argv[1]?.endsWith('16j-credentials-openai-sdk.ts') || process.argv[1]?.endsWith('16j-credentials-openai-sdk.js')) {
  main().catch(console.error);
}
