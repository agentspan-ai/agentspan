/**
 * Agent as Tool -- using one compiled graph as a tool inside another agent.
 *
 * Demonstrates:
 *   - Wrapping a CompiledStateGraph as a tool callable
 *   - An orchestrator agent calling specialist sub-agents via tool calls
 *   - Composing complex multi-agent systems from reusable graph components
 *   - Practical use case: orchestrator dispatching to math, writing, and trivia agents
 *
 * In production you would use:
 *   import { StateGraph, START, END } from '@langchain/langgraph';
 *   import { ToolNode, toolsCondition } from '@langchain/langgraph/prebuilt';
 */

import { AgentRuntime } from '../../src/index.js';

// ---------------------------------------------------------------------------
// Specialist sub-agent implementations (mock compiled graphs)
// ---------------------------------------------------------------------------
function askMathExpert(question: string): string {
  const q = question.toLowerCase();
  if (q.includes('15%') && q.includes('847')) {
    return 'To calculate 15% of 847: 847 * 0.15 = 127.05. Rounded to the nearest whole number: 127.';
  }
  if (q.includes('sqrt') || q.includes('square root')) {
    return 'Computing the square root as requested.';
  }
  return `Math analysis for: "${question}" -- The answer requires numerical computation.`;
}

function askWritingExpert(task: string): string {
  if (task.toLowerCase().includes('improve') || task.toLowerCase().includes('sentence')) {
    return '"The meeting did not go well, and the attendees were dissatisfied with the outcomes."';
  }
  return `Writing assistance: Polished version of the provided text.`;
}

function askTriviaExpert(question: string): string {
  if (question.toLowerCase().includes('world wide web')) {
    return 'Tim Berners-Lee invented the World Wide Web in 1989 while working at CERN.';
  }
  return `Trivia answer for: "${question}"`;
}

// ---------------------------------------------------------------------------
// Orchestrator dispatch logic
// ---------------------------------------------------------------------------
function orchestrate(query: string): string {
  const q = query.toLowerCase();

  if (q.includes('%') || q.includes('calculate') || q.includes('math') || /\d+.*\d+/.test(q)) {
    return `Routed to Math Expert:\n${askMathExpert(query)}`;
  }
  if (q.includes('improve') || q.includes('write') || q.includes('edit') || q.includes('sentence')) {
    return `Routed to Writing Expert:\n${askWritingExpert(query)}`;
  }
  if (q.includes('who') || q.includes('when') || q.includes('invent') || q.includes('history')) {
    return `Routed to Trivia Expert:\n${askTriviaExpert(query)}`;
  }

  return `General response: I've analyzed your question and here is my answer.`;
}

// ---------------------------------------------------------------------------
// Mock compiled graph
// ---------------------------------------------------------------------------
const graph = {
  name: 'orchestrator_with_subagents',

  invoke: async (input: Record<string, unknown>) => {
    const query = (input.input as string) ?? '';
    const result = orchestrate(query);
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
      ['orchestrator', {}],
      ['tools', {}],
      ['__end__', {}],
    ]),
    edges: [
      ['__start__', 'orchestrator'],
      ['orchestrator', 'tools'],
      ['tools', 'orchestrator'],
      ['orchestrator', '__end__'],
    ],
  }),

  nodes: new Map([
    ['orchestrator', {}],
    ['tools', {}],
  ]),

  stream: async function* (input: Record<string, unknown>) {
    const query = (input.input as string) ?? '';
    const result = orchestrate(query);
    yield ['updates', { orchestrator: { messages: [{ role: 'assistant', content: result }] } }];
    yield ['values', { messages: [{ role: 'assistant', content: result }] }];
  },
};

// ---------------------------------------------------------------------------
// Run
// ---------------------------------------------------------------------------
async function main() {
  const queries = [
    'What is 15% of 847, rounded to the nearest whole number?',
    'Who invented the World Wide Web and in what year?',
    "Improve this sentence: 'The meeting was went not good and people was unhappy.'",
  ];

  const runtime = new AgentRuntime();
  try {
    for (const query of queries) {
      console.log(`\nQuery: ${query}`);
      const result = await runtime.run(graph, query);
      result.printResult();
      console.log('-'.repeat(60));
    }
  } finally {
    await runtime.shutdown();
  }
}

main().catch(console.error);
