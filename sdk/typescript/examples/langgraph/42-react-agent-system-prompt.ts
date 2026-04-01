/**
 * ReAct Agent with System Prompt -- createReactAgent with prompt parameter.
 *
 * Demonstrates:
 *   - Passing a system prompt via the prompt parameter
 *   - Agentspan extracts the system prompt and forwards it to the server
 *   - Custom persona carried through the full Conductor execution
 */

import { createReactAgent } from '@langchain/langgraph/prebuilt';
import { ChatOpenAI } from '@langchain/openai';
import { DynamicStructuredTool } from '@langchain/core/tools';
import { SystemMessage } from '@langchain/core/messages';
import { z } from 'zod';
import { AgentRuntime } from '../../src/index.js';

// ---------------------------------------------------------------------------
// Tool definitions
// ---------------------------------------------------------------------------
const getExchangeRateTool = new DynamicStructuredTool({
  name: 'get_exchange_rate',
  description: 'Get the exchange rate between two currencies (demo rates).',
  schema: z.object({
    from_currency: z.string().describe('Source currency code'),
    to_currency: z.string().describe('Target currency code'),
  }),
  func: async ({ from_currency, to_currency }) => {
    const rates: Record<string, number> = {
      'USD-EUR': 0.92,
      'USD-GBP': 0.79,
      'USD-JPY': 149.5,
      'EUR-USD': 1.09,
      'GBP-USD': 1.27,
      'JPY-USD': 0.0067,
    };
    const key = `${from_currency.toUpperCase()}-${to_currency.toUpperCase()}`;
    const rate = rates[key];
    if (rate !== undefined) {
      return `1 ${from_currency.toUpperCase()} = ${rate} ${to_currency.toUpperCase()}`;
    }
    return `Exchange rate for ${from_currency}/${to_currency} not available.`;
  },
});

const convertUnitsTool = new DynamicStructuredTool({
  name: 'convert_units',
  description: 'Convert between common units (length, weight, temperature).',
  schema: z.object({
    value: z.number().describe('The value to convert'),
    from_unit: z.string().describe('Source unit'),
    to_unit: z.string().describe('Target unit'),
  }),
  func: async ({ value, from_unit, to_unit }) => {
    const conversions: Record<string, (x: number) => number> = {
      'km-miles': (x) => x * 0.621371,
      'miles-km': (x) => x * 1.60934,
      'kg-lbs': (x) => x * 2.20462,
      'lbs-kg': (x) => x * 0.453592,
      'celsius-fahrenheit': (x) => (x * 9) / 5 + 32,
      'fahrenheit-celsius': (x) => ((x - 32) * 5) / 9,
    };
    const key = `${from_unit.toLowerCase()}-${to_unit.toLowerCase()}`;
    const fn = conversions[key];
    if (fn) {
      return `${value} ${from_unit} = ${fn(value).toFixed(2)} ${to_unit}`;
    }
    return `Conversion from ${from_unit} to ${to_unit} not supported.`;
  },
});

// ---------------------------------------------------------------------------
// Build the graph
// ---------------------------------------------------------------------------
const SYSTEM_PROMPT =
  'You are a friendly travel assistant specializing in currency exchange ' +
  'and unit conversions. Always show the exact numbers and be concise.';

const tools = [getExchangeRateTool, convertUnitsTool];
const llm = new ChatOpenAI({ model: 'gpt-4o-mini', temperature: 0 });

const graph = createReactAgent({
  llm,
  tools,
  prompt: new SystemMessage(SYSTEM_PROMPT),
});

(graph as any)._agentspan = {
  model: 'openai/gpt-4o-mini',
  tools,
  instructions: SYSTEM_PROMPT,
  framework: 'langgraph',
};

const PROMPT =
  "I'm flying from the US to Japan with $800. " +
  'How many yen will I get? The flight is 9,540 km — how far is that in miles?';

// ---------------------------------------------------------------------------
// Run on agentspan
// ---------------------------------------------------------------------------
async function main() {
  const runtime = new AgentRuntime();
  try {
    // Deploy to server. CLI alternative (recommended for CI/CD):
    //   agentspan deploy <module>
    // await runtime.deploy(graph);
    // await runtime.serve(graph);
    // Direct run for local development:
    const result = await runtime.run(graph, PROMPT);
    console.log('Status:', result.status);
    result.printResult();
  } finally {
    await runtime.shutdown();
  }
}

// Only run when executed directly (not when imported for discovery)
if (process.argv[1]?.endsWith('42-react-agent-system-prompt.ts') || process.argv[1]?.endsWith('42-react-agent-system-prompt.js')) {
  main().catch(console.error);
}
