/**
 * Code Execution -- sandboxed environments for running LLM-generated code.
 *
 * Demonstrates code executor types:
 *
 * 1. LocalCodeExecutor -- runs code in a local subprocess (no sandbox)
 * 2. DockerCodeExecutor -- runs code inside a Docker container (sandboxed)
 * 3. JupyterCodeExecutor -- runs code in a persistent Jupyter kernel
 *
 * Each executor is attached to an agent as a tool via `executor.asTool()`.
 *
 * Requirements:
 *   - Conductor server with LLM support
 *   - Docker (for DockerCodeExecutor example)
 *   - AGENTSPAN_SERVER_URL=http://localhost:8080/api as environment variable
 *   - AGENTSPAN_LLM_MODEL=openai/gpt-4o-mini as environment variable
 */

import {
  Agent,
  AgentRuntime,
  LocalCodeExecutor,
  DockerCodeExecutor,
} from '../src/index.js';
import { llmModel } from './settings.js';

// -- Example 1: Local code execution ---------------------------------------

const localExecutor = new LocalCodeExecutor({ timeout: 10 });

export const coder = new Agent({
  name: 'local_coder',
  model: llmModel,
  tools: [localExecutor.asTool()],
  instructions:
    'You are a Python developer. Write and execute code to solve problems. ' +
    'Always use the code_executor tool to run your code and show results.',
});

// -- Example 2: Docker-sandboxed execution ---------------------------------

const dockerExecutor = new DockerCodeExecutor({
  image: 'python:3.12-slim',
  timeout: 15,
  memoryLimit: '256m',
});

export const sandboxedCoder = new Agent({
  name: 'sandboxed_coder',
  model: llmModel,
  tools: [dockerExecutor.asTool('run_sandboxed')],
  instructions:
    'You write Python code that runs in a sandboxed Docker container. ' +
    'Use the run_sandboxed tool to execute code safely.',
});

// -- Run -------------------------------------------------------------------

// Only run when executed directly (not when imported for discovery)
if (process.argv[1]?.endsWith('24-code-execution.ts') || process.argv[1]?.endsWith('24-code-execution.js')) {
  const runtime = new AgentRuntime();
  try {
    console.log('--- Local Code Execution ---');
    const result = await runtime.run(
      coder,
      'Write a Python function to find the first 10 Fibonacci numbers and print them.',
    );
    result.printResult();
  } finally {
    await runtime.shutdown();
  }
}
