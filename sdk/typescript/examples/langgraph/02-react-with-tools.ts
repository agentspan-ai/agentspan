/**
 * ReAct Agent with Tools -- createReactAgent with practical tools.
 *
 * Demonstrates:
 *   - Defining tools with DynamicStructuredTool from @langchain/core/tools
 *   - Passing tools to createReactAgent for a ReAct-style loop
 *   - Multi-tool invocation in a single query
 */

import { createReactAgent } from '@langchain/langgraph/prebuilt';
import { ChatOpenAI } from '@langchain/openai';
import { HumanMessage } from '@langchain/core/messages';
import { DynamicStructuredTool } from '@langchain/core/tools';
import { z } from 'zod';
import { AgentRuntime } from '../../src/index.js';

// ---------------------------------------------------------------------------
// Tool definitions
// ---------------------------------------------------------------------------
const calculateTool = new DynamicStructuredTool({
  name: 'calculate',
  description: 'Evaluate a mathematical expression. Supports basic arithmetic, sqrt, and pi.',
  schema: z.object({
    expression: z.string().describe('The mathematical expression to evaluate'),
  }),
  func: async ({ expression }) => {
    try {
      const sanitized = expression.replace(/[^0-9+\-*/().sqrtpi ]/g, '');
      const result = Function(
        '"use strict"; const sqrt = Math.sqrt; const pi = Math.PI; return (' +
          sanitized +
          ')',
      )();
      return String(result);
    } catch (e) {
      return `Error evaluating expression: ${e}`;
    }
  },
});

const countWordsTool = new DynamicStructuredTool({
  name: 'count_words',
  description: 'Count the number of words in a given text.',
  schema: z.object({
    text: z.string().describe('The text to count words in'),
  }),
  func: async ({ text }) => {
    const words = text.trim().split(/\s+/);
    return `The text contains ${words.length} word(s).`;
  },
});

const getTodayTool = new DynamicStructuredTool({
  name: 'get_today',
  description: "Return today's date in YYYY-MM-DD format.",
  schema: z.object({}),
  func: async () => new Date().toISOString().slice(0, 10),
});

// ---------------------------------------------------------------------------
// Build the graph
// ---------------------------------------------------------------------------
const llm = new ChatOpenAI({ model: 'gpt-4o-mini', temperature: 0 });
const graph = createReactAgent({
  llm,
  tools: [calculateTool, countWordsTool, getTodayTool],
});

const PROMPT =
  "What is the square root of 256? Also, how many words are in 'the quick brown fox'? And what is today's date?";

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
      console.log(`  ${role}: [tool_calls]`, JSON.stringify(msg.tool_calls.map((tc: any) => tc.name)));
    } else {
      const content = typeof msg.content === 'string' ? msg.content.slice(0, 200) : JSON.stringify(msg.content);
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
