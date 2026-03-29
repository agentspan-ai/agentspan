/**
 * ReAct Agent Multi-Model -- createReactAgent works with any LangChain-supported model.
 *
 * Demonstrates:
 *   - createReactAgent with a different model (still using ChatOpenAI for TS examples)
 *   - Date-related tools for practical utility
 *   - Same code pattern, swappable model -- no Agentspan-specific changes needed
 *
 * Note: The Python version uses ChatAnthropic. This TypeScript port uses ChatOpenAI
 * with gpt-4o-mini since @langchain/anthropic may not be installed. The pattern
 * is identical -- swap the LLM constructor to use any supported provider.
 */

import { createReactAgent } from '@langchain/langgraph/prebuilt';
import { ChatOpenAI } from '@langchain/openai';
import { DynamicStructuredTool } from '@langchain/core/tools';
import { z } from 'zod';
import { AgentRuntime } from '../../src/index.js';

// ---------------------------------------------------------------------------
// Tool definitions
// ---------------------------------------------------------------------------
const getTodayTool = new DynamicStructuredTool({
  name: 'get_today',
  description: "Return today's date in YYYY-MM-DD format.",
  schema: z.object({}),
  func: async () => {
    return new Date().toISOString().slice(0, 10);
  },
});

const daysBetweenTool = new DynamicStructuredTool({
  name: 'days_between',
  description: 'Calculate the number of days between two dates (YYYY-MM-DD format).',
  schema: z.object({
    date1: z.string().describe('First date in YYYY-MM-DD format'),
    date2: z.string().describe('Second date in YYYY-MM-DD format'),
  }),
  func: async ({ date1, date2 }) => {
    try {
      const d1 = new Date(date1);
      const d2 = new Date(date2);
      const diff = Math.abs(Math.round((d2.getTime() - d1.getTime()) / (1000 * 60 * 60 * 24)));
      return `There are ${diff} days between ${date1} and ${date2}.`;
    } catch (e) {
      return `Invalid date format: ${e}`;
    }
  },
});

const dayOfWeekTool = new DynamicStructuredTool({
  name: 'day_of_week',
  description: 'Return the day of the week for a given date (YYYY-MM-DD format).',
  schema: z.object({
    date_str: z.string().describe('Date in YYYY-MM-DD format'),
  }),
  func: async ({ date_str }) => {
    try {
      const d = new Date(date_str);
      const days = ['Sunday', 'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday'];
      return `${date_str} falls on a ${days[d.getDay()]}.`;
    } catch (e) {
      return `Invalid date format: ${e}`;
    }
  },
});

// ---------------------------------------------------------------------------
// Build the graph
// ---------------------------------------------------------------------------
const tools = [getTodayTool, daysBetweenTool, dayOfWeekTool];
const llm = new ChatOpenAI({ model: 'gpt-4o-mini', temperature: 0 });

const graph = createReactAgent({ llm, tools });

(graph as any)._agentspan = {
  model: 'openai/gpt-4o-mini',
  tools,
  framework: 'langgraph',
};

const PROMPT =
  "What day of the week is today? " +
  "How many days until New Year's Day 2026? " +
  'What day of the week will that be?';

// ---------------------------------------------------------------------------
// Run on agentspan
// ---------------------------------------------------------------------------
async function main() {
  const runtime = new AgentRuntime();
  try {
    // Deploy to server. CLI alternative (recommended for CI/CD):
    //   agentspan deploy <module>
    await runtime.deploy(graph);
    await runtime.serve(graph);

    // Quick test: uncomment below (and comment out serve) to run directly.
    // const result = await runtime.run(graph, PROMPT);
    // console.log('Status:', result.status);
    // result.printResult();
  } finally {
    await runtime.shutdown();
  }
}

// Only run when executed directly (not when imported for discovery)
if (process.argv[1]?.endsWith('43-react-agent-multi-model.ts') || process.argv[1]?.endsWith('43-react-agent-multi-model.js')) {
  main().catch(console.error);
}
