/**
 * Credentials -- LangChain AgentExecutor with credential injection.
 *
 * Demonstrates:
 *   - Same pattern as LangGraph -- credentials resolved from server
 *     and injected into process.env before the executor runs
 *
 * NOTE: This example demonstrates the credential injection pattern for
 * LangChain agents running through Agentspan. Since LangChain is an
 * optional dependency, the example uses native Agentspan Agent with
 * credential-aware tools that mirror what a LangChain agent would do.
 *
 * In a full LangChain integration, you would:
 *   const executor = createLangChainAgent();
 *   const result = await runtime.run(executor, prompt, { credentials: ["GITHUB_TOKEN"] });
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

// Mirrors a LangChain @tool that checks for a credential in the environment
const checkGithubToken = tool(
  async () => {
    // Try in-process credential resolution first
    try {
      const token = await getCredential('GITHUB_TOKEN');
      return { message: `GitHub token available (starts with ${token.slice(0, 4)}...)` };
    } catch {
      // Fall back to process.env (as a LangChain tool would)
      const token = process.env.GITHUB_TOKEN ?? '';
      if (token) {
        return { message: `GitHub token available via env (starts with ${token.slice(0, 4)}...)` };
      }
      return { message: 'GitHub token is NOT available' };
    }
  },
  {
    name: 'check_github_token',
    description: 'Check if GitHub token is available in the environment.',
    inputSchema: { type: 'object', properties: {} },
    isolated: false,
    credentials: ['GITHUB_TOKEN'],
  },
);

export const agent = new Agent({
  name: 'langchain_cred_agent',
  model: llmModel,
  tools: [checkGithubToken],
  credentials: ['GITHUB_TOKEN'],
  instructions: 'You are a helpful assistant. Use tools when asked.',
});

// -- Run ----------------------------------------------------------------------

// Only run when executed directly (not when imported for discovery)
async function main() {
  const runtime = new AgentRuntime();
  try {
    // Deploy to server. CLI alternative (recommended for CI/CD):
    //   agentspan deploy <module>
    await runtime.deploy(executor);
    await runtime.serve(executor);

    // Quick test: uncomment below (and comment out serve) to run directly.
    // const runtime = new AgentRuntime();
    // try {
    // const result = await runtime.run(
    // agent,
    // 'Check if the GitHub token is set',
    // );
    // result.printResult();
  } finally {
    await runtime.shutdown();
    // }
}

if (process.argv[1]?.endsWith('16i-credentials-langchain.ts') || process.argv[1]?.endsWith('16i-credentials-langchain.js')) {
  main().catch(console.error);
}
