/**
 * Debate Agents -- two agents arguing opposing positions.
 *
 * Demonstrates:
 *   - Two specialized agents with opposing system prompts
 *   - Alternating turns tracked in state
 *   - A judge agent that evaluates the debate and declares a winner
 *   - Practical use case: pros/cons analysis, brainstorming, red-teaming
 *
 * In production you would use:
 *   import { StateGraph, START, END } from '@langchain/langgraph';
 *   builder.addConditionalEdges("con", continueOrJudge, { ... });
 */

import { AgentRuntime } from '../../src/index.js';

// ---------------------------------------------------------------------------
// State types
// ---------------------------------------------------------------------------
interface Turn {
  speaker: string;
  argument: string;
}

interface DebateState {
  topic: string;
  turns: Turn[];
  round: number;
  verdict: string;
}

const MAX_ROUNDS = 2;

// ---------------------------------------------------------------------------
// Node functions
// ---------------------------------------------------------------------------
function agentPro(state: DebateState): Partial<DebateState> {
  const round = state.round ?? 0;
  let argument: string;

  if (round === 0) {
    argument =
      'AI will create more jobs than it destroys by spawning entirely new industries. ' +
      'Just as the Industrial Revolution created factory jobs, AI is creating roles in ' +
      'data science, AI ethics, prompt engineering, and AI-human collaboration.';
  } else {
    argument =
      'History consistently shows that technology creates more jobs than it eliminates. ' +
      'The key is adaptation: AI augments human capabilities rather than replacing them, ' +
      'leading to higher productivity and new market opportunities.';
  }

  const turns = [...(state.turns ?? []), { speaker: 'PRO', argument }];
  return { turns };
}

function agentCon(state: DebateState): Partial<DebateState> {
  const round = (state.round ?? 0) + 1;
  let argument: string;

  if (round === 1) {
    argument =
      'AI automation threatens millions of jobs in manufacturing, customer service, and ' +
      'transportation. Unlike previous revolutions, AI can replicate cognitive tasks, ' +
      'making even white-collar workers vulnerable to displacement.';
  } else {
    argument =
      'The pace of AI advancement outstrips the ability of workers to retrain. ' +
      'New AI jobs require advanced skills that most displaced workers lack, ' +
      'creating a growing inequality gap rather than equal opportunity.';
  }

  const turns = [...(state.turns ?? []), { speaker: 'CON', argument }];
  return { turns, round };
}

function judge(state: DebateState): Partial<DebateState> {
  const transcript = state.turns
    .map((t) => `${t.speaker}: ${t.argument}`)
    .join('\n\n');

  const verdict =
    `Debate Analysis:\n\n` +
    `Both sides presented compelling arguments. PRO effectively highlighted historical ` +
    `precedent and the emergence of new industries. CON raised valid concerns about the ` +
    `pace of change and the skills gap.\n\n` +
    `Winner: PRO (by a narrow margin)\n\n` +
    `Reasoning: While CON's concerns about displacement are valid, PRO's historical ` +
    `argument is supported by evidence from multiple technological revolutions. The ` +
    `key differentiator is that PRO acknowledged the need for adaptation, making ` +
    `a more nuanced case.`;

  return { verdict };
}

function continueOrJudge(state: DebateState): string {
  if ((state.round ?? 0) >= MAX_ROUNDS) return 'judge';
  return 'con';
}

// ---------------------------------------------------------------------------
// Mock compiled graph
// ---------------------------------------------------------------------------
const graph = {
  name: 'debate_agents',

  invoke: async (input: Record<string, unknown>) => {
    const topic = (input.input as string) ?? '';
    let state: DebateState = { topic, turns: [], round: 0, verdict: '' };

    for (let i = 0; i < MAX_ROUNDS; i++) {
      state = { ...state, ...agentPro(state) };
      state = { ...state, ...agentCon(state) };

      if (continueOrJudge(state) === 'judge') break;
    }

    state = { ...state, ...judge(state) };
    return { output: state.verdict };
  },

  getGraph: () => ({
    nodes: new Map([
      ['__start__', {}],
      ['pro', {}],
      ['con', {}],
      ['judge', {}],
      ['__end__', {}],
    ]),
    edges: [
      ['__start__', 'pro'],
      ['pro', 'con'],
      // Conditional: con -> pro (continue) | judge (done)
      ['judge', '__end__'],
    ],
  }),

  nodes: new Map([
    ['pro', {}],
    ['con', {}],
    ['judge', {}],
  ]),

  stream: async function* (input: Record<string, unknown>) {
    const topic = (input.input as string) ?? '';
    let state: DebateState = { topic, turns: [], round: 0, verdict: '' };

    for (let i = 0; i < MAX_ROUNDS; i++) {
      state = { ...state, ...agentPro(state) };
      yield ['updates', { pro: { argument: state.turns[state.turns.length - 1].argument } }];

      state = { ...state, ...agentCon(state) };
      yield ['updates', { con: { argument: state.turns[state.turns.length - 1].argument } }];

      if (continueOrJudge(state) === 'judge') break;
    }

    state = { ...state, ...judge(state) };
    yield ['updates', { judge: { verdict: state.verdict } }];
    yield ['values', { output: state.verdict }];
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
      'Artificial intelligence will create more jobs than it destroys.',
    );
    console.log('Status:', result.status);
    result.printResult();
  } finally {
    await runtime.shutdown();
  }
}

main().catch(console.error);
