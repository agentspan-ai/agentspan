/**
 * ReAct Agent Multi-Model -- create_react_agent works with any supported model.
 *
 * Demonstrates:
 *   - create_react_agent with Claude (ChatAnthropic) instead of OpenAI
 *   - Model is auto-detected from the LLM instance and forwarded to Conductor
 *   - Same code, different model -- no Agentspan-specific changes needed
 *
 * In production you would use:
 *   import { ChatAnthropic } from '@langchain/anthropic';
 *   import { createReactAgent } from '@langchain/langgraph/prebuilt';
 *   const graph = createReactAgent({ llm: new ChatAnthropic(...), tools });
 */

import { AgentRuntime } from '../../src/index.js';

// ---------------------------------------------------------------------------
// Tool implementations
// ---------------------------------------------------------------------------
function getToday(): string {
  return new Date().toISOString().split('T')[0];
}

function daysBetween(date1: string, date2: string): string {
  try {
    const d1 = new Date(date1);
    const d2 = new Date(date2);
    const diff = Math.abs(Math.round((d2.getTime() - d1.getTime()) / (1000 * 60 * 60 * 24)));
    return `There are ${diff} days between ${date1} and ${date2}.`;
  } catch {
    return 'Invalid date format. Use YYYY-MM-DD.';
  }
}

function dayOfWeek(dateStr: string): string {
  try {
    const d = new Date(dateStr);
    const days = ['Sunday', 'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday'];
    return `${dateStr} falls on a ${days[d.getUTCDay()]}.`;
  } catch {
    return 'Invalid date format. Use YYYY-MM-DD.';
  }
}

// ---------------------------------------------------------------------------
// Mock agent dispatch
// ---------------------------------------------------------------------------
function dispatch(query: string): string {
  const parts: string[] = [];
  const today = getToday();

  if (query.toLowerCase().includes('today')) {
    parts.push(`Today is ${today}. ${dayOfWeek(today)}`);
  }

  if (query.toLowerCase().includes("new year") || query.toLowerCase().includes('2026-01-01')) {
    parts.push(daysBetween(today, '2026-01-01'));
    parts.push(dayOfWeek('2026-01-01'));
  }

  return parts.join('\n\n') || `Today is ${today}.`;
}

// ---------------------------------------------------------------------------
// Mock compiled graph (using Claude model)
// ---------------------------------------------------------------------------
const graph = {
  name: 'date_calculator_agent',

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
  const runtime = new AgentRuntime();
  try {
    const result = await runtime.run(
      graph,
      "What day of the week is today? " +
      "How many days until New Year's Day 2026? " +
      'What day of the week will that be?',
    );
    console.log('Status:', result.status);
    result.printResult();
  } finally {
    await runtime.shutdown();
  }
}

main().catch(console.error);
