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
 *   agentspan credentials set GH_TOKEN <your-gh-token>
 *
 * Requirements:
 *   - Agentspan server running at AGENTSPAN_SERVER_URL
 *   - AGENTSPAN_LLM_MODEL set (or defaults to openai/gpt-4o-mini)
 *   - `gh` CLI installed (https://cli.github.com)
 *   - GH_TOKEN stored via `agentspan credentials set`
 */

import { Agent, AgentRuntime } from '@agentspan-ai/sdk';
import { llmModel } from './settings';

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

async function main() {
  const runtime = new AgentRuntime();
  try {
    const result = await runtime.run(
    agent,
    "List the 5 most recently updated repos for the 'agentspan' and list the URL for the repo",
    );
    result.printResult();

    // Production pattern:
    // 1. Deploy once during CI/CD:
    // await runtime.deploy(agent);
    // CLI alternative:
    // agentspan deploy --package sdk/typescript/examples --agents github_cli_agent
    //
    // 2. In a separate long-lived worker process:
    // await runtime.serve(agent);
  } finally {
    await runtime.shutdown();
  }
}

main().catch(console.error);
