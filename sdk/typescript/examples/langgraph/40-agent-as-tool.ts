/**
 * Agent as Tool -- using one compiled graph as a tool inside another agent.
 *
 * Demonstrates:
 *   - Wrapping a compiled StateGraph as a DynamicStructuredTool
 *   - An orchestrator agent calling specialist sub-agents via tool calls
 *   - Composing complex multi-agent systems from reusable graph components
 *   - Practical use case: orchestrator dispatching to a math agent and a writing agent
 */

import { StateGraph, START, END, MessagesAnnotation } from '@langchain/langgraph';
import { ToolNode, toolsCondition } from '@langchain/langgraph/prebuilt';
import { ChatOpenAI } from '@langchain/openai';
import { DynamicStructuredTool } from '@langchain/core/tools';
import { HumanMessage, SystemMessage } from '@langchain/core/messages';
import { z } from 'zod';
import { AgentRuntime } from '../../src/index.js';

// ---------------------------------------------------------------------------
// Specialist agents (as plain compiled graphs)
// ---------------------------------------------------------------------------
function makeSpecialist(systemPrompt: string) {
  const specialistLlm = new ChatOpenAI({ model: 'gpt-4o-mini', temperature: 0 });

  async function node(state: typeof MessagesAnnotation.State) {
    const msgs = [new SystemMessage(systemPrompt), ...state.messages];
    const response = await specialistLlm.invoke(msgs);
    return { messages: [response] };
  }

  const b = new StateGraph(MessagesAnnotation);
  b.addNode('specialist', node);
  b.addEdge(START, 'specialist');
  b.addEdge('specialist', END);
  return b.compile();
}

const mathGraph = makeSpecialist(
  'You are a math expert. Solve mathematical problems precisely with step-by-step reasoning.',
);

const writingGraph = makeSpecialist(
  'You are a professional writer and editor. Help craft, improve, and polish written content.',
);

const triviaGraph = makeSpecialist(
  'You are a trivia expert. Answer questions about history, science, culture, and general knowledge.',
);

// ---------------------------------------------------------------------------
// Wrap specialist graphs as tool callables
// ---------------------------------------------------------------------------
const askMathExpertTool = new DynamicStructuredTool({
  name: 'ask_math_expert',
  description: 'Send a math problem to the math specialist agent and get the answer.',
  schema: z.object({
    question: z.string().describe('The math problem to solve'),
  }),
  func: async ({ question }) => {
    const result = await mathGraph.invoke({ messages: [new HumanMessage(question)] });
    const msgs = result.messages;
    const last = msgs[msgs.length - 1];
    return typeof last.content === 'string' ? last.content : JSON.stringify(last.content);
  },
});

const askWritingExpertTool = new DynamicStructuredTool({
  name: 'ask_writing_expert',
  description: 'Send a writing task to the writing specialist agent and get the result.',
  schema: z.object({
    task: z.string().describe('The writing task'),
  }),
  func: async ({ task }) => {
    const result = await writingGraph.invoke({ messages: [new HumanMessage(task)] });
    const msgs = result.messages;
    const last = msgs[msgs.length - 1];
    return typeof last.content === 'string' ? last.content : JSON.stringify(last.content);
  },
});

const askTriviaExpertTool = new DynamicStructuredTool({
  name: 'ask_trivia_expert',
  description: 'Look up a trivia fact or answer a general knowledge question.',
  schema: z.object({
    question: z.string().describe('The trivia question'),
  }),
  func: async ({ question }) => {
    const result = await triviaGraph.invoke({ messages: [new HumanMessage(question)] });
    const msgs = result.messages;
    const last = msgs[msgs.length - 1];
    return typeof last.content === 'string' ? last.content : JSON.stringify(last.content);
  },
});

// ---------------------------------------------------------------------------
// Orchestrator agent
// ---------------------------------------------------------------------------
const tools = [askMathExpertTool, askWritingExpertTool, askTriviaExpertTool];
const orchestratorLlm = new ChatOpenAI({ model: 'gpt-4o-mini', temperature: 0 }).bindTools(tools);
const toolNode = new ToolNode(tools);

async function orchestrator(state: typeof MessagesAnnotation.State) {
  const system = new SystemMessage(
    'You are an orchestrator. Route tasks to the appropriate specialist:\n' +
      '- Math problems -> ask_math_expert\n' +
      '- Writing/editing tasks -> ask_writing_expert\n' +
      '- General knowledge/trivia -> ask_trivia_expert\n' +
      "Combine the specialist's answer into a final helpful response.",
  );
  const msgs = [system, ...state.messages];
  const response = await orchestratorLlm.invoke(msgs);
  return { messages: [response] };
}

const orchBuilder = new StateGraph(MessagesAnnotation)
  .addNode('orchestrator', orchestrator)
  .addNode('tools', toolNode)
  .addEdge(START, 'orchestrator')
  .addConditionalEdges('orchestrator', toolsCondition)
  .addEdge('tools', 'orchestrator');

const graph = orchBuilder.compile();

(graph as any)._agentspan = {
  model: 'openai/gpt-4o-mini',
  tools,
  framework: 'langgraph',
};

// ---------------------------------------------------------------------------
// Run on agentspan
// ---------------------------------------------------------------------------
async function main() {
  const queries = [
    'What is 15% of 847, rounded to the nearest whole number?',
    'Who invented the World Wide Web and in what year?',
    "Improve this sentence: 'The meeting was went not good and people was unhappy.'",
  ];

  const runtime = new AgentRuntime();
  try {
    // Deploy to server. CLI alternative (recommended for CI/CD):
    //   agentspan deploy <module>
    // await runtime.deploy(graph);
    // await runtime.serve(graph);
    // Direct run for local development:
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

// Only run when executed directly (not when imported for discovery)
if (process.argv[1]?.endsWith('40-agent-as-tool.ts') || process.argv[1]?.endsWith('40-agent-as-tool.js')) {
  main().catch(console.error);
}
