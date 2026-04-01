/**
 * Credentials -- GitHub CLI (gh) with automatic credential injection.
 *
 * Demonstrates:
 *   - cliConfig with allowedCommands: ["gh"] gives the agent a run_command tool
 *   - credentials: ["GH_TOKEN"] auto-injects the token into the tool env
 *   - The agent calls `gh` commands directly -- no subprocess boilerplate needed
 *
 * Setup (one-time, via CLI):
 *   agentspan login
 *   agentspan credentials set --name GH_TOKEN
 *
 * Requirements:
 *   - Agentspan server running at AGENTSPAN_SERVER_URL
 *   - AGENTSPAN_LLM_MODEL set (or defaults to openai/gpt-4o-mini)
 *   - `gh` CLI installed (https://cli.github.com)
 *   - GH_TOKEN stored via `agentspan credentials set`
 */

import { Agent, AgentRuntime } from '../src';
import { llmModel } from './settings.js';

export const agent = new Agent({
  name: 'github_cli_agent',
  model: llmModel,
  cliConfig: { enabled: true, allowedCommands: ['gh'] },
  credentials: ['GH_TOKEN'],
  instructions:
    'You are a GitHub assistant that uses the `gh` CLI tool. ' +
    'GH_TOKEN is already set in the environment -- gh will use it automatically. ' +
    'Use --json for structured output when listing repos, issues, or PRs. ' +
    'Always confirm with the user before creating issues or PRs.',
});

// -- Run ----------------------------------------------------------------------

// Only run when executed directly (not when imported for discovery)
async function main() {
  const runtime = new AgentRuntime();
  try {
    // Deploy to server. CLI alternative (recommended for CI/CD):
    //   agentspan deploy <module>
    // await runtime.deploy(agent);
    // await runtime.serve(agent);
    // Direct run for local development:
    // const runtime = new AgentRuntime();
    // try {
    const result = await runtime.run(
    agent,
    "List the 5 most recently updated repos for the 'agentspan'",
    );
    result.printResult();
  } finally {
    await runtime.shutdown();
  }
}

if (process.argv[1]?.endsWith('16d-credentials-gh-cli.ts') || process.argv[1]?.endsWith('16d-credentials-gh-cli.js')) {
  main().catch(console.error);
}
