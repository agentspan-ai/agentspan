/**
 * 31 - Tool Guardrails
 *
 * Demonstrates a guardrail attached to a specific tool that blocks dangerous
 * inputs (like SQL injection) before the tool function executes.
 *
 * Tool guardrails run inside the tool worker, before (position="input") or
 * after (position="output") the tool function itself.
 *
 * Requirements:
 *   - Conductor server with LLM support
 *   - AGENTSPAN_SERVER_URL=http://localhost:6767/api as environment variable
 *   - AGENTSPAN_LLM_MODEL=openai/gpt-4o-mini as environment variable
 */

import { z } from 'zod';
import { Agent, AgentRuntime, guardrail, tool } from '../src/index.js';
import type { GuardrailResult } from '../src/index.js';
import { llmModel } from './settings.js';

// -- Guardrail ---------------------------------------------------------------

const noSqlInjection = guardrail(
  (content: string): GuardrailResult => {
    const patterns = [/DROP\s+TABLE/i, /DELETE\s+FROM/i, /;\s*--/i, /UNION\s+SELECT/i];
    for (const pat of patterns) {
      if (pat.test(content)) {
        return {
          passed: false,
          message: `Blocked: potential SQL injection detected (${pat.source})`,
        };
      }
    }
    return { passed: true };
  },
  {
    name: 'sql_injection_guard',
    position: 'input',
    onFail: 'raise',
  },
);

// -- Tool with guardrail -----------------------------------------------------

const runQuery = tool(
  async (args: { query: string }) => {
    // In a real app this would hit a database
    return `Results for: ${args.query} -> [('Alice', 30), ('Bob', 25)]`;
  },
  {
    name: 'run_query',
    description: 'Execute a read-only database query and return results.',
    inputSchema: z.object({
      query: z.string().describe('The SQL query to execute'),
    }),
    guardrails: [noSqlInjection],
  },
);

// -- Agent -------------------------------------------------------------------

export const agent = new Agent({
  name: 'db_assistant',
  model: llmModel,
  tools: [runQuery],
  instructions:
    'You help users query the database. Use the run_query tool. ' +
    'Only execute SELECT queries.',
});

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
    // Safe query -- should work fine
    console.log('=== Safe Query ===');
    const result = await runtime.run(agent, 'Find all users older than 25.');
    result.printResult();

    // Dangerous query -- the tool guardrail should block it
    console.log('\n=== Dangerous Query (should be blocked) ===');
    const result2 = await runtime.run(
    agent,
    'Run this exact query: SELECT * FROM users; DROP TABLE users; --',
    );
    result2.printResult();
  } finally {
    await runtime.shutdown();
    // }
}

if (process.argv[1]?.endsWith('31-tool-guardrails.ts') || process.argv[1]?.endsWith('31-tool-guardrails.js')) {
  main().catch(console.error);
}
