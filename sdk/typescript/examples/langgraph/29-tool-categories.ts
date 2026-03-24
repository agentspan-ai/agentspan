/**
 * Tool Categories -- organizing tools into categories with metadata.
 *
 * Demonstrates:
 *   - Defining tools with rich metadata
 *   - Grouping tools by category (math, string, date)
 *   - Passing all categorized tools to the agent
 *   - The LLM correctly selects the right tool for each query
 *
 * In production you would use:
 *   import { tool } from '@langchain/core/tools';
 *   import { createReactAgent } from '@langchain/langgraph/prebuilt';
 */

import { AgentRuntime } from '../../src/index.js';

// ---------------------------------------------------------------------------
// Tool implementations
// ---------------------------------------------------------------------------

// -- Math tools --
function squareRoot(n: number): string {
  if (n < 0) return 'Error: Cannot compute square root of a negative number.';
  return `sqrt(${n}) = ${Math.sqrt(n).toFixed(6)}`;
}

function power(base: number, exponent: number): string {
  return `${base}^${exponent} = ${Math.pow(base, exponent)}`;
}

function factorial(n: number): string {
  if (n < 0 || n > 20) return 'Error: n must be between 0 and 20.';
  let result = 1;
  for (let i = 2; i <= n; i++) result *= i;
  return `${n}! = ${result}`;
}

// -- String tools --
function countWords(text: string): string {
  return `Word count: ${text.split(/\s+/).filter(Boolean).length}`;
}

function reverseString(text: string): string {
  return `Reversed: ${text.split('').reverse().join('')}`;
}

function titleCase(text: string): string {
  return `Title case: ${text.replace(/\w\S*/g, (t) => t.charAt(0).toUpperCase() + t.slice(1).toLowerCase())}`;
}

// -- Date tools --
function currentDate(): string {
  return `Today's date: ${new Date().toISOString().split('T')[0]}`;
}

function daysUntil(targetDate: string): string {
  const target = new Date(targetDate);
  if (isNaN(target.getTime())) return 'Invalid date format. Use YYYY-MM-DD.';
  const diff = Math.ceil((target.getTime() - Date.now()) / (1000 * 60 * 60 * 24));
  if (diff > 0) return `${diff} days until ${targetDate}`;
  if (diff === 0) return `${targetDate} is today!`;
  return `${targetDate} was ${Math.abs(diff)} days ago`;
}

function dayOfWeek(dateStr: string): string {
  const d = new Date(dateStr);
  if (isNaN(d.getTime())) return 'Invalid date format. Use YYYY-MM-DD.';
  const days = ['Sunday', 'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday'];
  return `${dateStr} is a ${days[d.getUTCDay()]}`;
}

// ---------------------------------------------------------------------------
// Tool dispatcher (mock agent)
// ---------------------------------------------------------------------------
function dispatch(query: string): string {
  const q = query.toLowerCase();
  if (q.includes('square root') || q.includes('sqrt')) {
    const num = parseFloat(query.match(/\d+/)?.[0] ?? '0');
    return squareRoot(num);
  }
  if (q.includes('how many words')) {
    const match = query.match(/'([^']+)'/);
    return countWords(match?.[1] ?? query);
  }
  if (q.includes('day of the week')) {
    const match = query.match(/\d{4}-\d{2}-\d{2}/);
    return dayOfWeek(match?.[0] ?? '');
  }
  return 'I could not determine which tool to use for this query.';
}

// ---------------------------------------------------------------------------
// Mock compiled graph
// ---------------------------------------------------------------------------
const graph = {
  name: 'tool_categories_agent',

  invoke: async (input: Record<string, unknown>) => {
    const query = (input.input as string) ?? '';
    const result = dispatch(query);
    return {
      messages: [
        { role: 'user', content: query },
        { role: 'assistant', content: result },
      ],
    };
  },

  getGraph: () => ({
    nodes: new Map([
      ['__start__', {}],
      ['agent', {}],
      ['tools', {}],
      ['__end__', {}],
    ]),
    edges: [
      ['__start__', 'agent'],
      ['agent', 'tools'],
      ['tools', 'agent'],
      ['agent', '__end__'],
    ],
  }),

  nodes: new Map([
    ['agent', {}],
    ['tools', {}],
  ]),

  stream: async function* (input: Record<string, unknown>) {
    const query = (input.input as string) ?? '';
    const result = dispatch(query);
    yield ['updates', { agent: { messages: [{ role: 'assistant', content: result }] } }];
    yield ['values', { messages: [{ role: 'assistant', content: result }] }];
  },
};

// ---------------------------------------------------------------------------
// Run
// ---------------------------------------------------------------------------
async function main() {
  const queries = [
    'What is the square root of 144?',
    "How many words are in the phrase 'The quick brown fox'?",
    'What day of the week was 2000-01-01?',
  ];

  const runtime = new AgentRuntime();
  try {
    for (const query of queries) {
      console.log(`\nQuery: ${query}`);
      const result = await runtime.run(graph, query);
      result.printResult();
    }
  } finally {
    await runtime.shutdown();
  }
}

main().catch(console.error);
