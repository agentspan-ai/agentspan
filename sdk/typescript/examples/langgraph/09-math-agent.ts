/**
 * Math Agent -- createReactAgent with comprehensive arithmetic and math tools.
 *
 * Demonstrates:
 *   - Defining multiple related tools in a single agent
 *   - Using createReactAgent for a specialized domain (mathematics)
 *   - Chaining multiple tool calls to solve multi-step problems
 */

import { createReactAgent } from '@langchain/langgraph/prebuilt';
import { ChatOpenAI } from '@langchain/openai';
import { HumanMessage } from '@langchain/core/messages';
import { DynamicStructuredTool } from '@langchain/core/tools';
import { z } from 'zod';
import { AgentRuntime } from '../../src/index.js';

// ---------------------------------------------------------------------------
// Math tool definitions
// ---------------------------------------------------------------------------
const addTool = new DynamicStructuredTool({
  name: 'add',
  description: 'Add two numbers together.',
  schema: z.object({
    a: z.number().describe('First number'),
    b: z.number().describe('Second number'),
  }),
  func: async ({ a, b }) => String(a + b),
});

const subtractTool = new DynamicStructuredTool({
  name: 'subtract',
  description: 'Subtract b from a.',
  schema: z.object({
    a: z.number().describe('First number'),
    b: z.number().describe('Second number'),
  }),
  func: async ({ a, b }) => String(a - b),
});

const multiplyTool = new DynamicStructuredTool({
  name: 'multiply',
  description: 'Multiply two numbers.',
  schema: z.object({
    a: z.number().describe('First number'),
    b: z.number().describe('Second number'),
  }),
  func: async ({ a, b }) => String(a * b),
});

const divideTool = new DynamicStructuredTool({
  name: 'divide',
  description: 'Divide a by b.',
  schema: z.object({
    a: z.number().describe('Dividend'),
    b: z.number().describe('Divisor'),
  }),
  func: async ({ a, b }) => {
    if (b === 0) return 'Error: Division by zero is undefined.';
    return String(a / b);
  },
});

const powerTool = new DynamicStructuredTool({
  name: 'power',
  description: 'Raise base to the given exponent.',
  schema: z.object({
    base: z.number().describe('The base number'),
    exponent: z.number().describe('The exponent'),
  }),
  func: async ({ base, exponent }) => String(Math.pow(base, exponent)),
});

const sqrtTool = new DynamicStructuredTool({
  name: 'sqrt',
  description: 'Compute the square root of a number.',
  schema: z.object({
    n: z.number().describe('The number to take the square root of'),
  }),
  func: async ({ n }) => {
    if (n < 0) return `Error: Cannot compute the square root of a negative number (${n}).`;
    return String(Math.sqrt(n));
  },
});

const factorialTool = new DynamicStructuredTool({
  name: 'factorial',
  description: 'Compute the factorial of n (n!).',
  schema: z.object({
    n: z.number().describe('A non-negative integer (max 20)'),
  }),
  func: async ({ n }) => {
    if (n < 0) return 'Error: Factorial is not defined for negative numbers.';
    if (n > 20) return 'Error: Input too large (max 20 to avoid overflow).';
    let result = 1;
    for (let i = 2; i <= n; i++) result *= i;
    return String(result);
  },
});

// ---------------------------------------------------------------------------
// Build the graph
// ---------------------------------------------------------------------------
const llm = new ChatOpenAI({ model: 'gpt-4o-mini', temperature: 0 });
const graph = createReactAgent({
  llm,
  tools: [addTool, subtractTool, multiplyTool, divideTool, powerTool, sqrtTool, factorialTool],
});

const PROMPT =
  'Calculate: (2^10 + sqrt(144)) / 4, then compute 5! and tell me the final answers.';

// ---------------------------------------------------------------------------
// Run
// ---------------------------------------------------------------------------
async function main() {
  // ── Path 1: Native ──
  console.log('=== Native LangGraph execution ===');
  const nativeResult = await graph.invoke({
    messages: [new HumanMessage(PROMPT)],
  });
  for (const msg of nativeResult.messages) {
    const role = msg.constructor.name;
    if (msg.tool_calls && msg.tool_calls.length > 0) {
      console.log(`  ${role}: [tool_calls]`, msg.tool_calls.map((tc: any) => `${tc.name}(${JSON.stringify(tc.args)})`));
    } else if (msg.name) {
      console.log(`  ${role} (${msg.name}): ${msg.content}`);
    } else {
      const content = typeof msg.content === 'string' ? msg.content.slice(0, 300) : JSON.stringify(msg.content);
      console.log(`  ${role}: ${content}`);
    }
  }

  // ── Path 2: Agentspan ──
  console.log('\n=== Agentspan passthrough execution ===');
  const runtime = new AgentRuntime();
  try {
    const result = await runtime.run(graph, PROMPT);
    console.log('Status:', result.status);
    result.printResult();
  } finally {
    await runtime.shutdown();
  }
}

main().catch(console.error);
