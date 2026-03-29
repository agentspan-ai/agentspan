/**
 * 45 - Agent Tool
 *
 * Unlike sub-agents (which use handoff delegation), an agentTool is invoked
 * inline by the parent LLM like a function call. The child agent runs its
 * own workflow and returns the result as a tool output.
 *
 *   manager (parent)
 *     tools:
 *       - agentTool(researcher)   <- child agent with search tool
 *       - calculate               <- regular tool
 *
 * Requirements:
 *   - Conductor server with AgentTool support
 *   - AGENTSPAN_SERVER_URL=http://localhost:8080/api as environment variable
 *   - AGENTSPAN_LLM_MODEL=openai/gpt-4o-mini as environment variable
 */

import { z } from 'zod';
import { Agent, AgentRuntime, agentTool, tool } from '../src/index.js';
import { llmModel } from './settings.js';

// -- Child agent's tool -------------------------------------------------------

const searchKnowledgeBase = tool(
  async (args: { query: string }) => {
    const data: Record<string, { summary: string; use_cases: string[] }> = {
      python: {
        summary: 'Python is a high-level programming language.',
        use_cases: ['web development', 'data science', 'automation'],
      },
      rust: {
        summary: 'Rust is a systems language focused on safety and performance.',
        use_cases: ['systems programming', 'WebAssembly', 'CLI tools'],
      },
    };
    for (const [key, val] of Object.entries(data)) {
      if (args.query.toLowerCase().includes(key)) {
        return { query: args.query, ...val };
      }
    }
    return { query: args.query, summary: 'No specific data found.' };
  },
  {
    name: 'search_knowledge_base',
    description: 'Search an internal knowledge base for information.',
    inputSchema: z.object({
      query: z.string().describe('The search query'),
    }),
  },
);

// -- Regular tool for parent --------------------------------------------------

const calculate = tool(
  async (args: { expression: string }) => {
    const allowed = new Set('0123456789+-*/.(). '.split(''));
    if (![...args.expression].every((c) => allowed.has(c))) {
      return { error: 'Invalid expression' };
    }
    try {
      // Simple expression evaluator (demo only -- not production-safe)
      const fn = new Function(`return (${args.expression});`);
      return { result: fn() };
    } catch (e) {
      return { error: String(e) };
    }
  },
  {
    name: 'calculate',
    description: 'Evaluate a math expression safely.',
    inputSchema: z.object({
      expression: z.string().describe('A mathematical expression to evaluate'),
    }),
  },
);

// -- Child agent (has its own tools) ------------------------------------------

export const researcher = new Agent({
  name: 'researcher_45',
  model: llmModel,
  instructions:
    'You are a research assistant. Use search_knowledge_base to find ' +
    'information about topics. Provide concise summaries.',
  tools: [searchKnowledgeBase],
});

// -- Parent agent (uses researcher as a tool) ---------------------------------

export const manager = new Agent({
  name: 'manager_45',
  model: llmModel,
  instructions:
    'You are a project manager. Use the researcher tool to gather ' +
    'information and the calculate tool for math. Synthesize findings.',
  tools: [agentTool(researcher), calculate],
});

// Only run when executed directly (not when imported for discovery)
async function main() {
  const runtime = new AgentRuntime();
  try {
    // Deploy to server. CLI alternative (recommended for CI/CD):
    //   agentspan deploy <module>
    await runtime.deploy(manager);
    await runtime.serve(manager);

    // Quick test: uncomment below (and comment out serve) to run directly.
    // const runtime = new AgentRuntime();
    // try {
    // const result = await runtime.run(
    // manager,
    // 'Research Python and Rust, then calculate how many use cases they ' +
    // 'have combined.',
    // );
    // result.printResult();
  } finally {
    await runtime.shutdown();
    // }
}

if (process.argv[1]?.endsWith('45-agent-tool.ts') || process.argv[1]?.endsWith('45-agent-tool.js')) {
  main().catch(console.error);
}
