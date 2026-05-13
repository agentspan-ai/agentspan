/**
 * Credentials -- Framework passthrough with credential injection.
 *
 * Demonstrates:
 *   - Credentials resolved from the server and injected into process.env
 *     before the graph executes
 *   - Works the same for LangChain, OpenAI Agent SDK, and Google ADK
 *
 * This pattern is used when you run a foreign framework agent (LangGraph,
 * LangChain, OpenAI, ADK) through Agentspan and need tools inside the
 * graph to access credentials from the credential store.
 *
 * NOTE: Since the TypeScript SDK's RunOptions does not yet support a
 * top-level `credentials` parameter, this example demonstrates the pattern
 * using a native Agent with credential-aware tools. The concept is the same:
 * credentials are resolved and injected before tool execution.
 *
 * Setup (one-time):
 *   agentspan credentials set GITHUB_TOKEN <your-github-token>
 *
 * Requirements:
 *   - Agentspan server running at AGENTSPAN_SERVER_URL
 *   - AGENTSPAN_LLM_MODEL set (or defaults to openai/gpt-4o-mini)
 *   - GITHUB_TOKEN stored via `agentspan credentials set`
 */

import { Agent, AgentRuntime, tool, getCredential } from '@agentspan-ai/sdk';
import { llmModel } from './settings';

// A tool that reads GITHUB_TOKEN from the credential store (in-process mode).
// In a framework passthrough scenario, this credential would be injected into
// process.env before the framework's agent executes.
const checkGithubAuth = tool(
  async () => {
    // Try getCredential() first (in-process mode)
    try {
      const token = await getCredential('GITHUB_TOKEN');
      return { message: `GitHub token is set (starts with ${token.slice(0, 4)}...)` };
    } catch {
      // Fall back to process.env
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
  name: 'framework_passthrough_agent',
  model: llmModel,
  tools: [checkGithubAuth],
  credentials: ['GITHUB_TOKEN'],
  instructions: 'Check if GitHub authentication is available using the tool.',
});

// -- Run ----------------------------------------------------------------------

async function main() {
  const runtime = new AgentRuntime();
  try {
    const result = await runtime.run(
    agent,
    'Check if GitHub authentication is available',
    );
    result.printResult();

    // Production pattern:
    // 1. Deploy once during CI/CD:
    // await runtime.deploy(agent);
    // CLI alternative:
    // agentspan deploy --package sdk/typescript/examples --agents framework_passthrough_agent
    //
    // 2. In a separate long-lived worker process:
    // await runtime.serve(agent);
  } finally {
    await runtime.shutdown();
  }
}

main().catch(console.error);
