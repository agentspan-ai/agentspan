/**
 * Tool Categories -- organizing tools into categories with metadata.
 *
 * Demonstrates:
 *   - Defining tools with rich metadata (description, schema)
 *   - Grouping tools by category (math, string, date)
 *   - Passing all categorized tools to createReactAgent
 *   - The LLM correctly selects the right tool for each query
 */

import { createReactAgent } from '@langchain/langgraph/prebuilt';
import { ChatOpenAI } from '@langchain/openai';
import { DynamicStructuredTool } from '@langchain/core/tools';
import { z } from 'zod';
import { AgentRuntime } from '../../src/index.js';

// ---------------------------------------------------------------------------
// LLM
// ---------------------------------------------------------------------------
const llm = new ChatOpenAI({ model: 'gpt-4o-mini', temperature: 0 });

// ---------------------------------------------------------------------------
// Math tools
// ---------------------------------------------------------------------------
const squareRootTool = new DynamicStructuredTool({
  name: 'square_root',
  description: 'Calculate the square root of a non-negative number.',
  schema: z.object({
    number: z.number().describe('The number to compute the square root of'),
  }),
  func: async ({ number }) => {
    if (number < 0) return 'Error: Cannot compute square root of a negative number.';
    return `sqrt(${number}) = ${Math.sqrt(number).toFixed(6)}`;
  },
});

const powerTool = new DynamicStructuredTool({
  name: 'power',
  description: 'Raise a base number to an exponent (base ** exponent).',
  schema: z.object({
    base: z.number().describe('The base number'),
    exponent: z.number().describe('The exponent'),
  }),
  func: async ({ base, exponent }) => {
    return `${base}^${exponent} = ${Math.pow(base, exponent)}`;
  },
});

const factorialTool = new DynamicStructuredTool({
  name: 'factorial',
  description: 'Compute the factorial of a non-negative integer.',
  schema: z.object({
    n: z.number().int().describe('The non-negative integer (0-20)'),
  }),
  func: async ({ n }) => {
    if (n < 0 || n > 20) return 'Error: n must be between 0 and 20.';
    let result = 1;
    for (let i = 2; i <= n; i++) result *= i;
    return `${n}! = ${result}`;
  },
});

// ---------------------------------------------------------------------------
// String tools
// ---------------------------------------------------------------------------
const countWordsTool = new DynamicStructuredTool({
  name: 'count_words',
  description: 'Count the number of words in the given text.',
  schema: z.object({
    text: z.string().describe('The text to count words in'),
  }),
  func: async ({ text }) => {
    const words = text.trim().split(/\s+/);
    return `Word count: ${words.length}`;
  },
});

const reverseStringTool = new DynamicStructuredTool({
  name: 'reverse_string',
  description: 'Reverse the characters in a string.',
  schema: z.object({
    text: z.string().describe('The text to reverse'),
  }),
  func: async ({ text }) => {
    return `Reversed: ${text.split('').reverse().join('')}`;
  },
});

const titleCaseTool = new DynamicStructuredTool({
  name: 'title_case',
  description: 'Convert the text to title case.',
  schema: z.object({
    text: z.string().describe('The text to convert'),
  }),
  func: async ({ text }) => {
    const titled = text.replace(
      /\w\S*/g,
      (w) => w.charAt(0).toUpperCase() + w.slice(1).toLowerCase(),
    );
    return `Title case: ${titled}`;
  },
});

// ---------------------------------------------------------------------------
// Date tools
// ---------------------------------------------------------------------------
const currentDateTool = new DynamicStructuredTool({
  name: 'current_date',
  description: "Return today's date in YYYY-MM-DD format.",
  schema: z.object({}),
  func: async () => {
    return `Today's date: ${new Date().toISOString().slice(0, 10)}`;
  },
});

const daysUntilTool = new DynamicStructuredTool({
  name: 'days_until',
  description: 'Calculate how many days until a target date (YYYY-MM-DD).',
  schema: z.object({
    target_date: z.string().describe('The target date in YYYY-MM-DD format'),
  }),
  func: async ({ target_date }) => {
    const target = new Date(target_date);
    if (isNaN(target.getTime())) return 'Invalid date format. Use YYYY-MM-DD.';
    const today = new Date();
    today.setHours(0, 0, 0, 0);
    target.setHours(0, 0, 0, 0);
    const delta = Math.round((target.getTime() - today.getTime()) / (1000 * 60 * 60 * 24));
    if (delta > 0) return `${delta} days until ${target_date}`;
    if (delta === 0) return `${target_date} is today!`;
    return `${target_date} was ${Math.abs(delta)} days ago`;
  },
});

const dayOfWeekTool = new DynamicStructuredTool({
  name: 'day_of_week',
  description: 'Return the day of the week for a given date (YYYY-MM-DD).',
  schema: z.object({
    date_str: z.string().describe('The date in YYYY-MM-DD format'),
  }),
  func: async ({ date_str }) => {
    const d = new Date(date_str);
    if (isNaN(d.getTime())) return 'Invalid date format. Use YYYY-MM-DD.';
    const days = ['Sunday', 'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday'];
    return `${date_str} is a ${days[d.getDay()]}`;
  },
});

// ---------------------------------------------------------------------------
// Build the graph
// ---------------------------------------------------------------------------
const allTools = [
  // Math
  squareRootTool,
  powerTool,
  factorialTool,
  // String
  countWordsTool,
  reverseStringTool,
  titleCaseTool,
  // Date
  currentDateTool,
  daysUntilTool,
  dayOfWeekTool,
];

const graph = createReactAgent({ llm, tools: allTools });

// Add agentspan metadata for extraction
(graph as any)._agentspan = {
  model: 'openai/gpt-4o-mini',
  tools: allTools,
  framework: 'langgraph',
};

const PROMPT = 'What is the square root of 144?';

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
    // agentspan deploy --package sdk/typescript/examples/langgraph --agents tool_categories
    //
    // 2. In a separate long-lived worker process:
    // await runtime.serve(graph);
  } finally {
    await runtime.shutdown();
  }
}

// Only run when executed directly (not when imported for discovery)
if (process.argv[1]?.endsWith('29-tool-categories.ts') || process.argv[1]?.endsWith('29-tool-categories.js')) {
  main().catch(console.error);
}
