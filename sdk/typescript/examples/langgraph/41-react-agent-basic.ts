/**
 * Basic ReAct Agent -- create_react_agent runs on Conductor.
 *
 * Demonstrates:
 *   - Using createReactAgent directly with AgentRuntime
 *   - No Agentspan wrapper needed -- pass the graph straight to runtime.run()
 *   - Agentspan detects the ReAct structure and runs LLM + tools on Conductor
 *
 * In production you would use:
 *   import { createReactAgent } from '@langchain/langgraph/prebuilt';
 *   import { ChatOpenAI } from '@langchain/openai';
 *   const graph = createReactAgent({ llm, tools: [calculate, countWords, reverseString] });
 */

import { AgentRuntime } from '../../src/index.js';

// ---------------------------------------------------------------------------
// Tool implementations
// ---------------------------------------------------------------------------
function calculate(expression: string): string {
  try {
    // Safe math evaluation
    const result = Function(
      '"use strict"; return (' + expression.replace(/sqrt/g, 'Math.sqrt').replace(/pi/g, 'Math.PI') + ')',
    )();
    return String(result);
  } catch (e) {
    return `Error evaluating expression: ${e}`;
  }
}

function countWords(text: string): string {
  return `The text contains ${text.split(/\s+/).filter(Boolean).length} word(s).`;
}

function reverseString(text: string): string {
  return text.split('').reverse().join('');
}

// ---------------------------------------------------------------------------
// Mock agent dispatch
// ---------------------------------------------------------------------------
function dispatch(query: string): string {
  const parts: string[] = [];

  if (query.includes('sqrt(256)') || query.includes('2**10')) {
    const sqrt = calculate('Math.sqrt(256)');
    const pow = calculate('2**10');
    parts.push(`sqrt(256) = ${sqrt}, 2^10 = ${pow}, sum = ${Number(sqrt) + Number(pow)}`);
  }

  if (query.toLowerCase().includes('count the words')) {
    const match = query.match(/'([^']+)'/);
    if (match) parts.push(countWords(match[1]));
  }

  if (query.toLowerCase().includes('reversed')) {
    const match = query.match(/'(\w+)'/g);
    const word = match?.[match.length - 1]?.replace(/'/g, '') ?? 'Agentspan';
    parts.push(`'${word}' reversed is '${reverseString(word)}'`);
  }

  return parts.join('\n\n') || 'I processed your request.';
}

// ---------------------------------------------------------------------------
// Mock compiled graph
// ---------------------------------------------------------------------------
const graph = {
  name: 'math_and_text_agent',

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
      "What is sqrt(256) + 2**10? " +
      "Also count the words in 'the quick brown fox jumps over the lazy dog'. " +
      "And what is 'Agentspan' reversed?",
    );
    console.log('Status:', result.status);
    result.printResult();
  } finally {
    await runtime.shutdown();
  }
}

main().catch(console.error);
