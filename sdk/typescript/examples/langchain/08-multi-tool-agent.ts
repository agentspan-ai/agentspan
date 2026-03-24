/**
 * Multi-Tool Agent -- agent with diverse tool categories for travel planning.
 *
 * Demonstrates:
 *   - Combining tools from different domains: time, currency, flight info
 *   - ChatOpenAI with bindTools() selecting and chaining multiple tool calls
 *   - Real LLM reasoning about which tools to use
 *   - Running via AgentRuntime
 *
 * Requires: OPENAI_API_KEY environment variable
 */

import { ChatOpenAI } from '@langchain/openai';
import { DynamicStructuredTool } from '@langchain/core/tools';
import { HumanMessage, AIMessage, ToolMessage, SystemMessage } from '@langchain/core/messages';
import { RunnableLambda } from '@langchain/core/runnables';
import { z } from 'zod';
import { AgentRuntime } from '../../src/index.js';

// ── Tool definitions ─────────────────────────────────────

const getLocalTimeTool = new DynamicStructuredTool({
  name: 'get_local_time',
  description: 'Get the current local time in a city. Supported: New York, London, Paris, Tokyo, Sydney, Dubai, Los Angeles.',
  schema: z.object({
    city: z.string().describe('City name'),
  }),
  func: async ({ city }) => {
    const timezones: Record<string, [string, number]> = {
      'new york': ['UTC-5 (EST)', -5],
      london: ['UTC+0 (GMT)', 0],
      paris: ['UTC+1 (CET)', 1],
      tokyo: ['UTC+9 (JST)', 9],
      sydney: ['UTC+11 (AEDT)', 11],
      dubai: ['UTC+4 (GST)', 4],
      'los angeles': ['UTC-8 (PST)', -8],
    };
    const key = city.toLowerCase().trim();
    const entry = timezones[key];
    if (!entry) return `Time data not available for ${city}.`;
    const [label, offset] = entry;
    const utcNow = new Date();
    const local = new Date(utcNow.getTime() + offset * 3600 * 1000);
    const hours = local.getUTCHours().toString().padStart(2, '0');
    const mins = local.getUTCMinutes().toString().padStart(2, '0');
    return `${city}: ${hours}:${mins} (${label})`;
  },
});

const convertCurrencyTool = new DynamicStructuredTool({
  name: 'convert_currency',
  description: 'Convert an amount from one currency to another. Supported: USD, EUR, GBP, JPY, AUD, CAD, CHF, INR.',
  schema: z.object({
    amount: z.number().describe('Amount to convert'),
    from: z.string().describe('Source currency code (e.g. "USD")'),
    to: z.string().describe('Target currency code (e.g. "JPY")'),
  }),
  func: async ({ amount, from, to }) => {
    const ratesToUsd: Record<string, number> = {
      usd: 1.0, eur: 1.08, gbp: 1.26, jpy: 0.0067,
      aud: 0.64, cad: 0.74, chf: 1.11, inr: 0.012,
    };
    const fromRate = ratesToUsd[from.toLowerCase()];
    const toRate = ratesToUsd[to.toLowerCase()];
    if (!fromRate || !toRate) {
      return `Currency conversion not supported for ${from}/${to}`;
    }
    const result = (amount * fromRate) / toRate;
    return `${amount} ${from.toUpperCase()} = ${result.toFixed(2)} ${to.toUpperCase()}`;
  },
});

const getFlightDurationTool = new DynamicStructuredTool({
  name: 'get_flight_duration',
  description: 'Get estimated flight duration between two cities.',
  schema: z.object({
    from: z.string().describe('Departure city'),
    to: z.string().describe('Arrival city'),
  }),
  func: async ({ from, to }) => {
    const durations: Record<string, string> = {
      'new york->london': '7h 30m',
      'london->new york': '8h 00m',
      'london->tokyo': '11h 45m',
      'tokyo->london': '12h 15m',
      'new york->los angeles': '5h 30m',
      'los angeles->tokyo': '11h 00m',
      'new york->tokyo': '14h 00m',
      'tokyo->new york': '13h 00m',
      'paris->new york': '8h 10m',
      'dubai->london': '7h 10m',
    };
    const key = `${from.toLowerCase()}->${to.toLowerCase()}`;
    const revKey = `${to.toLowerCase()}->${from.toLowerCase()}`;
    const duration = durations[key] ?? durations[revKey];
    if (duration) {
      return `Flight from ${from} to ${to}: approximately ${duration}`;
    }
    return `No direct flight data available for ${from} to ${to}`;
  },
});

// ── Agent loop ───────────────────────────────────────────

const tools = [getLocalTimeTool, convertCurrencyTool, getFlightDurationTool];
const toolMap = Object.fromEntries(tools.map((t) => [t.name, t]));

async function runTravelAgent(prompt: string): Promise<string> {
  const model = new ChatOpenAI({ modelName: 'gpt-4o-mini', temperature: 0 }).bindTools(tools);

  const messages: (SystemMessage | HumanMessage | AIMessage | ToolMessage)[] = [
    new SystemMessage(
      'You are a travel planning assistant. Use the provided tools to help with ' +
      'time zones, currency conversion, and flight duration estimates. ' +
      'Provide a comprehensive, well-formatted summary.'
    ),
    new HumanMessage(prompt),
  ];

  for (let i = 0; i < 5; i++) {
    const response = await model.invoke(messages);
    messages.push(response);

    const toolCalls = response.tool_calls ?? [];
    if (toolCalls.length === 0) {
      return typeof response.content === 'string'
        ? response.content
        : JSON.stringify(response.content);
    }

    for (const tc of toolCalls) {
      const tool = toolMap[tc.name];
      if (tool) {
        const result = await (tool as any).invoke(tc.args);
        messages.push(new ToolMessage({ content: String(result), tool_call_id: tc.id! }));
      }
    }
  }

  return 'Agent reached maximum iterations.';
}

// ── Wrap for Agentspan ───────────────────────────────────

const agentRunnable = new RunnableLambda({
  func: async (input: { input: string }) => {
    const output = await runTravelAgent(input.input);
    return { output };
  },
});

// Add agentspan metadata for extraction
(agentRunnable as any)._agentspan = {
  model: 'openai/gpt-4o-mini',
  tools,
  framework: 'langchain',
};

async function main() {
  const userPrompt =
    "I'm an American planning to travel from New York to Tokyo. " +
    'What time is it there right now, how long is the flight, ' +
    'and how much is 500 USD in JPY?';

  const runtime = new AgentRuntime();
  try {
    const result = await runtime.run(agentRunnable, userPrompt);
    console.log('Status:', result.status);
    result.printResult();
  } finally {
    await runtime.shutdown();
  }
}

main().catch(console.error);
