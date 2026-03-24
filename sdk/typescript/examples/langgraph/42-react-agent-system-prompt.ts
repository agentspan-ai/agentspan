/**
 * ReAct Agent with System Prompt -- create_react_agent with prompt parameter.
 *
 * Demonstrates:
 *   - Passing a system prompt via the prompt parameter
 *   - Agentspan extracts the system prompt and forwards it to the server
 *   - Custom persona carried through the full Conductor execution
 *
 * In production you would use:
 *   import { createReactAgent } from '@langchain/langgraph/prebuilt';
 *   const graph = createReactAgent({ llm, tools, prompt: SYSTEM_PROMPT });
 */

import { AgentRuntime } from '../../src/index.js';

// ---------------------------------------------------------------------------
// Tool implementations
// ---------------------------------------------------------------------------
const EXCHANGE_RATES: Record<string, number> = {
  'USD-EUR': 0.92,
  'USD-GBP': 0.79,
  'USD-JPY': 149.5,
  'EUR-USD': 1.09,
  'GBP-USD': 1.27,
  'JPY-USD': 0.0067,
};

function getExchangeRate(from: string, to: string): string {
  const key = `${from.toUpperCase()}-${to.toUpperCase()}`;
  const rate = EXCHANGE_RATES[key];
  if (rate) return `1 ${from.toUpperCase()} = ${rate} ${to.toUpperCase()}`;
  return `Exchange rate for ${from}/${to} not available.`;
}

const UNIT_CONVERSIONS: Record<string, (x: number) => number> = {
  'km-miles': (x) => x * 0.621371,
  'miles-km': (x) => x * 1.60934,
  'kg-lbs': (x) => x * 2.20462,
  'lbs-kg': (x) => x * 0.453592,
  'celsius-fahrenheit': (x) => x * 9 / 5 + 32,
  'fahrenheit-celsius': (x) => (x - 32) * 5 / 9,
};

function convertUnits(value: number, from: string, to: string): string {
  const key = `${from.toLowerCase()}-${to.toLowerCase()}`;
  const fn = UNIT_CONVERSIONS[key];
  if (fn) return `${value} ${from} = ${fn(value).toFixed(2)} ${to}`;
  return `Conversion from ${from} to ${to} not supported.`;
}

// ---------------------------------------------------------------------------
// Mock agent dispatch (acts as travel assistant with system prompt persona)
// ---------------------------------------------------------------------------
function dispatch(query: string): string {
  const parts: string[] = [];

  // Exchange rate queries
  if (query.toLowerCase().includes('yen') || query.toLowerCase().includes('jpy')) {
    const usdAmount = query.match(/\$(\d+)/)?.[1] ?? '800';
    const rate = EXCHANGE_RATES['USD-JPY'] ?? 149.5;
    const yen = Number(usdAmount) * rate;
    parts.push(`${getExchangeRate('USD', 'JPY')}\n$${usdAmount} USD = ${yen.toFixed(0)} JPY`);
  }

  // Unit conversion queries
  if (query.toLowerCase().includes('km') || query.toLowerCase().includes('miles')) {
    const kmMatch = query.match(/([\d,]+)\s*km/);
    if (kmMatch) {
      const km = Number(kmMatch[1].replace(/,/g, ''));
      parts.push(convertUnits(km, 'km', 'miles'));
    }
  }

  return parts.join('\n\n') || 'As your travel assistant, I can help with currency exchange and unit conversions.';
}

// ---------------------------------------------------------------------------
// Mock compiled graph
// ---------------------------------------------------------------------------
const graph = {
  name: 'travel_assistant_agent',

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
      "I'm flying from the US to Japan with $800. " +
      'How many yen will I get? The flight is 9,540 km -- how far is that in miles?',
    );
    console.log('Status:', result.status);
    result.printResult();
  } finally {
    await runtime.shutdown();
  }
}

main().catch(console.error);
