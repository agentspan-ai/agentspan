/**
 * Debate Agents -- two agents arguing opposing positions.
 *
 * Demonstrates:
 *   - Two specialized agents with opposing system prompts
 *   - Alternating turns tracked in state
 *   - A judge agent that evaluates the debate and declares a winner
 *   - Practical use case: pros/cons analysis, brainstorming, red-teaming
 */

import { StateGraph, START, END, Annotation } from '@langchain/langgraph';
import { ChatOpenAI } from '@langchain/openai';
import { HumanMessage, SystemMessage } from '@langchain/core/messages';
import { AgentRuntime } from '../../src/index.js';

const llm = new ChatOpenAI({ model: 'gpt-4o-mini', temperature: 0.3 });

const MAX_ROUNDS = 2;

// ---------------------------------------------------------------------------
// State schema
// ---------------------------------------------------------------------------
interface Turn {
  speaker: string;
  argument: string;
}

const DebateState = Annotation.Root({
  topic: Annotation<string>({
    reducer: (_prev: string, next: string) => next ?? _prev,
    default: () => '',
  }),
  turns: Annotation<Turn[]>({
    reducer: (_prev: Turn[], next: Turn[]) => next ?? _prev,
    default: () => [],
  }),
  round: Annotation<number>({
    reducer: (_prev: number, next: number) => next ?? _prev,
    default: () => 0,
  }),
  verdict: Annotation<string>({
    reducer: (_prev: string, next: string) => next ?? _prev,
    default: () => '',
  }),
});

type State = typeof DebateState.State;

// ---------------------------------------------------------------------------
// Node functions
// ---------------------------------------------------------------------------
async function agentPro(state: State): Promise<Partial<State>> {
  const previous = (state.turns || [])
    .map((t) => `${t.speaker}: ${t.argument}`)
    .join('\n');

  let prompt = `Topic: ${state.topic}`;
  if (previous) {
    prompt += `\n\nDebate so far:\n${previous}\n\nNow make your argument in favour (2-3 sentences).`;
  } else {
    prompt += '\n\nMake your opening argument in favour of this topic (2-3 sentences).';
  }

  const response = await llm.invoke([
    new SystemMessage(
      'You are a persuasive debater arguing IN FAVOUR of the given topic. Be concise and compelling.',
    ),
    new HumanMessage(prompt),
  ]);

  const content = typeof response.content === 'string' ? response.content.trim() : '';
  const turns = [...(state.turns || []), { speaker: 'PRO', argument: content }];
  return { turns };
}

async function agentCon(state: State): Promise<Partial<State>> {
  const previous = (state.turns || [])
    .map((t) => `${t.speaker}: ${t.argument}`)
    .join('\n');

  const response = await llm.invoke([
    new SystemMessage(
      'You are a persuasive debater arguing AGAINST the given topic. Be concise and direct.',
    ),
    new HumanMessage(
      `Topic: ${state.topic}\n\nDebate so far:\n${previous}\n\nMake your counter-argument (2-3 sentences).`,
    ),
  ]);

  const content = typeof response.content === 'string' ? response.content.trim() : '';
  const turns = [...(state.turns || []), { speaker: 'CON', argument: content }];
  return { turns, round: (state.round || 0) + 1 };
}

async function judge(state: State): Promise<Partial<State>> {
  const transcript = (state.turns || [])
    .map((t) => `${t.speaker}: ${t.argument}`)
    .join('\n\n');

  const response = await llm.invoke([
    new SystemMessage(
      'You are an impartial debate judge. Review the debate transcript and:\n' +
        '1. Identify which side made the stronger arguments\n' +
        '2. Declare the winner (PRO or CON) and explain why in 2-3 sentences\n' +
        '3. Note any logical fallacies or weak points',
    ),
    new HumanMessage(`Debate topic: ${state.topic}\n\nTranscript:\n${transcript}`),
  ]);

  const content = typeof response.content === 'string' ? response.content.trim() : '';
  return { verdict: content };
}

function continueOrJudge(state: State): string {
  if ((state.round || 0) >= MAX_ROUNDS) {
    return 'judge';
  }
  return 'con';
}

// ---------------------------------------------------------------------------
// Build the graph
// ---------------------------------------------------------------------------
const builder = new StateGraph(DebateState);
builder.addNode('pro', agentPro);
builder.addNode('con', agentCon);
builder.addNode('judge', judge);

builder.addEdge(START, 'pro');
builder.addConditionalEdges('con', continueOrJudge, { judge: 'judge', con: 'pro' });
builder.addEdge('pro', 'con');
builder.addEdge('judge', END);

const graph = builder.compile();

(graph as any)._agentspan = {
  model: 'openai/gpt-4o-mini',
  tools: [],
  framework: 'langgraph',
};

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
    const result = await runtime.run(
    graph,
    'Artificial intelligence will create more jobs than it destroys.',
    );
    console.log('Status:', result.status);
    result.printResult();
  } finally {
    await runtime.shutdown();
  }
}

// Only run when executed directly (not when imported for discovery)
if (process.argv[1]?.endsWith('36-debate-agents.ts') || process.argv[1]?.endsWith('36-debate-agents.js')) {
  main().catch(console.error);
}
