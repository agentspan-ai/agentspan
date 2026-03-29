/**
 * Credentials -- per-user secrets injected into isolated tool subprocesses.
 *
 * Demonstrates:
 *   - tool() with credentials: ["GITHUB_TOKEN"] (default isolated=true)
 *   - Credentials injected into a fresh subprocess -- parent env never touched
 *   - Tool reads credential from process.env inside the subprocess
 *   - Fallback to process.env when no server credential is set (non-strict mode)
 *
 * How it works:
 *   1. Agent starts -> server mints a short-lived execution token
 *   2. Before each tool call, the SDK fetches declared credentials from
 *      POST /api/credentials/resolve using that token
 *   3. The tool function runs in a fresh subprocess with credentials
 *      injected as env vars. The parent process's process.env is unchanged.
 *
 * Setup (one-time, via CLI):
 *   agentspan login                                     # authenticate
 *   agentspan credentials set --name GITHUB_TOKEN       # enter token when prompted
 *
 * Requirements:
 *   - Agentspan server running at AGENTSPAN_SERVER_URL
 *   - AGENTSPAN_LLM_MODEL set (or defaults to openai/gpt-4o-mini)
 *   - GITHUB_TOKEN stored via `agentspan credentials set` OR set in process.env
 */

import { Agent, AgentRuntime, tool } from '../src/index.js';
import { llmModel } from './settings.js';

// -- Isolated tool: list GitHub repos -----------------------------------------

const listGithubRepos = tool(
  async (args: { username: string }) => {
    const token = process.env.GITHUB_TOKEN ?? '';
    const headers: Record<string, string> = {
      Accept: 'application/vnd.github+json',
    };
    if (token) {
      headers.Authorization = `Bearer ${token}`;
    }

    try {
      const resp = await fetch(
        `https://api.github.com/users/${args.username}/repos?per_page=5&sort=updated`,
        { headers, signal: AbortSignal.timeout(10_000) },
      );
      if (!resp.ok) {
        return { error: `GitHub API error: ${resp.status} ${resp.statusText}` };
      }
      const repos = (await resp.json()) as Array<{ name: string; stargazers_count: number }>;
      return {
        username: args.username,
        repos: repos.map((r) => ({ name: r.name, stars: r.stargazers_count })),
        authenticated: Boolean(token),
      };
    } catch (err) {
      return { error: String(err) };
    }
  },
  {
    name: 'list_github_repos',
    description: 'List public repositories for a GitHub user. GITHUB_TOKEN env var is injected automatically.',
    inputSchema: {
      type: 'object',
      properties: {
        username: { type: 'string', description: 'GitHub username' },
      },
      required: ['username'],
    },
    credentials: ['GITHUB_TOKEN'],
  },
);

// -- Isolated tool: create GitHub issue ---------------------------------------

const createGithubIssue = tool(
  async (args: { repo: string; title: string; body: string }) => {
    const token = process.env.GITHUB_TOKEN;
    if (!token) {
      return { error: 'GITHUB_TOKEN not available -- cannot create issues without auth' };
    }

    try {
      const resp = await fetch(
        `https://api.github.com/repos/${args.repo}/issues`,
        {
          method: 'POST',
          headers: {
            Accept: 'application/vnd.github+json',
            Authorization: `Bearer ${token}`,
            'Content-Type': 'application/json',
          },
          body: JSON.stringify({ title: args.title, body: args.body }),
          signal: AbortSignal.timeout(10_000),
        },
      );
      if (!resp.ok) {
        return { error: `GitHub API error: ${resp.status} ${resp.statusText}` };
      }
      const issue = (await resp.json()) as { number?: number; html_url?: string };
      return { issue_number: issue.number, url: issue.html_url };
    } catch (err) {
      return { error: String(err) };
    }
  },
  {
    name: 'create_github_issue',
    description:
      'Create a GitHub issue. Requires GITHUB_TOKEN with write access. repo format: "owner/repo-name"',
    inputSchema: {
      type: 'object',
      properties: {
        repo: { type: 'string', description: 'Repository in "owner/repo" format' },
        title: { type: 'string', description: 'Issue title' },
        body: { type: 'string', description: 'Issue body' },
      },
      required: ['repo', 'title', 'body'],
    },
    credentials: ['GITHUB_TOKEN'],
  },
);

// -- Agent definition ---------------------------------------------------------

export const agent = new Agent({
  name: 'github_agent',
  model: llmModel,
  tools: [listGithubRepos, createGithubIssue],
  // Declare credentials at the agent level -- SDK auto-fetches for all tools
  credentials: ['GITHUB_TOKEN'],
  instructions:
    'You are a GitHub assistant. You can list repos and create issues. ' +
    'Always confirm with the user before creating issues.',
});

// -- Run ----------------------------------------------------------------------

// Only run when executed directly (not when imported for discovery)
async function main() {
  const runtime = new AgentRuntime();
  try {
    // Deploy to server. CLI alternative (recommended for CI/CD):
    //   agentspan deploy <module>
    await runtime.deploy(agent);
    await runtime.serve(agent);

    // Quick test: uncomment below (and comment out serve) to run directly.
    // const runtime = new AgentRuntime();
    // try {
    // const result = await runtime.run(
    // agent,
    // "List the 5 most recently updated repos for the 'agentspan' GitHub user.",
    // );
    // result.printResult();
  } finally {
    await runtime.shutdown();
    // }
}

if (process.argv[1]?.endsWith('16-credentials-isolated-tool.ts') || process.argv[1]?.endsWith('16-credentials-isolated-tool.js')) {
  main().catch(console.error);
}
