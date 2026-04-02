/**
 * 39a - Docker-sandboxed Code Execution
 *
 * The agent writes code and the DockerCodeExecutor runs it inside an
 * isolated Docker container. No network access, limited memory, and the
 * host filesystem is untouched.
 *
 * Requirements:
 *   - Conductor server with LLM support
 *   - Docker installed and daemon running
 *   - AGENTSPAN_SERVER_URL=http://localhost:6767/api as environment variable
 *   - AGENTSPAN_LLM_MODEL=openai/gpt-4o-mini as environment variable
 */

import { Agent, AgentRuntime, DockerCodeExecutor } from '../src/index.js';
import { llmModel } from './settings.js';

const dockerExecutor = new DockerCodeExecutor({
  image: 'python:3.12-slim',
  timeout: 30,
  memoryLimit: '256m',
});

export const dockerCoder = new Agent({
  name: 'docker_coder',
  model: llmModel,
  tools: [dockerExecutor.asTool('execute_code')],
  codeExecutionConfig: {
    enabled: true,
  },
  instructions:
    'You write Python code that runs in a sandboxed Docker container. ' +
    'You have no network access. Write self-contained code.',
});

// Only run when executed directly (not when imported for discovery)
async function main() {
  const runtime = new AgentRuntime();
  try {
    console.log('--- Docker Sandboxed Code Execution ---');
    const result = await runtime.run(
    dockerCoder,
    "Print Python's version and the container's hostname.",
    );
    result.printResult();

    // Production pattern:
    // 1. Deploy once during CI/CD:
    // await runtime.deploy(dockerCoder);
    // CLI alternative:
    // agentspan deploy --package sdk/typescript/examples --agents docker_coder
    //
    // 2. In a separate long-lived worker process:
    // await runtime.serve(dockerCoder);
  } finally {
    await runtime.shutdown();
  }
}

if (process.argv[1]?.endsWith('39a-docker-code-execution.ts') || process.argv[1]?.endsWith('39a-docker-code-execution.js')) {
  main().catch(console.error);
}
