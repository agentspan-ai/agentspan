/**
 * Google ADK AgentTool -- agent-as-tool invocation.
 *
 * Demonstrates:
 *   - Using AgentTool to wrap an agent as a callable tool
 *   - The parent agent's LLM invokes the child agent like a function
 *   - The child agent runs its own tools and returns the result
 *   - Unlike subAgents (handoff), AgentTool runs inline and returns
 *
 * Architecture:
 *   manager (parent agent)
 *     tools:
 *       - AgentTool(researcher)   <- child agent with its own tools
 *       - AgentTool(calculator)   <- another child agent
 *
 * Requirements:
 *   - npm install @google/adk zod
 *   - AGENTSPAN_SERVER_URL for agentspan path
 */

import { LlmAgent, FunctionTool, AgentTool } from '@google/adk';
import { z } from 'zod';
import { AgentRuntime } from '../../src/index.js';

const model = process.env.AGENTSPAN_LLM_MODEL ?? 'gemini-2.5-flash';

// ── Child agents (each has their own tools) ──────────────────────

const searchKnowledgeBase = new FunctionTool({
  name: 'search_knowledge_base',
  description: 'Search an internal knowledge base for information.',
  parameters: z.object({
    query: z.string().describe('The search query'),
  }),
  execute: async (args: { query: string }) => {
    const data: Record<string, {
      summary: string;
      popularity: string;
      key_use_cases: string[];
    }> = {
      python: {
        summary: 'Python is a high-level programming language created by Guido van Rossum in 1991.',
        popularity: 'Most popular language on TIOBE index (2024)',
        key_use_cases: ['web development', 'data science', 'AI/ML', 'automation'],
      },
      rust: {
        summary: 'Rust is a systems programming language focused on safety and performance.',
        popularity: 'Most admired language on Stack Overflow survey (2024)',
        key_use_cases: ['systems programming', 'WebAssembly', 'CLI tools', 'embedded'],
      },
    };
    for (const [key, val] of Object.entries(data)) {
      if (args.query.toLowerCase().includes(key)) {
        return { query: args.query, found: true, ...val };
      }
    }
    return { query: args.query, found: false, summary: 'No results found.' };
  },
});

export const researcher = new LlmAgent({
  name: 'researcher',
  model,
  instruction:
    'You are a research assistant. Use the knowledge base tool to find ' +
    'information and provide concise, factual answers.',
  tools: [searchKnowledgeBase],
});

const compute = new FunctionTool({
  name: 'compute',
  description: 'Evaluate a mathematical expression.',
  parameters: z.object({
    expression: z.string().describe("A math expression like '2 + 3 * 4'"),
  }),
  execute: async (args: { expression: string }) => {
    // Safe subset of math operations
    const safeMath: Record<string, unknown> = {
      abs: Math.abs,
      round: Math.round,
      min: Math.min,
      max: Math.max,
      sqrt: Math.sqrt,
      pow: Math.pow,
      PI: Math.PI,
      E: Math.E,
    };
    try {
      // Simple expression evaluation (for demo purposes)
      const expr = args.expression
        .replace(/pi/gi, String(Math.PI))
        .replace(/e(?![a-z])/gi, String(Math.E));
      // Use Function constructor for basic math evaluation
      const result = new Function(`"use strict"; return (${expr})`)();
      return { expression: args.expression, result };
    } catch (e: unknown) {
      return { expression: args.expression, error: String(e) };
    }
  },
});

export const calculator = new LlmAgent({
  name: 'calculator',
  model,
  instruction: 'You are a math assistant. Use the compute tool for calculations.',
  tools: [compute],
});

// ── Parent agent with AgentTool wrappers ─────────────────────────

export const manager = new LlmAgent({
  name: 'manager',
  model,
  instruction:
    'You are a manager agent. You have two specialist agents available as tools:\n' +
    '- researcher: for looking up information\n' +
    '- calculator: for math computations\n\n' +
    'Use the appropriate agent tool to answer the user\'s question. ' +
    'You can call multiple agent tools if needed.',
  tools: [
    new AgentTool({ agent: researcher }),
    new AgentTool({ agent: calculator }),
  ],
});

// ── Run on agentspan ───────────────────────────────────────────────

async function main() {
  const runtime = new AgentRuntime();
  try {
    // Deploy to server. CLI alternative (recommended for CI/CD):
    //   agentspan deploy <module>
    await runtime.deploy(manager);
    await runtime.serve(manager);

    // Quick test: uncomment below (and comment out serve) to run directly.
    // const result = await runtime.run(
    // manager,
    // 'Look up information about Python and Rust, then calculate ' +
    // "what percentage of Python's 4 key use cases overlap with Rust's 4 use cases.",
    // );
    // console.log('Status:', result.status);
    // result.printResult();
  } finally {
    await runtime.shutdown();
  }
}

// Only run when executed directly (not when imported for discovery)
if (process.argv[1]?.endsWith('21-agent-tool.ts') || process.argv[1]?.endsWith('21-agent-tool.js')) {
  main().catch(console.error);
}
