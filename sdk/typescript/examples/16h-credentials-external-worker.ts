/**
 * Credentials -- External worker credential resolution.
 *
 * Demonstrates:
 *   - tool() with external: true, credentials: ["GITHUB_TOKEN"] declares
 *     credentials for an external worker
 *   - The external worker uses resolveCredentials() to fetch
 *     credential values from the server at runtime
 *   - Works for workers running in separate processes, containers,
 *     or machines
 *
 * This example shows two sides:
 *   1. Agent definition (declares the external tool with credentials)
 *   2. External worker pattern (resolves credentials using the helper)
 *
 * The external worker typically runs in a separate process. Here we
 * demonstrate both patterns in one file.
 *
 * Setup (one-time):
 *   agentspan credentials set GITHUB_TOKEN <your-github-token>
 *
 * Requirements:
 *   - Agentspan server running at AGENTSPAN_SERVER_URL
 *   - AGENTSPAN_LLM_MODEL set (or defaults to openai/gpt-4o-mini)
 *   - GITHUB_TOKEN stored via `agentspan credentials set`
 */

import {
  Agent,
  tool,
  resolveCredentials,
  extractExecutionToken,
} from '@agentspan-ai/sdk';
import { llmModel } from './settings';

// -- Agent side: declare external tool with credentials -----------------------

const githubLookup = tool(
  async (_args: { username: string }) => {
    // Stub -- actual implementation is in the external worker below
    return { stub: true };
  },
  {
    name: 'github_lookup',
    description: "Look up a GitHub user's profile. Runs on an external worker.",
    inputSchema: {
      type: 'object',
      properties: {
        username: { type: 'string', description: 'GitHub username to look up' },
      },
      required: ['username'],
    },
    external: true,
    credentials: ['GITHUB_TOKEN'],
  },
);

export const agent = new Agent({
  name: 'external_cred_agent',
  model: llmModel,
  tools: [githubLookup],
  instructions: 'You can look up GitHub users. Use the github_lookup tool.',
});

// -- External worker side: resolve credentials at runtime ---------------------
// In production, this would run in a separate process.

async function externalWorkerExample(taskInput: Record<string, unknown>) {
  // extractExecutionToken reads __agentspan_ctx__ from task input
  const executionToken = extractExecutionToken(taskInput);
  if (!executionToken) {
    console.log('  No execution token found in task input');
    return;
  }

  const serverUrl = process.env.AGENTSPAN_SERVER_URL ?? 'http://localhost:6767/api';

  // resolveCredentials calls the server to get credential values
  const creds = await resolveCredentials(serverUrl, {}, executionToken, ['GITHUB_TOKEN']);
  const token = creds.GITHUB_TOKEN ?? '';

  console.log(`  Resolved GITHUB_TOKEN: ${token ? 'present' : 'missing'}`);

  // Use the credential to make API calls
  const username = (taskInput.username as string) ?? 'octocat';
  const headers: Record<string, string> = {};
  if (token) {
    headers.Authorization = `Bearer ${token}`;
  }

  const resp = await fetch(`https://api.github.com/users/${username}`, {
    headers,
    signal: AbortSignal.timeout(10_000),
  });

  if (resp.ok) {
    const user = (await resp.json()) as Record<string, unknown>;
    return {
      name: user.name,
      login: user.login,
      public_repos: user.public_repos,
      followers: user.followers,
    };
  } else {
    return { error: `GitHub API error: ${resp.status}` };
  }
}

// Suppress unused variable warning
void externalWorkerExample;

console.log('Note: This example demonstrates the pattern for external workers.');
console.log('The external worker (externalWorkerExample) would run in a separate process.');
console.log();
console.log('To run end-to-end:');
console.log('  1. Start the external worker in one terminal');
console.log('  2. Run the agent in another terminal');
console.log();
console.log('Agent definition:');
console.log(`  name: ${agent.name}`);
console.log(`  tools: [${agent.tools.map((t) => (t as { name?: string }).name ?? 'unknown').join(', ')}]`);
console.log();
console.log('External worker pattern:');
console.log("  const token = extractExecutionToken(taskInput);");
console.log("  const creds = await resolveCredentials(serverUrl, {}, token, ['GITHUB_TOKEN']);");
console.log("  const value = creds.GITHUB_TOKEN;");
