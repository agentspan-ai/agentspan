/**
 * 39c - Serverless Code Execution
 *
 * The ServerlessCodeExecutor sends code to an HTTP endpoint and returns
 * the result. Use this to offload execution to a hosted sandbox, AWS Lambda,
 * Google Cloud Functions, or any service that accepts a JSON payload.
 *
 * This example starts a tiny local HTTP server to simulate the remote service,
 * then runs an agent that executes code through it.
 *
 * Requirements:
 *   - Conductor server with LLM support
 *   - AGENTSPAN_SERVER_URL=http://localhost:6767/api as environment variable
 *   - AGENTSPAN_LLM_MODEL=openai/gpt-4o-mini as environment variable
 */

import { createServer } from 'http';
import { execSync } from 'child_process';
import { Agent, AgentRuntime, ServerlessCodeExecutor } from '../src/index.js';
import { llmModel } from './settings.js';

// -- Tiny mock execution server -----------------------------------------------

const PORT = 9753;

const server = createServer((req, res) => {
  if (req.method !== 'POST') {
    res.writeHead(405);
    res.end();
    return;
  }

  let body = '';
  req.on('data', (chunk: Buffer) => { body += chunk.toString(); });
  req.on('end', () => {
    const parsed = JSON.parse(body) as { code?: string; timeout?: number };
    const code = parsed.code ?? '';
    const timeout = (parsed.timeout ?? 10) * 1000;

    let result: { output: string; error: string; exit_code: number };
    try {
      const output = execSync(`python3 -c ${JSON.stringify(code)}`, {
        timeout,
        encoding: 'utf-8',
        stdio: ['pipe', 'pipe', 'pipe'],
      });
      result = { output, error: '', exit_code: 0 };
    } catch (err: unknown) {
      const e = err as { stdout?: string; stderr?: string; status?: number };
      result = {
        output: e.stdout ?? '',
        error: e.stderr ?? String(err),
        exit_code: e.status ?? 1,
      };
    }

    res.writeHead(200, { 'Content-Type': 'application/json' });
    res.end(JSON.stringify(result));
  });
});

server.listen(PORT, '127.0.0.1');

// -- Agent setup --------------------------------------------------------------

const serverlessExecutor = new ServerlessCodeExecutor({
  endpoint: `http://127.0.0.1:${PORT}/execute`,
  timeout: 15,
});

export const serverlessCoder = new Agent({
  name: 'serverless_coder',
  model: llmModel,
  tools: [serverlessExecutor.asTool('execute_code')],
  codeExecutionConfig: {
    enabled: true,
  },
  instructions:
    'You write Python code that runs on a remote execution service. ' +
    'Use the execute_code tool to run code remotely.',
});

// -- Run ----------------------------------------------------------------------

// Only run when executed directly (not when imported for discovery)
async function main() {
  const runtime = new AgentRuntime();
  try {
    console.log('--- Serverless Code Execution ---');
    const result = await runtime.run(
      serverlessCoder,
      'Calculate 2**100 and print the result.',
    );
    result.printResult();

    // Production pattern:
    // 1. Deploy once during CI/CD:
    // await runtime.deploy(serverlessCoder);
    // CLI alternative:
    // agentspan deploy --package sdk/typescript/examples
    //
    // 2. In a separate long-lived worker process:
    // await runtime.serve(serverlessCoder);
  } finally {
    server.close();
    await runtime.shutdown();
  }
}

if (process.argv[1]?.endsWith('39c-serverless-code-execution.ts') || process.argv[1]?.endsWith('39c-serverless-code-execution.js')) {
  main().catch(console.error);
}
