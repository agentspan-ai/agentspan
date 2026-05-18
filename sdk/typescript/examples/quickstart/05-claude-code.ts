/**
 * Claude Code agent — uses Claude's built-in tools (Read, Glob, Grep).
 */

import { Agent, AgentRuntime } from '@agentspan-ai/sdk';

export const agent = new Agent({
  name: 'code_explorer',
  model: 'claude-code/sonnet',
  instructions: 'You explore codebases and answer questions about them.',
  tools: ['Read', 'Glob', 'Grep'],
  maxTurns: 5,
});

async function main() {
  const runtime = new AgentRuntime();
  try {
    const result = await runtime.run(agent, 'What TypeScript files are in the current directory?');
    result.printResult();

    // Production pattern:
    // 1. Deploy once during CI/CD:
    // await runtime.deploy(agent);
    // CLI alternative:
    // agentspan deploy --package sdk/typescript/examples/quickstart --agents code_explorer
    //
    // 2. In a separate long-lived worker process:
    // await runtime.serve(agent);
  } finally {
    await runtime.shutdown();
  }
}

export const prompt = 'What TypeScript files are in the current directory?';

main().catch(console.error);
