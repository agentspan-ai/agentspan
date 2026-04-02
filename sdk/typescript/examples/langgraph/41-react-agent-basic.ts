/**
 * Basic ReAct Agent -- createReactAgent runs on Conductor without create_agent.
 *
 * Demonstrates:
 *   - Using createReactAgent from @langchain/langgraph/prebuilt directly with AgentRuntime
 *   - No Agentspan wrapper needed -- pass the graph straight to runtime.run()
 *   - Agentspan detects the ReAct structure and runs LLM + tools on Conductor
 */

import { createReactAgent } from '@langchain/langgraph/prebuilt';
import { ChatOpenAI } from '@langchain/openai';
import { DynamicStructuredTool } from '@langchain/core/tools';
import { z } from 'zod';
import { AgentRuntime } from '../../src/index.js';

// ---------------------------------------------------------------------------
// Tool definitions
// ---------------------------------------------------------------------------
const calculateTool = new DynamicStructuredTool({
  name: 'calculate',
  description:
    'Evaluate a mathematical expression and return the result. ' +
    "Supports +, -, *, /, **, sqrt, and pi. Example: '2 ** 10', 'sqrt(144)', '(3 + 5) * 2'",
  schema: z.object({
    expression: z.string().describe('The mathematical expression to evaluate'),
  }),
  func: async ({ expression }) => {
    try {
      const sanitized = expression.replace(/[^0-9+\-*/().sqrtpi ]/g, '');
      const result = Function(
        '"use strict"; const sqrt = Math.sqrt; const pi = Math.PI; return (' +
          sanitized +
          ')',
      )();
      return String(result);
    } catch (e) {
      return `Error evaluating expression: ${e}`;
    }
  },
});

const countWordsTool = new DynamicStructuredTool({
  name: 'count_words',
  description: 'Count the number of words in the provided text.',
  schema: z.object({
    text: z.string().describe('The text to count words in'),
  }),
  func: async ({ text }) => {
    const words = text.trim().split(/\s+/);
    return `The text contains ${words.length} word(s).`;
  },
});

const reverseStringTool = new DynamicStructuredTool({
  name: 'reverse_string',
  description: 'Reverse a string and return it.',
  schema: z.object({
    text: z.string().describe('The text to reverse'),
  }),
  func: async ({ text }) => {
    return text.split('').reverse().join('');
  },
});

// ---------------------------------------------------------------------------
// Build the graph
// ---------------------------------------------------------------------------
const tools = [calculateTool, countWordsTool, reverseStringTool];
const llm = new ChatOpenAI({ model: 'gpt-4o-mini', temperature: 0 });
const graph = createReactAgent({ llm, tools });

(graph as any)._agentspan = {
  model: 'openai/gpt-4o-mini',
  tools,
  framework: 'langgraph',
};

const PROMPT =
  'What is sqrt(256) + 2**10? ' +
  "Also count the words in 'the quick brown fox jumps over the lazy dog'. " +
  "And what is 'Agentspan' reversed?";

// ---------------------------------------------------------------------------
// Run on agentspan
// ---------------------------------------------------------------------------
async function main() {
  const runtime = new AgentRuntime();
  try {
    const result = await runtime.run(graph, PROMPT);
    console.log('Status:', result.status);
    result.printResult();

    // Production pattern:
    // 1. Deploy once during CI/CD:
    // await runtime.deploy(graph);
    // CLI alternative:
    // agentspan deploy --package sdk/typescript/examples/langgraph --agents react_agent_basic
    //
    // 2. In a separate long-lived worker process:
    // await runtime.serve(graph);
  } finally {
    await runtime.shutdown();
  }
}

// Only run when executed directly (not when imported for discovery)
if (process.argv[1]?.endsWith('41-react-agent-basic.ts') || process.argv[1]?.endsWith('41-react-agent-basic.js')) {
  main().catch(console.error);
}
