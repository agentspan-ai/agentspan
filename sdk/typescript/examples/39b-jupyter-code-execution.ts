/**
 * 39b - Jupyter Kernel Code Execution
 *
 * The JupyterCodeExecutor runs code in a real Jupyter kernel. Variables,
 * imports, and definitions persist between executions -- just like cells in
 * a notebook. Perfect for data-science workflows where analysis is built up
 * step by step.
 *
 * Requirements:
 *   - Conductor server with LLM support
 *   - Jupyter runtime installed (jupyter_client, ipykernel)
 *   - AGENTSPAN_SERVER_URL=http://localhost:6767/api as environment variable
 *   - AGENTSPAN_LLM_MODEL=openai/gpt-4o-mini as environment variable
 */

import { Agent, AgentRuntime, JupyterCodeExecutor } from '../src/index.js';
import { llmModel } from './settings.js';

const jupyterExecutor = new JupyterCodeExecutor({
  kernelName: 'python3',
  timeout: 30,
});

export const jupyterCoder = new Agent({
  name: 'jupyter_coder',
  model: llmModel,
  tools: [jupyterExecutor.asTool('execute_code')],
  codeExecutionConfig: {
    enabled: true,
  },
  instructions:
    'You are a data scientist. Variables persist between code executions, ' +
    "just like a Jupyter notebook. Build up your analysis step by step -- " +
    'import libraries once, then reuse them in subsequent calls. ' +
    "The 'math' module is already imported for you.",
});

// Only run when executed directly (not when imported for discovery)
async function main() {
  const runtime = new AgentRuntime();
  try {
    console.log('--- Jupyter Kernel Code Execution ---');
    const result = await runtime.run(
    jupyterCoder,
    "Compute the first 10 Fibonacci numbers using a loop, store them in a " +
    "list called 'fibs', and print them. Then in a second execution, print " +
    "the sum of 'fibs' (it should still exist from the first call).",
    );
    result.printResult();

    // Production pattern:
    // 1. Deploy once during CI/CD:
    // await runtime.deploy(jupyterCoder);
    // CLI alternative:
    // agentspan deploy --package sdk/typescript/examples --agents jupyter_coder
    //
    // 2. In a separate long-lived worker process:
    // await runtime.serve(jupyterCoder);
  } finally {
    await runtime.shutdown();
  }
}

if (process.argv[1]?.endsWith('39b-jupyter-code-execution.ts') || process.argv[1]?.endsWith('39b-jupyter-code-execution.js')) {
  main().catch(console.error);
}
