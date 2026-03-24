/**
 * Custom Tools -- advanced tool definitions with typed schemas.
 *
 * Demonstrates:
 *   - DynamicStructuredTool with Zod schemas for unit conversion, formatting, percentage
 *   - ChatOpenAI with bindTools() for structured tool invocation
 *   - Manual tool-calling loop with multiple queries
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

const convertUnitsTool = new DynamicStructuredTool({
  name: 'convert_units',
  description: 'Convert a value from one unit to another. Supported: km<->miles, kg<->lbs, celsius<->fahrenheit, meters<->feet.',
  schema: z.object({
    value: z.number().describe('The numeric value to convert'),
    fromUnit: z.string().describe('Source unit (e.g. "km", "celsius")'),
    toUnit: z.string().describe('Target unit (e.g. "miles", "fahrenheit")'),
  }),
  func: async ({ value, fromUnit, toUnit }) => {
    const from = fromUnit.toLowerCase().trim();
    const to = toUnit.toLowerCase().trim();
    const conversions: Record<string, (v: number) => number> = {
      'km->miles': (v) => v * 0.621371,
      'miles->km': (v) => v * 1.60934,
      'kg->lbs': (v) => v * 2.20462,
      'lbs->kg': (v) => v * 0.453592,
      'celsius->fahrenheit': (v) => v * 9 / 5 + 32,
      'fahrenheit->celsius': (v) => (v - 32) * 5 / 9,
      'meters->feet': (v) => v * 3.28084,
      'feet->meters': (v) => v * 0.3048,
    };
    const key = `${from}->${to}`;
    const fn = conversions[key];
    if (fn) {
      return `${value} ${from} = ${fn(value).toFixed(4)} ${to}`;
    }
    return `Conversion from ${from} to ${to} is not supported.`;
  },
});

const formatNumberTool = new DynamicStructuredTool({
  name: 'format_number',
  description: 'Format a number with specified decimal places and optional comma separators.',
  schema: z.object({
    num: z.number().describe('The number to format'),
    decimalPlaces: z.number().default(2).describe('Number of decimal places'),
    useComma: z.boolean().default(true).describe('Whether to use comma separators'),
  }),
  func: async ({ num, decimalPlaces, useComma }) => {
    const formatted = useComma
      ? num.toLocaleString('en-US', { minimumFractionDigits: decimalPlaces, maximumFractionDigits: decimalPlaces })
      : num.toFixed(decimalPlaces);
    return `Formatted: ${formatted}`;
  },
});

const percentageTool = new DynamicStructuredTool({
  name: 'calculate_percentage',
  description: 'Calculate what percentage one number is of another.',
  schema: z.object({
    part: z.number().describe('The part value'),
    whole: z.number().describe('The whole value'),
  }),
  func: async ({ part, whole }) => {
    if (whole === 0) return "Error: 'whole' cannot be zero.";
    const pct = (part / whole) * 100;
    return `${part} is ${pct.toFixed(2)}% of ${whole}`;
  },
});

// ── Agent loop ───────────────────────────────────────────

const tools = [convertUnitsTool, formatNumberTool, percentageTool];
const toolMap = Object.fromEntries(tools.map((t) => [t.name, t]));

async function runAgentLoop(prompt: string): Promise<string> {
  const model = new ChatOpenAI({ modelName: 'gpt-4o-mini', temperature: 0 }).bindTools(tools);

  const messages: (SystemMessage | HumanMessage | AIMessage | ToolMessage)[] = [
    new SystemMessage('You are a helpful math assistant. Use the provided tools to perform conversions, formatting, and percentage calculations.'),
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

// ── Wrap as runnable for Agentspan ─────────────────────────

const agentRunnable = new RunnableLambda({
  func: async (input: { input: string }) => {
    const output = await runAgentLoop(input.input);
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
  const runtime = new AgentRuntime();

  const queries = [
    'Convert 100 km to miles.',
    'Format the number 1234567.891 with 3 decimal places.',
    'What percentage is 37 of 185?',
  ];

  try {
    for (const query of queries) {
      console.log(`\n${'='.repeat(60)}`);
      console.log(`Q: ${query}`);
      const result = await runtime.run(agentRunnable, query);
      console.log('Status:', result.status);
      result.printResult();
    }
  } finally {
    await runtime.shutdown();
  }
}

main().catch(console.error);
