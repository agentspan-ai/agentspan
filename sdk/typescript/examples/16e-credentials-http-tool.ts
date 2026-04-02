/**
 * Credentials -- HTTP tool with server-side credential resolution.
 *
 * Demonstrates:
 *   - httpTool() with credentials: ["GITHUB_TOKEN"]
 *   - ${GITHUB_TOKEN} in headers resolved server-side (not in TypeScript)
 *   - No worker process needed -- Conductor makes the HTTP call directly
 *
 * The ${NAME} syntax in headers tells the server to substitute the credential
 * value from the store at execution time. The plaintext value never appears
 * in the workflow definition.
 *
 * Setup (one-time):
 *   agentspan credentials set --name GITHUB_TOKEN
 *
 * Requirements:
 *   - Agentspan server running at AGENTSPAN_SERVER_URL
 *   - AGENTSPAN_LLM_MODEL set (or defaults to openai/gpt-4o-mini)
 *   - GITHUB_TOKEN stored via `agentspan credentials set`
 */

import { Agent, AgentRuntime, httpTool } from '../src/index.js';
import { llmModel } from './settings.js';

// HTTP tool with credential-bearing headers.
// ${GITHUB_TOKEN} is resolved server-side from the credential store.
const listRepos = httpTool({
  name: 'list_github_repos',
  description:
    'List public GitHub repositories for a user. Returns JSON array with name, url, and stars.',
  url: 'https://api.github.com/users/agentspan/repos?per_page=5&sort=updated',
  headers: {
    Authorization: 'Bearer ${GITHUB_TOKEN}',
    Accept: 'application/vnd.github.v3+json',
  },
  credentials: ['GITHUB_TOKEN'],
});

export const agent = new Agent({
  name: 'github_http_agent',
  model: llmModel,
  tools: [listRepos],
  instructions: 'You list GitHub repos using the list_github_repos tool. Summarize the results.',
});

// -- Run ----------------------------------------------------------------------

// Only run when executed directly (not when imported for discovery)
async function main() {
  const runtime = new AgentRuntime();
  try {
    const result = await runtime.run(agent, 'List the repos for agentspan');
    result.printResult();

    // Production pattern:
    // 1. Deploy once during CI/CD:
    // await runtime.deploy(agent);
    // CLI alternative:
    // agentspan deploy --package sdk/typescript/examples --agents github_http_agent
    //
    // 2. In a separate long-lived worker process:
    // await runtime.serve(agent);
  } finally {
    await runtime.shutdown();
  }
}

if (process.argv[1]?.endsWith('16e-credentials-http-tool.ts') || process.argv[1]?.endsWith('16e-credentials-http-tool.js')) {
  main().catch(console.error);
}
