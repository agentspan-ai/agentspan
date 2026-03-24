/**
 * ReAct with Tools -- LangChain agent using tool-calling with a manual loop.
 *
 * Demonstrates:
 *   - Binding DynamicStructuredTool instances to ChatOpenAI via bindTools()
 *   - Manual tool-calling loop (no full AgentExecutor needed)
 *   - Country information lookup tools: population, capital, currency
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

const getPopulation = new DynamicStructuredTool({
  name: 'get_population',
  description: 'Get the population of a country by name.',
  schema: z.object({ country: z.string().describe('Country name, e.g. "Japan"') }),
  func: async ({ country }) => {
    const data: Record<string, string> = {
      usa: '~335 million', china: '~1.4 billion', india: '~1.45 billion',
      germany: '~84 million', brazil: '~215 million', japan: '~123 million',
      france: '~68 million', uk: '~67 million',
    };
    const pop = data[country.toLowerCase()];
    return pop ? `${country}: population is ${pop}` : `Population data not available for ${country}.`;
  },
});

const getCapital = new DynamicStructuredTool({
  name: 'get_capital',
  description: 'Get the capital city of a country.',
  schema: z.object({ country: z.string().describe('Country name') }),
  func: async ({ country }) => {
    const data: Record<string, string> = {
      usa: 'Washington D.C.', china: 'Beijing', india: 'New Delhi',
      germany: 'Berlin', brazil: 'Brasilia', japan: 'Tokyo',
      france: 'Paris', uk: 'London',
    };
    const cap = data[country.toLowerCase()];
    return cap ? `${country}: capital is ${cap}` : `Capital data not available for ${country}.`;
  },
});

const getCurrency = new DynamicStructuredTool({
  name: 'get_currency',
  description: 'Get the currency of a country.',
  schema: z.object({ country: z.string().describe('Country name') }),
  func: async ({ country }) => {
    const data: Record<string, string> = {
      usa: 'US Dollar (USD)', germany: 'Euro (EUR)', japan: 'Japanese Yen (JPY)',
      uk: 'British Pound (GBP)', india: 'Indian Rupee (INR)', china: 'Chinese Yuan (CNY)',
      brazil: 'Brazilian Real (BRL)', france: 'Euro (EUR)',
    };
    const cur = data[country.toLowerCase()];
    return cur ? `${country}: currency is ${cur}` : `Currency data not available for ${country}.`;
  },
});

// ── Manual tool-calling agent loop ───────────────────────

const tools = [getPopulation, getCapital, getCurrency];
const toolMap = Object.fromEntries(tools.map((t) => [t.name, t]));

async function runAgentLoop(prompt: string): Promise<string> {
  const model = new ChatOpenAI({ modelName: 'gpt-4o-mini', temperature: 0 }).bindTools(tools);

  const messages: (SystemMessage | HumanMessage | AIMessage | ToolMessage)[] = [
    new SystemMessage('You are a helpful assistant that looks up country information using the provided tools.'),
    new HumanMessage(prompt),
  ];

  // Loop until the model stops calling tools (max 5 iterations)
  for (let i = 0; i < 5; i++) {
    const response = await model.invoke(messages);
    messages.push(response);

    const toolCalls = response.tool_calls ?? [];
    if (toolCalls.length === 0) {
      // No more tool calls -- return final text
      return typeof response.content === 'string'
        ? response.content
        : JSON.stringify(response.content);
    }

    // Execute each tool call
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
  const userPrompt = 'What is the capital and currency of Japan, and what is its population?';

  // ── Run on agentspan ──────────────────────────────────────
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
